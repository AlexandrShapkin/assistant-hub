"""Orchestration of enabled adapters, persistence, and independent policy."""
from typing import Protocol

from .contracts import ActionIntent, ApprovalRule, Decision, PollResult, validate_cursor
from .policy import decide
from .registry import Registry


class HubPersistence(Protocol):
    """Only the storage operations needed by adapter orchestration."""

    def cursor(self, service: str, account: str) -> str | None: ...

    def ingest(self, service: str, account: str, result: PollResult) -> int: ...

    def record_intent(self, intent: ActionIntent, decision: Decision) -> Decision: ...


class Hub:
    def __init__(self, registry: Registry, store: HubPersistence) -> None:
        self.registry, self.store = registry, store

    def collect(self, service_id: str, account_id: str) -> int:
        adapter = self.registry.require(service_id, account_id, "read")
        if not any(c.name == "read" and not c.mutating for c in adapter.manifest.capabilities):
            raise ValueError("adapter does not declare read capability")
        cursor = self.store.cursor(service_id, account_id)
        validate_cursor(cursor)
        result = adapter.poll(account_id, cursor)
        return self.store.ingest(service_id, account_id, result)

    def plan(self, intent: ActionIntent, rules: tuple[ApprovalRule, ...] = ()) -> Decision:
        try:
            manifest = self.registry.require(intent.service_id, intent.account_id, intent.operation).manifest
        except (KeyError, ValueError):
            manifest = None
        return self.store.record_intent(intent, decide(intent, manifest, rules))
