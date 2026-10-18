"""Offline, read-only Google Calendar events projection. No OAuth or network access.

The caller must supply already authorized, bounded API pages. Every page and
event is validated BEFORE a single SQLite transaction changes any data.
"""
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from hashlib import sha256
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .core.contracts import Event
from .core.store import encode

SERVICE = "google-calendar"
MAX_PAGES = 12
MAX_EVENTS = 1500
MAX_TOKEN = 4096
MAX_CALENDAR_ID = 512
MAX_TEXT = 2048
_ACCOUNT_RE = re.compile(r"[\x21-\x7e]{1,512}\Z")


def account_for(calendar_id: str) -> str:
    """A calendar ID is private owner configuration, never directly a UI account key."""
    if not isinstance(calendar_id, str) or not _ACCOUNT_RE.fullmatch(calendar_id):
        raise ValueError("invalid calendar identity")
    return "gcal:" + sha256(calendar_id.encode("utf-8")).hexdigest()


def sanitized(value, limit=MAX_TEXT) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > 16384:
        raise ValueError("invalid calendar text")
    # Treat provider text as inert display data, never markup or commands.
    return "".join(ch for ch in value if ch in "\n\t" or
                   (ord(ch) >= 32 and not 127 <= ord(ch) <= 159 and
                    ch not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))[:limit]


def _instant(value: dict, fallback_zone: str):
    if not isinstance(value, dict):
        raise ValueError("invalid event time")
    if "dateTime" in value:
        raw = value["dateTime"]
        if not isinstance(raw, str) or len(raw) > 45:
            raise ValueError("invalid datetime")
        try:
            result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("invalid datetime") from None
        if result.tzinfo is None:
            raise ValueError("Google event time requires an offset")
        return result.astimezone(timezone.utc), False
    if set(value) == {"date"}:
        raw = value["date"]
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise ValueError("invalid all-day date")
        try:
            tz = ZoneInfo(fallback_zone)
            day = date.fromisoformat(raw)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("invalid calendar timezone/date") from None
        return datetime.combine(day, time(), tz).astimezone(timezone.utc), True
    raise ValueError("unsupported event start")


def _convert_event(raw: dict, account: str, fallback_zone: str) -> tuple[str, Event | None]:
    if not isinstance(raw, dict):
        raise ValueError("invalid Google event")
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not _ACCOUNT_RE.fullmatch(identifier):
        raise ValueError("invalid Google event ID")
    hashed = "v1:" + sha256(identifier.encode("utf-8")).hexdigest()
    status = raw.get("status", "confirmed")
    if status not in ("confirmed", "tentative", "cancelled"):
        raise ValueError("invalid Google event status")
    if status == "cancelled":
        return hashed, None
    start, all_day = _instant(raw.get("start"), fallback_zone)
    end, end_all_day = _instant(raw.get("end"), fallback_zone)
    if all_day != end_all_day or not start < end or (end - start).days > 366:
        raise ValueError("invalid Google event duration")
    recurrence_id = raw.get("recurringEventId")
    if recurrence_id is not None and (
        not isinstance(recurrence_id, str) or not _ACCOUNT_RE.fullmatch(recurrence_id)
    ):
        raise ValueError("invalid recurring series")
    title = sanitized(raw.get("summary", ""), 512) or "(untitled)"
    body = sanitized(raw.get("description", ""))
    location = sanitized(raw.get("location", ""), 512)
    attributes = {
        "location": location,
        "all_day": "true" if all_day else "false",
        "timezone": fallback_zone,
        "status": status,
        "provenance": "google-calendar",
        "recurring": "true" if recurrence_id is not None else "false",
    }
    return hashed, Event(SERVICE, account, hashed, "google.event", start, account, title,
                         body, attributes)


def normalized_pages(calendar_id: str, pages: tuple, zone: str = "Asia/Barnaul"):
    """Validate all pages before database mutation. Page fetch is elsewhere."""
    account = account_for(calendar_id)
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("invalid calendar timezone") from None
    if not isinstance(pages, tuple) or not 1 <= len(pages) <= MAX_PAGES:
        raise ValueError("invalid Google page count")
    seen = set()
    result = {}
    next_token = None
    for position, page in enumerate(pages):
        if not isinstance(page, dict) or type(page.get("items")) is not list:
            raise ValueError("invalid Google page")
        if len(page["items"]) > 250 or len(seen) + len(page["items"]) > MAX_EVENTS:
            raise ValueError("too many Google events")
        if position < len(pages) - 1:
            if ("nextSyncToken" in page or not isinstance(page.get("nextPageToken"), str)
                    or not page["nextPageToken"]):
                raise ValueError("invalid partial Google page")
        else:
            if page.get("nextPageToken") or not isinstance(page.get("nextSyncToken"), str):
                raise ValueError("Google sync needs final sync token")
            next_token = page["nextSyncToken"]
            if not 1 <= len(next_token) <= MAX_TOKEN or any(ord(x) < 33 for x in next_token):
                raise ValueError("invalid Google sync token")
        for row in page["items"]:
            key, event = _convert_event(row, account, zone)
            if key in seen:
                raise ValueError("duplicate Google event across pages")
            seen.add(key)
            result[key] = event
    return account, result, next_token


