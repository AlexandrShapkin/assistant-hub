"""Development ledger tests use fictional reports, never seed the application."""
import contextlib
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from assistant_hub.core.store import Store
from assistant_hub.development import DevelopmentLedger


def report(**changes):
    obj = dict(protocol_version="1", message_id=str(uuid4()), task_id="test-task",
               project="assistant-hub", executor_id="test-agent", sequence="1",
               status="running", issue="52", branch="test-branch", head_sha="a" * 40,
               pr="unknown")
    return obj | changes


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "hub.sqlite3"
        self.store = Store(self.path)
        self.now = 1000
        self.ledger = DevelopmentLedger(self.store, clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_empty_real_state_and_no_fixtures(self):
        data = self.ledger.snapshot()
        self.assertEqual(data["tasks"], [])
        self.assertEqual(data["events"], [])
        self.assertEqual(data["projects"], {"assistant-hub": "active", "codex-smart": "active", "rustcraft": "candidate"})
        self.assertFalse(data["executor_connected"])

    def test_replay_staleness_and_restart(self):
        obj = report()
        self.ledger.report(obj, actor="owner")
        self.assertEqual(self.ledger.snapshot()["tasks"][0]["freshness"], "recent report")
        self.now += 91
        self.assertTrue(self.ledger.report(obj, actor="owner")["replayed"])
        task = self.ledger.snapshot()["tasks"][0]
        self.assertEqual(task["freshness"], "stale / unknown")
        self.assertEqual(task["ci"], "unknown")
        self.now = 999
        self.assertEqual(self.ledger.snapshot()["tasks"][0]["freshness"], "stale / unknown")
        with contextlib.closing(Store(self.path)) as reopened:
            data = DevelopmentLedger(reopened).snapshot()
            self.assertEqual(data["tasks"][0]["head_sha"], "a" * 40)
            self.assertEqual(len(data["events"]), 1)
            self.assertEqual(reopened.db.execute("SELECT count(*) FROM audit").fetchone()[0], 1)

    def test_invalid_reports_do_not_change_state(self):
        obj = report()
        self.ledger.report(obj, actor="owner")
        before = self.ledger.snapshot()
        for changes in ({"status": "failed"}, {"message_id": str(uuid4())},
                        {"message_id": str(uuid4()), "sequence": "3"},
                        {"message_id": str(uuid4()), "sequence": "2", "project": "codex-smart"},
                        {"protocol_version": "2"}, {"sequence": True},
                        {"pr": "https://example.invalid/"}, {"project": "other"},
                        {"head_sha": "a" * 7}, {"branch": "bad\nbranch"},
                        {"raw_log": "not accepted"}, {"executor_id": "different", "sequence": "2"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.ledger.report(obj | changes, actor="owner")
            self.assertEqual(self.ledger.snapshot(), before)

    def test_next_report_and_terminal_cannot_regress(self):
        self.ledger.report(report(), actor="owner")
        self.ledger.report(report(sequence="2", status="completed"), actor="owner")
        with self.assertRaises(ValueError):
            self.ledger.report(report(sequence="3"), actor="owner")
        self.assertEqual(self.ledger.snapshot()["tasks"][0]["status"], "completed")

    def test_controls_remain_pending_and_persist_without_changing_task(self):
        self.ledger.report(report(), actor="owner")
        obj = dict(message_id=str(uuid4()), task_id="test-task", action="pause")
        self.assertEqual(self.ledger.control(obj, actor="owner")["delivery"], "pending")
        self.assertTrue(self.ledger.control(obj, actor="owner")["replayed"])
        with self.assertRaises(ValueError):
            self.ledger.control(obj | {"action": "resume"}, actor="owner")
        with contextlib.closing(Store(self.path)) as reopened:
            data = DevelopmentLedger(reopened).snapshot()
            self.assertEqual(data["tasks"][0]["status"], "running")
            self.assertEqual(data["events"][0]["kind"], "control_request")
            self.assertEqual(reopened.db.execute("SELECT subject FROM audit ORDER BY id DESC").fetchone()[0], "owner")

    def test_candidate_and_terminal_controls_denied(self):
        for project, status in (("rustcraft", "running"), ("assistant-hub", "failed")):
            task_id = project
            self.ledger.report(report(task_id=task_id, project=project, status=status), actor="owner")
            with self.assertRaises(ValueError):
                self.ledger.control(dict(message_id=str(uuid4()), task_id=task_id, action="resume"), actor="owner")

    def test_audit_failure_rolls_back_report_and_control(self):
        import sqlite3
        self.store.db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.report(report(), actor="owner")
        self.assertEqual(self.ledger.snapshot()["tasks"], [])
        self.assertEqual(self.ledger.snapshot()["events"], [])
        self.store.db.execute("DROP TRIGGER reject_audit")
        self.ledger.report(report(), actor="owner")
        self.store.db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'test'); END")
        before = self.ledger.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.control(dict(message_id=str(uuid4()), task_id="test-task", action="pause"), actor="owner")
        self.assertEqual(self.ledger.snapshot(), before)
