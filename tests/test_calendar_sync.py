"""Offline optional subscription behavior with fake clock and HTTP: no URLs fetched."""
from contextlib import closing
from pathlib import Path
import os
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from assistant_hub.adapters.public_feed import FeedResponse
from assistant_hub.calendar_sync import CalendarSubscription, read_subscription_url, MIN_INTERVAL, MAX_INTERVAL
from assistant_hub.core.contracts import PermanentPollError, TransientPollError
from assistant_hub.core.store import Store
from tests.test_calendar_import import calendar, event

URL = "https://school-calendar.example.org/student/approved.ics"
FILE = calendar(event("fake-a", "Synthetic class"))
NEXT = calendar(event("fake-a", "Changed class"))


class Clock:
    def __init__(self): self.time = 0.0
    def __call__(self): return self.time
    def tick(self, seconds): self.time += seconds


class CalendarSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "hub.sqlite3"
        self.clock = Clock()
        self.calls = []
        self.results = []
        def fetch(url, headers, *, accept):
            self.calls.append((url, headers, accept))
            if not self.results:
                raise AssertionError("unexpected calendar request")
            item = self.results.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        self.worker = CalendarSubscription(self.db, URL, MIN_INTERVAL, threading.RLock(),
                                            transport=fetch, clock=self.clock)

    def response(self, raw, etag=None):
        return FeedResponse(200, "text/calendar; charset=utf-8", raw.encode(), etag, None)

    def test_opt_in_initial_wait_conditional_and_atomic_week_update(self):
        self.results = [self.response(FILE, '"one"'),
                        FeedResponse(304, '', b''),
                        self.response(NEXT, '"two"')]
        self.worker.run_due()
        self.assertEqual(self.calls, [])
        self.clock.tick(MIN_INTERVAL)
        self.worker.run_due()
        self.assertEqual(self.calls, [(URL, {}, "text/calendar")])
        with closing(Store(self.db)) as store:
            first = store.inbox()[0]
            self.assertEqual(first["attributes"]["provenance"], "subscription-ics")
            self.assertEqual(first["title"], "Synthetic class")
            self.assertEqual(len(store.calendar_weeks()), 1)
        self.clock.tick(MIN_INTERVAL)
        self.worker.run_due()
        self.assertEqual(self.calls[1], (URL, {"If-None-Match": '"one"'}, "text/calendar"))
        self.clock.tick(MIN_INTERVAL)
        self.worker.run_due()
        with closing(Store(self.db)) as store:
            self.assertEqual(len(store.inbox()), 1)
            self.assertEqual(store.inbox()[0]["title"], "Changed class")
            self.assertEqual(len([a for a in store.audit() if a["kind"] == "calendar-import"]), 2)
            self.assertEqual(store.calendar_weeks()[0]["count"], 1)
        self.assertEqual(self.worker.headers["If-None-Match"], '"two"')
        self.assertEqual(self.worker.failures, 0)

    def test_invalid_http_never_imports_and_backoff_caps(self):
        self.results = [
            FeedResponse(200, "text/html", b'<html>hello</html>'),
            FeedResponse(200, "text/calendar", b"broken"),
            FeedResponse(304, "", b""),
            self.response(FILE, 'bad\nheader'),
            self.response(FILE, '"good"'),
        ]
        for i in range(4):
            self.clock.time = self.worker.next_due
            self.worker.run_due()
            self.assertEqual(self.worker.failures, i + 1)
        self.assertFalse(self.worker.has_snapshot)
        with closing(Store(self.db)) as store:
            self.assertEqual(store.inbox(), [])
            self.assertEqual(store.calendar_weeks(), [])
        self.clock.time = self.worker.next_due
        self.worker.run_due()
        self.assertEqual(self.worker.failures, 0)
        self.assertTrue(self.worker.has_snapshot)
        with closing(Store(self.db)) as store:
            self.assertEqual(len(store.inbox()), 1)

    def test_transient_backoff_permanent_suspend_and_cancel(self):
        self.results = [TransientPollError("fictional connection error")]
        self.clock.tick(MIN_INTERVAL)
        self.worker.run_due()
        self.assertEqual(self.worker.failures, 1)
        self.assertEqual(self.worker.next_due, MIN_INTERVAL * 3)
        self.results = [PermanentPollError("fictional unsafe DNS")]
        self.clock.time = self.worker.next_due
        self.worker.run_due()
        self.assertEqual(self.worker.next_due, float("inf"))
        stop = threading.Event()
        stop.set()
        self.worker.run(stop)
        self.assertEqual(len(self.calls), 2)

    def test_interval_bounds_and_no_network_during_constructor(self):
        self.assertEqual(self.calls, [])
        for interval in (-1, 0, 899, 86401, True, 3600.0):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                CalendarSubscription(self.db, URL, interval, threading.RLock(), transport=lambda *a: None)
        with self.assertRaises(ValueError):
            CalendarSubscription(self.db, "http://localhost/calendar.ics", 900, threading.RLock())
        self.assertEqual(MAX_INTERVAL, 86400)

    def test_cli_requires_private_approved_url_file_and_explicit_interval(self):
        from assistant_hub.local_server import main
        urlfile = self.root / "subscription-url"
        urlfile.write_text(URL + "\n")
        os.chmod(urlfile, 0o600)
        base = ["serve", "--verifier", str(self.root / "owner.json"),
                "--db", str(self.db)]
        invalid = (
            base + ["--calendar-url-file", str(urlfile)],
            base + ["--calendar-interval", "900"],
            base + ["--calendar-url-file", str(urlfile), "--calendar-interval", "899"],
            base + ["--calendar-url-file", str(urlfile), "--calendar-interval", "86401"],
        )
        with patch("assistant_hub.local_server.LocalServer") as server:
            for argv in invalid:
                with self.subTest(argv=argv), self.assertRaises(SystemExit):
                    main(argv)
            server.assert_not_called()
        with patch("assistant_hub.local_server.LocalServer") as server, \
             patch("assistant_hub.local_server.CalendarSubscription") as subscription:
            main(base + ["--calendar-url-file", str(urlfile), "--calendar-interval", "900"])
            self.assertEqual(server.call_count, 1)
            args = subscription.call_args.args
            self.assertEqual(args[1:3], (URL, 900))
            self.assertEqual(subscription.call_count, 1)
            subscription.return_value.run.assert_called_once()

    def test_private_url_file_and_untrusted_paths(self):
        # Do not put private URLs or group identifiers in Git.
        path = self.root / 'source.txt'
        path.write_text(URL + '\n')
        os.chmod(path, 0o600)
        self.assertEqual(read_subscription_url(path), URL)
        os.chmod(path, 0o644)
        with self.assertRaises(ValueError):
            read_subscription_url(path)
        os.chmod(path, 0o600)
        link = self.root / 'link'
        link.symlink_to(path)
        with self.assertRaises(OSError):
            read_subscription_url(link)
        path.write_text('https://calendar.example.org/lesson.ics?token=secretvalue')
        with self.assertRaises(ValueError):
            read_subscription_url(path)
        path.write_text("http://127.0.0.1/private.ics")
        with self.assertRaises(ValueError):
            read_subscription_url(path)
        path.write_text(URL + '\n' + URL)
        with self.assertRaises(ValueError):
            read_subscription_url(path)
        os.chmod(self.root, 0o755)
        with self.assertRaises(ValueError):
            read_subscription_url(path)


if __name__ == "__main__":
    unittest.main()
