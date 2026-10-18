"""Bounded read-only Gmail metadata collection, no message body or mutation.

Gmail's narrow gmail.metadata scope permits message headers and history, not
message content. A baseline samples the latest 75 INBOX messages; thereafter
history deltas maintain those and newly encountered inbox messages. No claim
is made that this is a full mailbox archive.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, ProxyHandler, HTTPSHandler, build_opener

from .core.contracts import (AuthenticationPollError, Event, PermanentPollError,
                             RateLimitPollError, TransientPollError)
from .core.store import encode
from .google_oauth import NoRedirect, _unique

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
SERVICE = "gmail"
LIMIT = 256 * 1024
MAX_RECENT = 75
MAX_HISTORY_PAGES = 6
MAX_CHANGES = 150
ERROR = "Gmail read-only metadata collection failed"
ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
HISTORY = re.compile(r"[0-9]{1,25}\Z")
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+\Z")


class HistoryExpired(Exception):
    """A Gmail history cursor is no longer available; use a bounded baseline."""


class MessageGone(Exception):
    """A message was removed between the history/list step and GET."""


def account_for(email):
    if not isinstance(email, str) or len(email) > 320 or not EMAIL.fullmatch(email):
        raise ValueError("invalid Gmail profile identity")
    return "gmail:" + sha256(email.casefold().encode("utf-8")).hexdigest()


def valid_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid Gmail message/thread identity")
    return value


def valid_history(value):
    if not isinstance(value, str) or not HISTORY.fullmatch(value):
        raise ValueError("invalid Gmail history cursor")
    return value


def clean(value, limit):
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError("invalid Gmail metadata")
    return "".join(c for c in value[:limit] if c in "\t\n" or (
        ord(c) >= 32 and not 127 <= ord(c) <= 159 and
        c not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))


def get_json(url, bearer, *, missing=None):
    """GET only Google's fixed Gmail API host; deny proxies and redirects."""
    if not isinstance(bearer, str) or not 8 <= len(bearer) <= 4096:
        raise ValueError("invalid Gmail bearer")
    if not isinstance(url, str) or not url.startswith(BASE + "/") or len(url) > 8192:
        raise ValueError("unexpected Gmail URL")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                          NoRedirect())
    req = Request(url, method="GET", headers={
        "Authorization": "Bearer " + bearer,
        "Accept": "application/json",
        "User-Agent": "assistant-hub-gmail-metadata-readonly/1",
    })
    try:
        with opener.open(req, timeout=12) as res:
            if res.status != 200 or res.headers.get_content_type() != "application/json":
                raise PermanentPollError(ERROR)
            raw = res.read(LIMIT + 1)
    except HTTPError as ex:
        code = ex.code
        ex.close()
        if code == 404 and missing == "history":
            raise HistoryExpired() from None
        if code == 404 and missing == "message":
            raise MessageGone() from None
        if code in (401, 403):
            raise AuthenticationPollError(ERROR) from None
        if code == 429:
            raise RateLimitPollError(ERROR) from None
        if code in (408, 500, 502, 503, 504):
            raise TransientPollError(ERROR) from None
        raise PermanentPollError(ERROR) from None
    except (OSError, URLError, TimeoutError):
        raise TransientPollError(ERROR) from None
    if len(raw) > LIMIT:
        raise PermanentPollError(ERROR)
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (UnicodeError, ValueError, RecursionError):
        raise PermanentPollError(ERROR) from None


class GmailReader:
    def __init__(self, bearer, *, transport=get_json):
        if not isinstance(bearer, str) or not 8 <= len(bearer) <= 4096:
            raise ValueError("invalid Gmail token")
        if not callable(transport):
            raise ValueError("Gmail transport required")
        self._bearer = bearer
        self._get = transport

    def profile(self):
        obj = self._get(BASE + "/profile", self._bearer)
        try:
            account_for(obj["emailAddress"])
            valid_history(obj["historyId"])
            return obj["emailAddress"], obj["historyId"]
        except (KeyError, ValueError, TypeError):
            raise PermanentPollError(ERROR) from None

    def recent(self):
        """Only latest MAX_RECENT inbox records, not a full inbox crawl."""
        obj = self._get(BASE + "/messages?" + urlencode({
            "labelIds": "INBOX", "maxResults": str(MAX_RECENT)
        }), self._bearer)
        try:
            items = obj.get("messages", [])
            if not isinstance(items, list) or len(items) > MAX_RECENT:
                raise ValueError()
            ids = [valid_id(item["id"]) for item in items]
            if len(set(ids)) != len(ids):
                raise ValueError()
            page = obj.get("nextPageToken")
            if page is not None and (not isinstance(page, str) or not 1 <= len(page) <= 4096):
                raise ValueError()
            return ids
        except (ValueError, KeyError, TypeError):
            raise PermanentPollError(ERROR) from None

    def message(self, ident):
        valid_id(ident)
        url = BASE + "/messages/" + quote(ident, safe="") + "?" + urlencode({
            "format": "metadata",
            "metadataHeaders": ["From", "Subject", "Date"],
            "fields": "id,threadId,labelIds,internalDate,payload(headers)",
        }, doseq=True)
        return self._get(url, self._bearer, missing="message")

    def changed(self, cursor):
        """Gather bounded history delta; require all pages before any store write."""
        valid_history(cursor)
        token = None
        visited = set()
        changed = []
        seen = set()
        for _ in range(MAX_HISTORY_PAGES):
            query = {"startHistoryId": cursor, "maxResults": "100",
                     "historyTypes": ["messageAdded", "messageDeleted",
                                      "labelAdded", "labelRemoved"]}
            if token is not None:
                query["pageToken"] = token
            result = self._get(BASE + "/history?" + urlencode(query, doseq=True),
                               self._bearer, missing="history")
            try:
                history = result.get("history", [])
                if not isinstance(history, list) or len(history) > 100:
                    raise ValueError()
                for item in history:
                    if not isinstance(item, dict):
                        raise ValueError()
                    for field in ("messagesAdded", "messagesDeleted",
                                  "labelsAdded", "labelsRemoved"):
                        changes = item.get(field, [])
                        if not isinstance(changes, list) or len(changes) > 100:
                            raise ValueError()
                        for change in changes:
                            ident = valid_id(change["message"]["id"])
                            if ident not in seen:
                                changed.append(ident)
                                seen.add(ident)
                                if len(changed) > MAX_CHANGES:
                                    raise ValueError()
                nxt = result.get("nextPageToken")
                if nxt is None:
                    new_cursor = valid_history(result["historyId"])
                    if int(new_cursor) < int(cursor):
                        raise ValueError()
                    return changed, new_cursor
                if not isinstance(nxt, str) or not 1 <= len(nxt) <= 4096 or nxt in visited:
                    raise ValueError()
                visited.add(nxt)
                token = nxt
            except (KeyError, TypeError, ValueError):
                raise PermanentPollError(ERROR) from None
        raise PermanentPollError(ERROR)


