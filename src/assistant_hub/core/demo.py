"""Entirely synthetic fixture; performs no I/O."""
from datetime import datetime, timezone
from .contracts import Capability, Event, Manifest, PollResult, PermanentPollError


class DemoAdapter:
    accounts = ("demo-one", "demo-two")
    manifest = Manifest("demo", "1", (
        Capability("read", False, "low"),
        Capability("reply", True, "high"),
        Capability("exact-template", True, "low"),
    ))

    def poll(self, account_id: str, cursor: str | None) -> PollResult:
        if account_id not in self.accounts:
            raise PermanentPollError("unknown synthetic account")
        if cursor not in (None, "done"):
            raise PermanentPollError("invalid demo cursor")
        if cursor == "done":
            return PollResult((), "done")
        return PollResult((Event(
            "demo", account_id, "synthetic-1", "message",
            datetime(2026, 1, 1, tzinfo=timezone.utc), "synthetic-thread",
            "Fake demo event", "Synthetic content only.", {"fixture": "true"},
        ),), "done")


class BulletinAdapter:
    """Second synthetic provider with its own account and pagination semantics."""
    accounts = ("bulletin-alpha", "bulletin-beta")
    manifest = Manifest("bulletin", "1.0", (Capability("read", False, "low"),))

    def poll(self, account_id: str, cursor: str | None) -> PollResult:
        if account_id not in self.accounts or cursor not in (None, "page-2", "complete"):
            raise PermanentPollError("unsupported synthetic account or cursor")
        def event(identity: str, day: int) -> Event:
            return Event("bulletin", account_id, identity, "bulletin",
                         datetime(2026, 1, day, tzinfo=timezone.utc),
                         "synthetic-board", "Fake bulletin", "Synthetic content only.")
        if cursor is None:
            return PollResult((event("later", 3), event("synthetic-1", 1)), "page-2")
        if cursor == "page-2":
            return PollResult((event("synthetic-1", 1), event("middle", 2)), "complete")
        return PollResult((event("later", 3),), "complete")
