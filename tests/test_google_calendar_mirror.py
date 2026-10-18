"""Offline synthetic Google Calendar read-only projection tests."""
from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from assistant_hub.core.store import Store
from assistant_hub.google_calendar_mirror import (
    SERVICE, account_for, normalized_pages, apply_google_pages,
    sync_google_calendar, GoogleSyncTokenExpired, fetch_google_pages,
)


def row(id="id-one", summary="Fake class", status="confirmed"):
    return {"id": id, "summary": summary, "status": status,
            "start": {"dateTime": "2026-10-19T10:00:00+07:00"},
            "end": {"dateTime": "2026-10-19T11:30:00+07:00"},
            "location": "Synthetic room", "description": "Synthetic class details"}


def full(*items, token="opaque-full-token"):
    return ({"items": list(items), "nextSyncToken": token},)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'hub.db'
        self.calendar = "synthetic.calendar@example.invalid"
        self.account = account_for(self.calendar)

    def test_full_delta_updates_and_cancellations(self):
        with closing(Store(self.db)) as store:
            out = apply_google_pages(store, self.calendar, full(row(), row("two", "Fake meeting")),
                                     initial=True)
            self.assertEqual(out, {"initial": True, "added": 2, "updated": 0, "removed": 0})
            before = store.inbox()
            self.assertEqual(len(before), 2)
            self.assertEqual(store.cursor(SERVICE, self.account), "opaque-full-token")
            self.assertTrue(all(e["service_id"] == SERVICE for e in before))
            self.assertEqual(before[0]["attributes"]["location"], "Synthetic room")
            self.assertEqual(before[0]["timestamp"], "2026-10-19T03:00:00+00:00")
            self.assertNotIn(self.calendar, str(before))
            store.set_status(SERVICE, self.account, before[0]["external_id"], "done", "owner")
            delta = full(row(summary="Fake shifted class"), {"id": "two", "status": "cancelled"},
                         token="opaque-next-token")
            result = apply_google_pages(store, self.calendar, delta, initial=False)
            self.assertEqual((result["updated"], result["removed"]), (1, 1))
            self.assertEqual(len(store.inbox()), 1)
            self.assertEqual(store.inbox_with_status()[0]["status"], "done")
            self.assertEqual(store.inbox()[0]["title"], "Fake shifted class")
            self.assertEqual(store.cursor(SERVICE, self.account), "opaque-next-token")
            unchanged = apply_google_pages(store, self.calendar,
                                           full(row(summary="Fake shifted class"), token="later"),
                                           initial=False)
            self.assertEqual(unchanged["updated"], 0)
            self.assertEqual(len(store.inbox()), 1)
            self.assertEqual(len([a for a in store.audit() if a["kind"] == "google-sync"]), 3)

    def test_initial_full_replace_only_chosen_calendar(self):
        with closing(Store(self.db)) as store:
            apply_google_pages(store, self.calendar, full(row(), row("two")), initial=True)
            other = "other-cal@example.invalid"
            apply_google_pages(store, other, full(row("third")), initial=True)
            result = apply_google_pages(store, self.calendar, full(row("two")), initial=True)
            self.assertEqual(result["removed"], 1)
            self.assertEqual(len(store.inbox()), 2)
            self.assertEqual(len([e for e in store.inbox() if e["account_id"] == account_for(other)]), 1)

    def test_pagination_incremental_then_sync_token_expiry_recovers_safely(self):
        calls = []
        def initial_fetch(calendar, token, page):
            calls.append((calendar, token, page))
            if page is None:
                return {"items": [row("first")], "nextPageToken": "page-two"}
            return {"items": [row("second")], "nextSyncToken": "sync-initial"}
        with closing(Store(self.db)) as store:
            self.assertEqual(sync_google_calendar(store, self.calendar, initial_fetch)["added"], 2)
            self.assertEqual(calls, [(self.calendar, None, None),
                                     (self.calendar, None, "page-two")])
            self.assertEqual(store.cursor(SERVICE, self.account), "sync-initial")
            def delta(calendar, token, page):
                self.assertEqual(token, "sync-initial")
                self.assertIsNone(page)
                return {"items": [row("first", "Updated")],
                        "nextSyncToken": "sync-second"}
            self.assertEqual(sync_google_calendar(store, self.calendar, delta)["updated"], 1)
            self.assertEqual(len(store.inbox()), 2)
            def expired(calendar, token, page):
                if token is not None:
                    raise GoogleSyncTokenExpired()
                return {"items": [row("second")], "nextSyncToken": "new-baseline"}
            result = sync_google_calendar(store, self.calendar, expired)
            self.assertEqual(result["removed"], 1)
            self.assertEqual(len(store.inbox()), 1)
            self.assertEqual(store.cursor(SERVICE, self.account), "new-baseline")

    def test_partial_fetch_or_repeated_page_cannot_write(self):
        with closing(Store(self.db)) as store:
            sync_google_calendar(store, self.calendar,
                                 lambda *args: {"items": [row()], "nextSyncToken": "initial"})
            before = (store.inbox(), store.cursor(SERVICE, self.account), store.audit())
            cases = [
                lambda *args: {"items": [row("bad")], "nextPageToken": "repeat"},
                lambda *args: {"items": [row("bad")], "nextPageToken": "z" * 4097},
                lambda *args: {"items": [row("bad")], "nextPageToken": 123},
                lambda *args: None,
            ]
            for fake in cases:
                with self.subTest(index=str(fake)), self.assertRaises(ValueError):
                    sync_google_calendar(store, self.calendar, fake)
                self.assertEqual(before, (store.inbox(), store.cursor(SERVICE, self.account), store.audit()))
            with self.assertRaises(GoogleSyncTokenExpired):
                fetch_google_pages(lambda *args: (_ for _ in ()).throw(
                    GoogleSyncTokenExpired()), self.calendar, None)

    def test_all_day_and_recurring_instances(self):
        a = row("instance-a")
        a.update(recurringEventId="recurring-series-id",
                 originalStartTime={"dateTime": "2026-10-19T10:00:00+07:00"})
        b = {"id": "all-day-event", "summary": "Fake vacation",
             "start": {"date": "2026-10-20"}, "end": {"date": "2026-10-22"}}
        account, events, token = normalized_pages(self.calendar, full(a, b))
        self.assertEqual(account, self.account)
        self.assertEqual(len(events), 2)
        self.assertEqual(token, "opaque-full-token")
        self.assertEqual(sorted(e.attributes["all_day"] for e in events.values()), ["false", "true"])
        self.assertEqual(next(e for e in events.values() if e.title == "Fake vacation").timestamp.isoformat(),
                         "2026-10-19T17:00:00+00:00")
        self.assertEqual(next(e for e in events.values() if e.title == "Fake class").attributes["recurring"], "true")

    def test_pages_must_be_complete_before_transaction(self):
        first = {"items": [row("first")], "nextPageToken": "page2"}
        final = {"items": [row("second")], "nextSyncToken": "final-token"}
        with closing(Store(self.db)) as store:
            self.assertEqual(apply_google_pages(store, self.calendar, (first, final), initial=True)["added"], 2)
            before = (store.inbox(), store.cursor(SERVICE, self.account), store.audit())
            invalid = [
                (first,),  # page token but no terminal sync token
                ({"items": [row()], "nextSyncToken": "no", "nextPageToken": "p"},),
                (first, {"items": [row("first")], "nextSyncToken": "dup"}),
                ({"items": [row("new")], "nextSyncToken": ""},),
                ({"items": [row("new")], "nextSyncToken": "\nmalicious"},),
                ({"items": [row("new")], "nextSyncToken": 3},),
                ({"items": [row("new")], "nextSyncToken": "token", "nextPageToken": "still-paged"},),
                ({"items": [row("new")]},),
                ({"items": [row("new")], "nextSyncToken": "x"} for _ in range(13)),
            ]
            for fixture in invalid:
                with self.subTest(fixture=str(fixture)[:55]), self.assertRaises(ValueError):
                    apply_google_pages(store, self.calendar, fixture, initial=False)
                self.assertEqual(before, (store.inbox(), store.cursor(SERVICE, self.account), store.audit()))

    def test_bad_events_and_no_partial_records(self):
        good = row()
        invalid = [
            {"id": ""}, {"id": "fake", "status": "unknown"},
            dict(good, id="with\nnewline"), dict(good, start={"dateTime": "2026-10-19T10:00:00"}),
            dict(good, start={"date": "2026-10-20"}, end={"dateTime": "2026-10-20T13:00:00+07:00"}),
            dict(good, end={"dateTime": "2026-10-19T08:00:00+07:00"}),
            dict(good, summary=42),
            dict(good, recurringEventId="bad\tseries"),
        ]
        with closing(Store(self.db)) as store:
            for item in invalid:
                with self.subTest(item=item), self.assertRaises(ValueError):
                    apply_google_pages(store, self.calendar, full(good, item), initial=True)
                self.assertEqual(store.inbox(), [])
                self.assertIsNone(store.cursor(SERVICE, self.account))
            with self.assertRaises(ValueError):
                apply_google_pages(store, self.calendar, full(good), initial=False)

    def test_rollback_on_sqlite_failure(self):
        with closing(Store(self.db)) as store:
            apply_google_pages(store, self.calendar, full(row()), initial=True)
            before = (store.inbox(), store.cursor(SERVICE, self.account), store.audit())
            store.db.execute("""CREATE TRIGGER refuse_provider_writes BEFORE UPDATE ON events
                                BEGIN SELECT RAISE(ABORT, 'synthetic error'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                apply_google_pages(store, self.calendar,
                                   full(row(summary="Different"), token="new-token"), initial=False)
            self.assertEqual(before, (store.inbox(), store.cursor(SERVICE, self.account), store.audit()))

    def test_limits_and_identity(self):
        for name in ("", "with space", "a\nb", "a" * 513, None):
            with self.assertRaises(ValueError):
                account_for(name)
        with self.assertRaises(ValueError):
            normalized_pages(self.calendar, ({"items": [row(str(i)) for i in range(251)],
                                               "nextSyncToken": "t"},))
        with self.assertRaises(ValueError):
            normalized_pages(self.calendar, full(row()), "Bogus/Timezone")
        self.assertEqual(account_for(self.calendar), account_for(self.calendar))


if __name__ == "__main__":
    unittest.main()
