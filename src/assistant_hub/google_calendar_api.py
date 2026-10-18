"""Owner-invoked read-only Google Calendar API sync; disabled until explicit OAuth.

Only fixed HTTPS endpoints, query-bound pagination, bearer HTTP Authorization,
and an owner-selected private calendar allowlist. No Google mutations.
"""
from contextlib import closing
import json
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import build_opener, HTTPSHandler, ProxyHandler, Request

from .core.contracts import AuthenticationPollError, RateLimitPollError, TransientPollError
from .core.store import Store
from .google_calendar_mirror import (
    account_for, GoogleSyncTokenExpired, sync_google_calendar,
)
from .google_oauth import (
    NoRedirect, _unique, load_desktop_client, load_refresh_grant,
    read_private, refresh_access_token,
)

BASE = "https://www.googleapis.com/calendar/v3"
MAX_JSON_BYTES = 1024 * 1024
MAX_CALENDARS = 8
VALID_ZONE = re.compile(r"[A-Za-z][A-Za-z0-9_+./-]{1,99}\Z")


def private_calendar_allowlist(path):
    """Calendar choices from a separate 0600 file in an owner-owned 0700 dir."""
    try:
        obj = json.loads(read_private(path, max_bytes=8192).decode("utf-8"),
                         object_pairs_hook=_unique)
        if not isinstance(obj, dict) or set(obj) != {"calendars"}:
            raise ValueError()
        rows = obj["calendars"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CALENDARS:
            raise ValueError()
        result = []
        for record in rows:
            if not isinstance(record, dict) or set(record) != {"id", "timezone"}:
                raise ValueError()
            ident, zone = record["id"], record["timezone"]
            account_for(ident)
            if not isinstance(zone, str) or not VALID_ZONE.fullmatch(zone):
                raise ValueError()
            try:
                ZoneInfo(zone)
            except (ValueError, ZoneInfoNotFoundError, KeyError):
                raise ValueError() from None
            result.append((ident, zone))
        if len({id for id, _ in result}) != len(result):
            raise ValueError()
    except (UnicodeError, TypeError, KeyError, json.JSONDecodeError, ValueError):
        raise ValueError("invalid private Google Calendar allowlist") from None
    return tuple(result)


def _request_json(url, bearer):
    """No ambient proxy, no redirects; URL is fixed by GoogleCalendarReader."""
    if not isinstance(bearer, str) or not 8 <= len(bearer) <= 4096:
        raise ValueError("invalid Google bearer")
    if not url.startswith(BASE + "/"):
        raise ValueError("unexpected Google API endpoint")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                          NoRedirect())
    request = Request(url, method="GET", headers={
        "Authorization": "Bearer " + bearer, "Accept": "application/json",
        "User-Agent": "assistant-hub-readonly-calendar/1",
    })
    try:
        with opener.open(request, timeout=15) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError("unexpected Google API content")
            raw = response.read(MAX_JSON_BYTES + 1)
    except HTTPError as error:
        code = error.code
        error.close()
        if code == 410:
            raise GoogleSyncTokenExpired() from None
        if code in (401, 403):
            raise AuthenticationPollError("Google read authorization denied") from None
        if code == 429:
            raise RateLimitPollError("Google quota reached") from None
        if code in (408, 500, 502, 503, 504):
            raise TransientPollError("Google API temporarily unavailable") from None
        raise ValueError("Google read request failed") from None
    except (URLError, OSError, TimeoutError):
        raise TransientPollError("Google API temporarily unavailable") from None
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("oversized Google API response")
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(result, dict):
        raise ValueError("invalid Google API response")
    return result