def apply_google_pages(store, calendar_id: str, pages: tuple, *, initial: bool, zone="Asia/Barnaul"):
    """Atomic initial snapshot or incremental delta with preserved local statuses.

    This is not a live connector and never performs network activity.
    """
    if type(initial) is not bool:
        raise ValueError("sync mode required")
    account, events, token = normalized_pages(calendar_id, pages, zone)
    if initial is False and store.cursor(SERVICE, account) is None:
        raise ValueError("incremental sync requires full baseline")
    added = updated = removed = 0
    with store.db:
        before_rows = store.db.execute(
            "SELECT external_id, data FROM events WHERE service=? AND account=?",
            (SERVICE, account)).fetchall()
        previous = {r["external_id"]: r["data"] for r in before_rows}
        for key, event in events.items():
            if event is None:
                if key in previous:
                    store.db.execute(
                        "DELETE FROM event_states WHERE service=? AND account=? AND external_id=?",
                        (SERVICE, account, key))
                    store.db.execute(
                        "DELETE FROM events WHERE service=? AND account=? AND external_id=?",
                        (SERVICE, account, key))
                    removed += 1
                continue
            payload = asdict(event)
            payload["timestamp"] = event.timestamp.isoformat()
            data = encode(payload)
            if key not in previous:
                store.db.execute("INSERT INTO events VALUES (?, ?, ?, ?)",
                                 (SERVICE, account, key, data))
                added += 1
            elif data != previous[key]:
                store.db.execute(
                    "UPDATE events SET data=? WHERE service=? AND account=? AND external_id=?",
                    (data, SERVICE, account, key))
                updated += 1
        if initial:
            for key in previous.keys() - events.keys():
                store.db.execute(
                    "DELETE FROM event_states WHERE service=? AND account=? AND external_id=?",
                    (SERVICE, account, key))
                store.db.execute(
                    "DELETE FROM events WHERE service=? AND account=? AND external_id=?",
                    (SERVICE, account, key))
                removed += 1
        store.db.execute("INSERT OR REPLACE INTO cursors VALUES (?, ?, ?)",
                         (SERVICE, account, token))
        result = {"initial": initial, "added": added, "updated": updated, "removed": removed}
        # Do not store raw Google calendar IDs or sync tokens in the audit trail.
        store._audit("google-sync", account, encode(result))
    return result


class GoogleSyncTokenExpired(Exception):
    """Caller-mapped HTTP 410; the original token must not be reused."""


def fetch_google_pages(fetch_page, calendar_id: str, sync_token: str | None = None) -> tuple:
    """Fetch paginated API pages with a caller-supplied authorized transport.

    This function does not implement OAuth, issue requests by itself, or log
    tokens/URLs. The transport receives exact (calendar_id, sync_token, page).
    """
    account_for(calendar_id)
    if sync_token is not None and (
        not isinstance(sync_token, str) or not 1 <= len(sync_token) <= MAX_TOKEN
    ):
        raise ValueError("invalid prior Google sync cursor")
    if not callable(fetch_page):
        raise TypeError("authorized page transport required")
    pages, page_token, visited = [], None, set()
    for _ in range(MAX_PAGES):
        raw = fetch_page(calendar_id, sync_token, page_token)
        if not isinstance(raw, dict):
            raise ValueError("invalid Google API page")
        pages.append(raw)
        page_token = raw.get("nextPageToken")
        if page_token is None:
            # No source content committed until all pages are validated.
            normalized_pages(calendar_id, tuple(pages))
            return tuple(pages)
        if (not isinstance(page_token, str) or len(page_token) > MAX_TOKEN
                or not page_token or page_token in visited):
            raise ValueError("invalid Google pagination token")
        visited.add(page_token)
    raise ValueError("too many Google API pages")


def sync_google_calendar(store, calendar_id: str, fetch_page, *, zone="Asia/Barnaul"):
    """Initial/nextSyncToken read with safe HTTP 410 full replacement fallback.

    Requires explicit caller authorization for each calendar. No event
    creation or updates on Google; writes only the local SQLite mirror.
    """
    account = account_for(calendar_id)
    previous = store.cursor(SERVICE, account)
    try:
        pages = fetch_google_pages(fetch_page, calendar_id, previous)
        initial = previous is None
    except GoogleSyncTokenExpired:
        if previous is None:
            raise
        pages = fetch_google_pages(fetch_page, calendar_id, None)
        initial = True
    # Caller-specified zone is validated in the second projection pass;
    # all source pages have already arrived before this transaction.
    return apply_google_pages(store, calendar_id, pages, initial=initial, zone=zone)
