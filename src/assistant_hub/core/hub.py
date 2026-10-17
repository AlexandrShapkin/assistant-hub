"""Orchestration of enabled adapters, persistence, and independent policy."""
from .contracts import ActionIntent, ApprovalRule, Decision
from .policy import decide
from .registry import Registry
from .store import Store


class Hub:
    def __init__(self, registry: Registry, store: Store) -> None:
        self.registry, self.store = registry, store

    def collect(self, service_id: str, account_id: str) -> int:
        adapter = self.registry.get(service_id)
        if not any(c.name == "read" and not c.mutating for c in adapter.manifest.capabilities):
            raise ValueError("adapter does not declare read capability")
        result = adapter.poll(account_id, self.store.cursor(service_id, account_id))
        return self.store.ingest(service_id, account_id, result)

    def plan(self, intent: ActionIntent, rules: tuple[ApprovalRule, ...] = ()) -> Decision:
        try:
            manifest = self.registry.get(intent.service_id).manifest
        except KeyError:
            manifest = None
        return self.store.record_intent(intent, decide(intent, manifest, rules))
