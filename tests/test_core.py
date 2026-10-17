from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import stat
import tempfile
import unittest

from assistant_hub.core.contracts import ActionIntent, ApprovalRule, Capability, Event, Manifest, PollResult
from assistant_hub.core.demo import DemoAdapter
from assistant_hub.core.hub import Hub
from assistant_hub.core.policy import decide
from assistant_hub.core.registry import Registry
from assistant_hub.core.store import Store


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "hub.db"
        self.store = Store(self.path)
        self.registry = Registry()
        self.registry.enable(DemoAdapter())
        self.hub = Hub(self.registry, self.store)
        self.intent = ActionIntent("demo", "demo-one", "exact-template", "stable-target", "exact text", "key")
        self.rule = ApprovalRule("demo", "demo-one", "exact-template", "stable-target", "exact text", "local-user")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_account_dedup_separation_and_persisted_cursor(self):
        self.assertEqual(self.hub.collect("demo", "demo-one"), 1)
        self.assertEqual(self.hub.collect("demo", "demo-one"), 0)
        self.assertEqual(self.hub.collect("demo", "demo-two"), 1)
        self.assertEqual(len(self.store.inbox()), 2)
        self.assertEqual(self.store.ingest("demo", "demo-one", DemoAdapter().poll("demo-one", None)), 0)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.cursor("demo", "demo-one"), "done")
        self.assertEqual(self.hub.registry.get("demo").manifest.service_id, "demo")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_spoofed_event_rejects_whole_batch_and_cursor(self):
        valid = DemoAdapter().poll("demo-one", None).events[0]
        for spoof in (replace(valid, account_id="demo-two"), replace(valid, service_id="other")):
            with self.assertRaises(ValueError):
                self.store.ingest("demo", "demo-one", PollResult((valid, spoof), "done"))
            self.assertEqual(self.store.inbox(), [])
            self.assertIsNone(self.store.cursor("demo", "demo-one"))

    def test_default_and_high_risk_review(self):
        self.assertEqual(self.hub.plan(self.intent).status, "review")
        high = replace(self.intent, operation="reply", idempotency_key="high")
        rule = replace(self.rule, operation="reply")
        self.assertEqual(self.hub.plan(high, (rule,)).status, "review")

    def test_exact_rules_all_dimensions(self):
        manifest = DemoAdapter.manifest
        self.assertEqual(decide(self.intent, manifest, (self.rule,)).status, "preapproved")
        for field in ("service_id", "account_id", "operation", "target", "payload"):
            mismatch = replace(self.rule, **{field: getattr(self.rule, field) + " "})
            self.assertEqual(decide(self.intent, manifest, (mismatch,)).status, "review")
        self.assertEqual(decide(replace(self.intent, operation="read"), manifest).status, "allowed")

    def test_unknown_action_and_service_denied(self):
        for intent in (replace(self.intent, operation="unknown", idempotency_key="unknown-action"),
                       replace(self.intent, service_id="unknown", idempotency_key="unknown-service")):
            self.assertEqual(self.hub.plan(intent).status, "deny")

    def test_idempotency_conflict_and_original_decision(self):
        first = self.hub.plan(self.intent)
        self.assertEqual(self.hub.plan(self.intent, (self.rule,)), first)
        with self.assertRaises(ValueError):
            self.hub.plan(replace(self.intent, payload="different"))
        self.assertEqual(len(self.store.intents()), 1)
        self.assertEqual(len(self.store.audit()), 1)

    def test_review_is_only_audit_not_dispatch_or_policy_change(self):
        self.hub.plan(self.intent)
        before = self.store.intents()
        self.store.review("key", "approve", "local-user")
        self.store.review("key", "reject", "local-user")
        self.assertEqual(self.store.intents(), before)
        self.assertEqual([r["kind"] for r in self.store.audit()], ["plan", "review", "review"])
        self.assertFalse(hasattr(self.hub, "dispatch"))
        with self.assertRaises(ValueError):
            self.store.review("missing", "approve", "local-user")

    def test_invalid_manifests_registry_and_contracts(self):
        for args in (("", "1", ()), ("demo", "", ()), ("demo", "1", ("bad",)),
                     ("demo", "1", (Capability("read", False, "low"),) * 2)):
            with self.assertRaises(ValueError):
                Manifest(*args)
        with self.assertRaises(ValueError):
            Capability("reply", True, "medium")
        with self.assertRaises(ValueError):
            self.registry.enable(DemoAdapter())
        with self.assertRaises(ValueError):
            DemoAdapter().poll("unknown", None)
        with self.assertRaises(ValueError):
            Event("demo", "a", "id", "message", datetime.now(), "", "", "")
        with self.assertRaises(ValueError):
            Event("demo", "a", "id", "message", datetime.now(timezone.utc), "", "", "", {"x": 2})

    def test_database_symlink_rejected(self):
        link = Path(self.temp.name) / "link.db"
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            Store(link)


if __name__ == "__main__":
    unittest.main()
