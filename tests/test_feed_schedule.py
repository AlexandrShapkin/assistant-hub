"""Offline multi-source feed and opt-in schedule tests; no network traffic."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock

from assistant_hub.adapters.public_feed import PublicFeedCatalog, FeedResponse
from assistant_hub.core.contracts import PermanentPollError, TransientPollError
from assistant_hub.core.hub import Hub
from assistant_hub.core.registry import Binding, Registry
from assistant_hub.core.store import Store
from assistant_hub.feed_schedule import FeedSchedule, MIN_INTERVAL, MAX_INTERVAL

URLS = ("https://feeds.python.org/a", "https://feeds.python.org/b",
        "https://feeds.python.org/c")


def response(url):
    name = url.rsplit("/", 1)[-1]
    data = {"version": "https://jsonfeed.org/version/1.1",
            "items": [{"id": name, "title": name, "content_text": "Synthetic " + name,
                       "url": "https://feeds.python.org/item/" + name}]}
    return FeedResponse(200, "application/feed+json", json.dumps(data).encode(), '"tag-' + name + '"', None)


class FakeClock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class CatalogTests(unittest.TestCase):
    def test_multi_source_cursors_dedup_and_no_erase_when_disabled(self):
        calls = []
        def transport(url, headers):
            calls.append((url, dict(headers)))
            if headers: return FeedResponse(304, "", b"")
            return response(url)

        catalog = PublicFeedCatalog(URLS, transport)
        registry = Registry()
        registry.enable(catalog, tuple(Binding(a) for a in catalog.accounts))
        with tempfile.TemporaryDirectory() as temp, closing(Store(Path(temp) / "db")) as store:
            hub = Hub(registry, store)
            for account in catalog.accounts:
                self.assertEqual(hub.collect("public-feed", account), 1)
            self.assertEqual(len(store.inbox()), 3)
            for account in catalog.accounts:
                self.assertEqual(hub.collect("public-feed", account), 0)
                self.assertIn('"etag"', store.cursor("public-feed", account))
            self.assertEqual(len(store.audit()), 6)
            self.assertEqual(len({e["account_id"] for e in store.inbox()}), 3)
            self.assertEqual([h for _, h in calls[:3]], [{}, {}, {}])
            self.assertEqual([h for _, h in calls[3:]],
                             [{"If-None-Match": '"tag-' + n + '"'} for n in ("a", "b", "c")])
            # Removing a source from the startup allowlist never deletes past events.
            subset = PublicFeedCatalog(URLS[:2], transport)
            new_registry = Registry()
            new_registry.enable(subset, tuple(Binding(a) for a in subset.accounts))
            self.assertEqual(len(store.inbox()), 3)
            self.assertIsNotNone(store.cursor("public-feed", catalog.accounts[2]))
            with self.assertRaises(ValueError):
                Hub(new_registry, store).collect("public-feed", catalog.accounts[2])

    def test_bound_and_identity(self):
        for urls in ((), URLS * 3, (URLS[0], URLS[0]),
                     (URLS[0], "https://FEEDS.PYTHON.ORG:443/a")):
            with self.subTest(urls=urls), self.assertRaises(ValueError):
                PublicFeedCatalog(urls)
        catalog = PublicFeedCatalog(URLS)
        self.assertEqual(catalog.accounts, PublicFeedCatalog(URLS[::-1]).accounts[::-1])
        with self.assertRaises(PermanentPollError):
            catalog.poll("unknown", None)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "hub.sqlite3"
        self.clock = FakeClock()
        self.calls = []
        self.results = {}
        def transport(url, headers):
            self.calls.append((url, dict(headers)))
            results = self.results.get(url, [])
            if results:
                result = results.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result
            return response(url)

        self.catalog = PublicFeedCatalog(URLS, transport)
        self.registry = Registry()
        self.registry.enable(self.catalog, tuple(Binding(a) for a in self.catalog.accounts))
        self.lock = threading.RLock()
        self.scheduler = FeedSchedule(self.registry, self.db, self.catalog.accounts,
                                      MIN_INTERVAL, self.lock, clock=self.clock)

    def test_initial_delay_rate_limit_and_per_feed_cursor(self):
        self.scheduler.run_due()
        self.assertEqual(self.calls, [])
        self.clock.advance(MIN_INTERVAL)
        self.scheduler.run_due()
        self.assertEqual(len(self.calls), 3)
        self.scheduler.run_due()
        self.assertEqual(len(self.calls), 3)
        with closing(Store(self.db)) as store:
            self.assertEqual(len(store.inbox()), 3)
            self.assertEqual(len(store.audit()), 3)
            self.assertEqual(len({store.cursor("public-feed", a) for a in self.catalog.accounts}), 3)
        self.clock.advance(MIN_INTERVAL)
        self.scheduler.run_due()
        self.assertEqual(len(self.calls), 6)
        self.assertEqual([c[1] for c in self.calls[3:]],
                         [{"If-None-Match": '"tag-' + n + '"'} for n in ("a", "b", "c")])
        with closing(Store(self.db)) as store:
            self.assertEqual(len(store.inbox()), 3)  # no duplicate events

    def test_independent_backoff_and_permanent_suspend(self):
        self.results[URLS[0]] = [TransientPollError("fake timeout"), response(URLS[0])]
        self.results[URLS[1]] = [PermanentPollError("unsafe DNS answer")]
        self.clock.advance(MIN_INTERVAL)
        self.scheduler.run_due()
        a, b, c = self.catalog.accounts
        self.assertEqual(self.scheduler.failures[a], 1)
        self.assertEqual(self.scheduler.due[a], MIN_INTERVAL * 3)
        self.assertEqual(self.scheduler.due[b], float("inf"))
        self.assertEqual(self.scheduler.due[c], MIN_INTERVAL * 2)
        self.clock.advance(MIN_INTERVAL)
        self.scheduler.run_due()
        self.assertEqual([u for u, _ in self.calls].count(URLS[2]), 2)
        self.assertEqual([u for u, _ in self.calls].count(URLS[0]), 1)
        self.clock.advance(MIN_INTERVAL)
        self.scheduler.run_due()
        self.assertEqual([u for u, _ in self.calls].count(URLS[0]), 2)
        self.assertEqual([u for u, _ in self.calls].count(URLS[1]), 1)
        self.assertEqual(self.scheduler.failures[a], 0)
        with closing(Store(self.db)) as store:
            self.assertEqual(len(store.inbox()), 2)
            self.assertIsNone(store.cursor("public-feed", b))

    def test_unexpected_worker_exception_does_not_break_other_sources(self):
        self.results[URLS[1]] = [RuntimeError("untrusted provider text")]
        self.clock.advance(MIN_INTERVAL)
        self.scheduler.run_due()
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.scheduler.failures[self.catalog.accounts[1]], 1)
        with closing(Store(self.db)) as store:
            self.assertEqual(len(store.inbox()), 2)

    def test_exponential_capped_retry_and_recovery(self):
        self.results[URLS[0]] = [TransientPollError("timeout")] * 12
        self.clock.advance(MIN_INTERVAL)
        for i in range(12):
            due = self.scheduler.due[self.catalog.accounts[0]]
            self.clock.value = due
            self.scheduler.run_due()
            self.assertLessEqual(self.scheduler.due[self.catalog.accounts[0]] - due, MAX_INTERVAL)
        self.assertEqual(self.scheduler.failures[self.catalog.accounts[0]], 7)
        self.assertEqual(self.scheduler.due[self.catalog.accounts[0]] - self.clock(), MAX_INTERVAL)
        self.clock.value = self.scheduler.due[self.catalog.accounts[0]]
        self.scheduler.run_due()
        self.assertEqual(self.scheduler.failures[self.catalog.accounts[0]], 0)

    def test_serialized_with_owner_manual_collection(self):
        self.clock.advance(MIN_INTERVAL)
        entered = threading.Event()
        def collect():
            entered.set()
            self.scheduler.run_due()
        with self.lock:
            thread = threading.Thread(target=collect)
            thread.start()
            self.assertTrue(entered.wait(1))
            self.assertFalse(self.calls)  # worker cannot collect while owner holds lock
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.calls), 3)

    def test_disabled_until_start_and_cancelled_worker(self):
        self.assertFalse(self.calls)
        stopped = threading.Event()
        stopped.set()
        self.scheduler.run(stopped)
        self.assertEqual(self.calls, [])
        for args in ((899,), (86401,), (True,), (900.0,), (0,)):
            with self.subTest(interval=args[0]), self.assertRaises(ValueError):
                FeedSchedule(self.registry, self.db, self.catalog.accounts,
                             args[0], self.lock, clock=self.clock)
        with self.assertRaises(ValueError):
            FeedSchedule(self.registry, self.db, ("unknown",), MIN_INTERVAL, self.lock,
                         clock=self.clock)


if __name__ == "__main__":
    unittest.main()
