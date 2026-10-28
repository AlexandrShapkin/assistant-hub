"""Hub orchestration depends on a narrow persistence port, not SQLite."""
import unittest

from assistant_hub.core.contracts import ActionIntent, Decision, PollResult
from assistant_hub.core.demo import DemoAdapter
from assistant_hub.core.hub import Hub
from assistant_hub.core.registry import Binding, Registry


class MemoryPersistence:
    def __init__(self):
        self.cursors = {}
        self.ingested = []
        self.decisions = []

    def cursor(self, service: str, account: str) -> str | None:
        return self.cursors.get((service, account))

    def ingest(self, service: str, account: str, result: PollResult) -> int:
        self.ingested.append((service, account, result))
        self.cursors[(service, account)] = result.cursor
        return len(result.events)

    def record_intent(self, intent: ActionIntent, decision: Decision) -> Decision:
        self.decisions.append((intent, decision))
        return decision


class HubPersistenceBoundaryTests(unittest.TestCase):
    def test_collect_and_plan_without_sqlite(self):
        registry = Registry()
        registry.enable(DemoAdapter(), (
            Binding("demo-one", ("read", "exact-template")),
        ))
        persistence = MemoryPersistence()
        hub = Hub(registry, persistence)

        self.assertEqual(hub.collect("demo", "demo-one"), 1)
        self.assertEqual(hub.collect("demo", "demo-one"), 0)
        self.assertEqual(persistence.cursor("demo", "demo-one"), "done")
        self.assertEqual(len(persistence.ingested), 2)

        intent = ActionIntent(
            "demo", "demo-one", "exact-template",
            "synthetic-target", "synthetic-payload", "synthetic-key",
        )
        decision = hub.plan(intent)
        self.assertEqual(decision.status, "review")
        self.assertEqual(persistence.decisions, [(intent, decision)])

    def test_disabled_account_never_reaches_persistence(self):
        registry = Registry()
        registry.enable(DemoAdapter(), (Binding("demo-one", ("read",)),))
        persistence = MemoryPersistence()
        hub = Hub(registry, persistence)
        with self.assertRaises(ValueError):
            hub.collect("demo", "demo-two")
        self.assertEqual(persistence.ingested, [])


if __name__ == "__main__":
    unittest.main()
