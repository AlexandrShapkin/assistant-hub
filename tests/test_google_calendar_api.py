"""Google Calendar read-only HTTPS API and private allowlist: all offline."""
from contextlib import closing
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urlsplit

from assistant_hub.core.store import Store
from assistant_hub.google_calendar_api import (
    BASE, GoogleCalendarReader, private_calendar_allowlist,
)
from assistant_hub.google_oauth import (
    write_private,
)
from assistant_hub.google_calendar_mirror import sync_google_calendar, account_for

ID = "synthetic.calendar@example.invalid"
BEARER = "synthetic-readonly-access-token"


def item():
    return {"id": "synthetic-event-01", "summary": "Synthetic seminar",
            "start": {"dateTime": "2026-10-19T10:00:00+07:00"},
            "end": {"dateTime": "2026-10-19T11:30:00+07:00"}}


class GoogleCalendarAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.allowlist = self.root / "calendar-allowlist.json"
        self.db = self.root / "data.sqlite3"

    def put_allowlist(self, entries):
        write_private(self.allowlist, json.dumps({"calendars": entries}).encode())

    def test_allowlist_enforces_owner_private_and_exact_schema(self):
        self.put_allowlist([{"id": ID, "timezone": "Asia/Barnaul"}])
        self.assertEqual(private_calendar_allowlist(self.allowlist), ((ID, "Asia/Barnaul"),))
        os.chmod(self.allowlist, 0o644)
        with self.assertRaises(ValueError):
            private_calendar_allowlist(self.allowlist)
        os.chmod(self.allowlist, 0o600)
        for entries in (
            [], [{"id": ID, "timezone": "Asia/Barnaul"}] * 2,
            [{"id": "invalid\ncalendar", "timezone": "Asia/Barnaul"}],
            [{"id": ID, "timezone": 11}],
            [{"id": ID, "timezone": "bad\\nzone"}],
            [{"id": ID, "timezone": "Asia/Barnaul", "extra": "bad"}],
        ):
            with self.subTest(entries=entries):
                self.put_allowlist(entries)
                with self.assertRaises(ValueError):
                    private_calendar_allowlist(self.allowlist)
        self.put_allowlist([{"id": ID, "timezone": "Asia/Barnaul"}])
        os.chmod(self.root, 0o755)
        with self.assertRaises(ValueError):
            private_calendar_allowlist(self.allowlist)

    def test_read_only_events_api_header_not_query_and_pagination(self):
        calls = []
        def fake_get(url, token):
            calls.append((url, token))
            if len(calls) == 1:
                return {"items": [item()], "nextPageToken": "page-2"}
            return {"items": [], "nextSyncToken": "sync-final"}
        client = GoogleCalendarReader(BEARER, get_json=fake_get)
        with closing(Store(self.db)) as store:
            result = sync_google_calendar(store, ID, client.event_page)
            self.assertEqual(result["added"], 1)
            self.assertEqual(store.inbox()[0]["title"], "Synthetic seminar")
            self.assertEqual(store.cursor("google-calendar", account_for(ID)), "sync-final")
        self.assertEqual(len(calls), 2)
        for url, token in calls:
            self.assertEqual(urlsplit(url).hostname, "www.googleapis.com")
            self.assertEqual(token, BEARER)
            self.assertNotIn(BEARER, url)
            self.assertNotIn("access_token", url)
            self.assertIn("/calendars/" + quote(ID, safe="") + "/events", url)
            params = parse_qs(urlsplit(url).query)
            self.assertEqual(params["showDeleted"], ["true"])
            self.assertEqual(params["singleEvents"], ["true"])
            self.assertNotIn("timeMin", params)
        self.assertEqual(parse_qs(urlsplit(calls[1][0]).query)["pageToken"], ["page-2"])

    def test_sync_token_uses_compatible_parameters_and_cancellation(self):
        calls = []
        def fake_get(url, token):
            calls.append(url)
            params = parse_qs(urlsplit(url).query)
            if "syncToken" not in params:
                return {"items": [item()], "nextSyncToken": "old"}
            return {"items": [{"id": "synthetic-event-01", "status": "cancelled"}],
                    "nextSyncToken": "next"}
        reader = GoogleCalendarReader(BEARER, get_json=fake_get)
        with closing(Store(self.db)) as store:
            self.assertEqual(sync_google_calendar(store, ID, reader.event_page)["added"], 1)
            self.assertEqual(sync_google_calendar(store, ID, reader.event_page)["removed"], 1)
            self.assertEqual(len(store.inbox()), 0)
        second = parse_qs(urlsplit(calls[1]).query)
        self.assertEqual(second["syncToken"], ["old"])
        self.assertEqual(second["showDeleted"], ["true"])
        self.assertNotIn("timeMin", second)
        self.assertNotIn("orderBy", second)

    def test_http_transport_fixed_host_header_and_error_mapping(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        from assistant_hub.google_calendar_api import _request_json
        from assistant_hub.google_calendar_mirror import GoogleSyncTokenExpired
        from assistant_hub.core.contracts import (AuthenticationPollError,
                                                  RateLimitPollError, TransientPollError)
        class Response:
            status = 200
            class Headers:
                def get_content_type(self): return "application/json"
            headers = Headers()
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, count): return b'{"items":[],"nextSyncToken":"fake"}'
        captured = []
        class Opener:
            error_code = None
            def open(self, request, timeout):
                captured.append(request)
                if self.error_code is not None:
                    raise HTTPError(request.full_url, self.error_code, "untrusted body", {}, None)
                return Response()
        fake = Opener()
        with patch("assistant_hub.google_calendar_api.build_opener", return_value=fake):
            obj = _request_json(BASE + "/users/me/calendarList?maxResults=100", BEARER)
            self.assertEqual(obj["items"], [])
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0].get_method(), "GET")
            self.assertEqual(captured[0].get_header("Authorization"), "Bearer " + BEARER)
            self.assertNotIn(BEARER, captured[0].full_url)
            for code, category in ((410, GoogleSyncTokenExpired),
                                   (401, AuthenticationPollError), (403, AuthenticationPollError),
                                   (429, RateLimitPollError), (503, TransientPollError),
                                   (302, ValueError)):
                with self.subTest(code=code):
                    fake.error_code = code
                    with self.assertRaises(category) as err:
                        _request_json(BASE + "/users/me/calendarList", BEARER)
                    self.assertNotIn("untrusted body", str(err.exception))
            with self.assertRaises(ValueError):
                _request_json("https://unauthorized.example.org/anything", BEARER)

    def test_calendar_list_read_only_and_exact_bounds(self):
        observed = []
        def transport(url, token):
            observed.append((url, token))
            return {"items": [{"id": ID, "summary": "Fake personal", "timeZone": "Asia/Barnaul",
                               "accessRole": "owner"}]}
        data = GoogleCalendarReader(BEARER, get_json=transport).calendar_list()
        self.assertEqual(data, [{"id": ID, "title": "Fake personal",
                                 "timezone": "Asia/Barnaul", "access_role": "owner"}])
        self.assertIn("/users/me/calendarList?", observed[0][0])
        with self.assertRaises(ValueError):
            GoogleCalendarReader(BEARER, get_json=lambda *a: {
                "items": [{"id": ID}, {"id": ID}]}).calendar_list()
        with self.assertRaises(ValueError):
            GoogleCalendarReader(BEARER, get_json=lambda *a: {"items": None}).calendar_list()


if __name__ == "__main__":
    unittest.main()
