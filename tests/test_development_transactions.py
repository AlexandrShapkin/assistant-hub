"""Cross-connection serialization tests for the owner-submitted development ledger.

These use fictional identifiers and independent SQLite connections. They do
not start an executor or send commands outside the test database.
"""
import contextlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4

from assistant_hub.core.store import Store
from assistant_hub.development import DevelopmentLedger


def report(**overrides):
    envelope = dict(protocol_version="1", message_id=str(uuid4()),
                    task_id="test-task", project="assistant-hub",
                    executor_id="test-agent", sequence="1", status="running",
                    issue="52", branch="test-branch", head_sha="a" * 40,
                    pr="unknown")
    return envelope | overrides


class DevelopmentTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.sqlite3"
        with contextlib.closing(Store(self.path)) as store:
            DevelopmentLedger(store, clock=lambda: 1000).report(report(), actor="owner")

    def tearDown(self):
        self.tmp.cleanup()

    def _race(self, callback):
        barrier = threading.Barrier(2)
        outcomes = []
        guard = threading.Lock()

        def delayed_clock():
            # The old code reads stale state before either first write.
            # BEGIN IMMEDIATE blocks the second writer until commit.
            try:
                barrier.wait(timeout=0.4)
            except threading.BrokenBarrierError:
                pass
            return 1001

        def worker():
            try:
                with contextlib.closing(Store(self.path)) as store:
                    ledger = DevelopmentLedger(store, clock=delayed_clock)
                    result = callback(ledger)
                outcome = "replay" if result.get("replayed") else "accepted"
            except ValueError:
                outcome = "rejected"
            except sqlite3.Error as exc:
                outcome = f"sqlite-error:{type(exc).__name__}"
            with guard:
                outcomes.append(outcome)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)
            self.assertFalse(thread.is_alive(), "SQLite writer did not terminate")
        return sorted(outcomes)

    def test_distinct_reports_same_sequence_only_one_commits(self):
        outcomes = self._race(lambda ledger: ledger.report(report(sequence="2"), actor="owner"))
        self.assertEqual(outcomes, ["accepted", "rejected"])
        with contextlib.closing(Store(self.path)) as store:
            self.assertEqual(store.db.execute(
                "SELECT sequence FROM development_tasks WHERE task_id='test-task'").fetchone()[0], 2)
            self.assertEqual(store.db.execute("SELECT count(*) FROM development_events").fetchone()[0], 2)
            self.assertEqual(store.db.execute("SELECT count(*) FROM audit").fetchone()[0], 2)

    def test_same_control_id_is_replayed_not_unique_constraint_error(self):
        message_id = str(uuid4())
        envelope = dict(message_id=message_id, task_id="test-task", action="pause")
        outcomes = self._race(lambda ledger: ledger.control(envelope, actor="owner"))
        self.assertEqual(outcomes, ["accepted", "replay"])
        with contextlib.closing(Store(self.path)) as store:
            self.assertEqual(store.db.execute("SELECT count(*) FROM development_events").fetchone()[0], 2)
            self.assertEqual(store.db.execute("SELECT count(*) FROM audit").fetchone()[0], 2)