class GoogleCalendarReader:
    """Explicit calendar selection and bounded Events API GETs, no write API."""

    def __init__(self, bearer, *, get_json=_request_json):
        if not isinstance(bearer, str) or not 8 <= len(bearer) <= 4096:
            raise ValueError("invalid Google access grant")
        if not callable(get_json):
            raise ValueError("Google API transport required")
        self._token = bearer
        self._get = get_json

    def event_page(self, calendar_id, sync_token, page_token):
        account_for(calendar_id)
        params = {"maxResults": "250", "singleEvents": "true", "showDeleted": "true"}
        if sync_token is not None:
            if not isinstance(sync_token, str) or not 1 <= len(sync_token) <= 4096:
                raise ValueError("invalid sync token")
            params["syncToken"] = sync_token
        if page_token is not None:
            if not isinstance(page_token, str) or not 1 <= len(page_token) <= 4096:
                raise ValueError("invalid page token")
            params["pageToken"] = page_token
        path = "/calendars/" + quote(calendar_id, safe="") + "/events"
        return self._get(BASE + path + "?" + urlencode(params), self._token)

    def calendar_list_page(self, page_token=None):
        params = {"maxResults": "100"}
        if page_token is not None:
            if not isinstance(page_token, str) or not 1 <= len(page_token) <= 4096:
                raise ValueError("invalid page token")
            params["pageToken"] = page_token
        return self._get(BASE + "/users/me/calendarList?" + urlencode(params), self._token)

    def calendar_list(self):
        seen, calendars = set(), []
        token = None
        for _ in range(5):
            page = self.calendar_list_page(token)
            items = page.get("items")
            if not isinstance(items, list) or len(items) > 100:
                raise ValueError("invalid Google calendar list")
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("invalid calendar list item")
                ident = item.get("id")
                account_for(ident)
                if ident in seen:
                    raise ValueError("repeated Google calendar ID")
                seen.add(ident)
                title, zone = item.get("summary", ""), item.get("timeZone", "")
                if (not isinstance(title, str) or len(title) > 2048 or
                        not isinstance(zone, str) or len(zone) > 100):
                    raise ValueError("invalid Google calendar metadata")
                calendars.append({"id": ident, "title": title, "timezone": zone,
                                  "access_role": item.get("accessRole", "")})
            token = page.get("nextPageToken")
            if token is None:
                return calendars
            if not isinstance(token, str) or not token or len(token) > 4096:
                raise ValueError("invalid calendar list page token")
        raise ValueError("calendar list too large")


def read_google_now(client_file, grant_file, db_file, allowlist_file):
    """One owner-triggered sync pass. No automatic service/poller registration."""
    client = load_desktop_client(client_file)
    load_refresh_grant(grant_file, client["client_id"])  # fail before any network use
    calendars = private_calendar_allowlist(allowlist_file)
    token = refresh_access_token(client, grant_file)
    reader = GoogleCalendarReader(token)
    outcomes = []
    db_path = Path(db_file)
    if not db_path.is_absolute() or not db_path.is_file():
        raise ValueError("existing absolute private database required")
    for ident, zone in calendars:
        with closing(Store(db_path)) as store:
            result = sync_google_calendar(
                store, ident, reader.event_page, zone=zone)
            outcomes.append((account_for(ident), result))
    return outcomes


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Explicit private read-only Google Calendar sync")
    parser.add_argument("--client", required=True, help="Google Desktop client JSON in private 0600 file")
    parser.add_argument("--tokens", required=True, help="private OAuth refresh grant file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list calendar names locally, no event syncing")
    group.add_argument("--sync", action="store_true", help="read an explicit private calendar allowlist into SQLite")
    parser.add_argument("--allowlist", help="private JSON list of selected Google calendars")
    parser.add_argument("--db", help="absolute private Assistant Hub SQLite path")
    args = parser.parse_args(argv)
    if args.sync and (not args.allowlist or not args.db or not Path(args.db).is_absolute()):
        parser.error("--sync requires --allowlist and absolute --db")
    try:
        client = load_desktop_client(args.client)
        if args.list:
            token = refresh_access_token(client, args.tokens)
            for entry in GoogleCalendarReader(token).calendar_list():
                print(entry["title"], "|", entry["id"], "|", entry["timezone"])
        else:
            for _, counts in read_google_now(args.client, args.tokens, args.db, args.allowlist):
                print("Google Calendar local read sync:", counts)
        return 0
    except (ValueError, OSError, AuthenticationPollError, RateLimitPollError,
            TransientPollError, GoogleSyncTokenExpired):
        parser.exit(1, "Google Calendar read failed; check authorization, permissions or source.\\n")


if __name__ == "__main__":
    raise SystemExit(main())
