import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from assistant_hub.core.assignments import AssignmentLedger
from assistant_hub.core.store import Store


class AssignmentLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "hub.db"
        self.store = Store(self.path)
        self.ledger = AssignmentLedger(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def event(self, seq, kind, message_id=None, generation=1):
        return self.ledger.record_event(
            "task", message_id or str(uuid4()), seq, generation, kind)

    def test_idempotent_assignment_and_conflicts(self):
        self.assertTrue(self.ledger.assign("task", "executor", 1, "key"))
        self.assertFalse(self.ledger.assign("task", "executor", 1, "key"))
        with self.assertRaises(ValueError):
            self.ledger.assign("other", "executor", 1, "key")
        with self.assertRaises(ValueError):
            self.ledger.assign("task", "executor", 2, "key")

    def test_events_deduplicate_and_refuse_regression(self):
        self.ledger.assign("task", "executor", 1, "key")
        message_id = str(uuid4())
        self.assertTrue(self.event(1, "accepted", message_id))
        self.assertFalse(self.event(1, "accepted", message_id))
        with self.assertRaises(ValueError):
            self.event(1, "started", message_id)
        with self.assertRaises(ValueError):
            self.event(2, "started", generation=2)
        self.assertTrue(self.event(2, "started"))
        self.assertTrue(self.event(3, "heartbeat"))
        self.assertTrue(self.event(4, "completed"))
        with self.assertRaises(ValueError):
            self.event(5, "started")
        with self.assertRaises(ValueError):
            self.event(3, "progress")
        self.assertEqual(self.ledger.status("task")["state"], "completed")

    def test_restart_persists_events(self):
        self.ledger.assign("task", "executor", 1, "key")
        self.event(1, "accepted")
        self.store.close()
        self.store = Store(self.path)
        self.ledger = AssignmentLedger(self.store)
        self.assertEqual(self.ledger.status("task")["last_sequence"], 1)
        self.event(2, "started")
        self.assertEqual(self.ledger.status("task")["state"], "running")

    def test_cancel_request_not_terminal(self):
        self.ledger.assign("task", "executor", 1, "key")
        self.assertTrue(self.ledger.request_cancel("task", 1))
        self.assertEqual(self.ledger.status("task")["state"], "cancel_requested")
        self.event(1, "cancelled")
        self.assertEqual(self.ledger.status("task")["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()


class DurableOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "hub.db"
        self.store = Store(self.path)
        self.ledger = AssignmentLedger(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_outbox_atomic_recovery_and_delivery(self):
        self.ledger.assign("task", "worker", 1, "key")
        self.assertEqual(len(self.ledger.pending_commands()), 1)
        self.store.close()
        self.store = Store(self.path)
        self.ledger = AssignmentLedger(self.store)
        self.assertEqual(self.ledger.pending_commands()[0]["idempotency_key"], "key")
        self.assertTrue(self.ledger.mark_delivered("task"))
        self.assertFalse(self.ledger.mark_delivered("task"))
        self.assertEqual(self.ledger.pending_commands(), [])

    def test_expired_lease_requires_reconciliation(self):
        self.ledger.assign("task", "worker", 1, "key")
        self.ledger.lease("task", 1, 110, 100)
        self.assertEqual(self.ledger.reconcile_expired(109), [])
        self.assertEqual(self.ledger.reconcile_expired(110), ["task"])
        self.assertEqual(self.ledger.reconcile_expired(120), [])
        self.assertEqual(self.ledger.status("task")["state"], "needs_reconciliation")
        with self.assertRaises(ValueError):
            self.ledger.lease("task", 1, 140, 120)
        with self.assertRaises(ValueError):
            self.ledger.assign("task", "worker", 2, "key")

    def test_bad_lease_is_rejected_without_change(self):
        self.ledger.assign("task", "worker", 1, "key")
        for deadline, now in ((100, 100), (99, 100), (True, 0)):
            with self.assertRaises(ValueError):
                self.ledger.lease("task", 1, deadline, now)
        with self.assertRaises(ValueError):
            self.ledger.lease("task", 2, 120, 100)
        self.assertEqual(self.ledger.status("task")["state"], "pending")


class CancellationAndRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "hub.db")
        self.ledger = AssignmentLedger(self.store)
        self.ledger.assign("task", "worker", 1, "key")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def event(self, seq, kind):
        return self.ledger.record_event("task", str(uuid4()), seq, 1, kind)

    def test_running_cancellation_requires_terminal_event(self):
        self.event(1, "accepted")
        self.event(2, "started")
        self.assertTrue(self.ledger.request_cancel("task", 1))
        self.assertFalse(self.ledger.request_cancel("task", 1))
        self.assertEqual(self.ledger.status("task")["state"], "cancel_requested")
        self.event(3, "cancelled")
        self.assertEqual(self.ledger.status("task")["state"], "cancelled")

    def test_expired_job_recovers_from_observed_status(self):
        self.ledger.lease("task", 1, 20, 10)
        self.assertEqual(self.ledger.reconcile_expired(20), ["task"])
        self.assertFalse(self.ledger.reconcile_status("task", 1, "not_found"))
        self.assertEqual(self.ledger.status("task")["state"], "needs_reconciliation")
        with self.assertRaises(ValueError):
            self.ledger.reconcile_status("task", 2, "running")
        self.assertTrue(self.ledger.reconcile_status("task", 1, "running"))
        self.assertEqual(self.ledger.status("task")["state"], "running")
        with self.assertRaises(ValueError):
            self.ledger.reconcile_status("task", 1, "completed")

    def test_cancel_rejects_terminal_and_stale_generation(self):
        with self.assertRaises(ValueError):
            self.ledger.request_cancel("task", 2)
        self.event(1, "accepted")
        self.event(2, "started")
        self.event(3, "completed")
        with self.assertRaises(ValueError):
            self.ledger.request_cancel("task", 1)

    def test_duplicate_event_rejects_generation_mismatch(self):
        message_id = str(uuid4())
        self.assertTrue(self.ledger.record_event("task", message_id, 1, 1, "accepted"))
        with self.assertRaises(ValueError):
            self.ledger.record_event("task", message_id, 1, 2, "accepted")


class RaceAndSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "hub.db")
        self.ledger = AssignmentLedger(self.store)
        self.ledger.assign("task", "worker", 1, "key")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def event(self, seq, kind):
        return self.ledger.record_event("task", str(uuid4()), seq, 1, kind)

    def test_completion_after_cancel_request_wins(self):
        self.event(1, "accepted")
        self.event(2, "started")
        self.ledger.request_cancel("task", 1)
        self.event(3, "completed")
        self.assertEqual(self.ledger.status("task")["state"], "completed")
        with self.assertRaises(ValueError):
            self.event(4, "cancelled")

    def test_failure_after_cancel_request_is_preserved(self):
        self.event(1, "accepted")
        self.event(2, "started")
        self.ledger.request_cancel("task", 1)
        self.event(3, "failed")
        self.assertEqual(self.ledger.status("task")["state"], "failed")

    def test_cancel_before_dispatch_drops_unsent_assign(self):
        self.assertEqual(len(self.ledger.pending_commands()), 1)
        self.ledger.request_cancel("task", 1)
        self.assertEqual(self.ledger.pending_commands(), [])
        self.assertFalse(self.ledger.mark_delivered("task"))

    def test_unknown_status_does_not_requeue(self):
        self.ledger.lease("task", 1, 20, 10)
        self.ledger.reconcile_expired(20)
        self.assertFalse(self.ledger.reconcile_status("task", 1, "not_found"))
        self.assertEqual(self.ledger.pending_commands(), [])
        self.assertEqual(self.ledger.status("task")["state"], "needs_reconciliation")
