"""Entirely synthetic fixture; performs no I/O."""
from datetime import datetime, timezone
from .contracts import Capability, Event, Manifest, PollResult


class DemoAdapter:
    accounts = ("demo-one", "demo-two")
    manifest = Manifest("demo", "1", (
        Capability("read", False, "low"),
        Capability("reply", True, "high"),
        Capability("exact-template", True, "low"),
    ))

    def poll(self, account_id: str, cursor: str | None) -> PollResult:
        if account_id not in self.accounts:
            raise ValueError("unknown synthetic account")
        if cursor not in (None, "done"):
            raise ValueError("invalid demo cursor")
        if cursor == "done":
            return PollResult((), "done")
        return PollResult((Event(
            "demo", account_id, "synthetic-1", "message",
            datetime(2026, 1, 1, tzinfo=timezone.utc), "synthetic-thread",
            "Fake demo event", "Synthetic content only.", {"fixture": "true"},
        ),), "done")
