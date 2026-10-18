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
        self.event(1, "cancel_requested")
        self.assertEqual(self.ledger.status("task")["state"], "cancel_requested")
        self.event(2, "cancelled")
        self.assertEqual(self.ledger.status("task")["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