def message_event(raw, account):
    """Project only message metadata; never retain snippet or RFC822 body."""
    try:
        ident = valid_id(raw["id"])
        thread = valid_id(raw["threadId"])
        label_ids = raw["labelIds"]
        if not isinstance(label_ids, list) or len(label_ids) > 100 or not all(
            isinstance(x, str) and 1 <= len(x) <= 128 for x in label_ids
        ):
            raise ValueError()
        if "INBOX" not in label_ids:
            return ident, None
        millis = raw["internalDate"]
        if not isinstance(millis, str) or not re.fullmatch(r"[0-9]{1,16}", millis):
            raise ValueError()
        instant = datetime.fromtimestamp(int(millis) / 1000, timezone.utc)
        headers = raw["payload"]["headers"]
        if not isinstance(headers, list) or len(headers) > 100:
            raise ValueError()
        fields = {}
        for entry in headers:
            key, value = entry["name"], entry["value"]
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError()
            if key.casefold() in ("from", "subject"):
                if key.casefold() in fields:
                    raise ValueError()
                fields[key.casefold()] = clean(value, 512)
        event = Event(SERVICE, account, "v1:" + sha256(ident.encode()).hexdigest(),
                      "gmail.message", instant,
                      "thread:" + sha256(thread.encode()).hexdigest(),
                      fields.get("subject") or "(no subject)", "",
                      {"from": fields.get("from", ""), "unread": str("UNREAD" in label_ids).lower(),
                       "provenance": "gmail-metadata"})
        return ident, event
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        raise PermanentPollError(ERROR) from None


def sync_gmail(store, reader, expected_email):
    """Atomic account-scoped snapshot/delta with stable identity and cursor.

    A history 404 re-baselines only the newest 75 messages. Old stored entries
    remain untouched to avoid falsely treating a partial window as a full inbox.
    """
    account = account_for(expected_email)
    actual, profile_cursor = reader.profile()
    if actual.casefold() != expected_email.casefold():
        raise AuthenticationPollError("Gmail account does not match private allowlist")
    previous = store.cursor(SERVICE, account)
    initial = previous is None
    rebased = False
    if initial:
        ids, next_cursor = reader.recent(), profile_cursor
    else:
        try:
            ids, next_cursor = reader.changed(previous)
        except HistoryExpired:
            ids, next_cursor = reader.recent(), profile_cursor
            rebased = True
    changes = {}
    for ident in ids:
        try:
            raw = reader.message(ident)
            key, event = message_event(raw, account)
            if key != ident:
                raise PermanentPollError(ERROR)
        except MessageGone:
            event = None
        changes["v1:" + sha256(ident.encode()).hexdigest()] = event
    added = updated = removed = 0
    with store.db:
        for key, event in changes.items():
            row = store.db.execute(
                "SELECT data FROM events WHERE service=? AND account=? AND external_id=?",
                (SERVICE, account, key)).fetchone()
            if event is None:
                if row is not None:
                    store.db.execute("DELETE FROM event_states WHERE service=? AND account=? AND external_id=?",
                                     (SERVICE, account, key))
                    store.db.execute("DELETE FROM events WHERE service=? AND account=? AND external_id=?",
                                     (SERVICE, account, key))
                    removed += 1
            else:
                payload = asdict(event)
                payload["timestamp"] = event.timestamp.isoformat()
                data = encode(payload)
                if row is None:
                    store.db.execute("INSERT INTO events VALUES (?, ?, ?, ?)",
                                     (SERVICE, account, key, data))
                    added += 1
                elif row["data"] != data:
                    store.db.execute(
                        "UPDATE events SET data=? WHERE service=? AND account=? AND external_id=?",
                        (data, SERVICE, account, key))
                    updated += 1
        store.db.execute("INSERT OR REPLACE INTO cursors VALUES (?, ?, ?)",
                         (SERVICE, account, next_cursor))
        result = {"initial": initial, "rebased": rebased,
                  "added": added, "updated": updated, "removed": removed}
        store._audit("gmail-metadata-sync", account, encode(result))
    return account, result
