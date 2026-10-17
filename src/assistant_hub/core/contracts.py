"""Typed public contracts. Adapter output and manifests are validated at boundaries."""
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Literal, Protocol

SDK_VERSION = 1
# Reserved compatibility names have fixed risk semantics. New provider/application
# capabilities use a namespaced name, e.g. "issues.create" or "feed.fetch".
RESERVED_CAPABILITIES = {
    "read": (False, "low"),
    "reply": (True, "high"),
    "exact-template": (True, "low"),
}
EXTENSION_NAME = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z][a-z0-9]*)+")
Risk = Literal["low", "high"]


class PollError(Exception):
    """Provider failure. Core propagates it without retry or cursor changes."""


class TransientPollError(PollError):
    pass


class PermanentPollError(PollError):
    pass


class AuthenticationPollError(PollError):
    pass


class RateLimitPollError(PollError):
    pass


def validate_cursor(cursor: str | None) -> None:
    if cursor is not None and (not nonempty(cursor) or len(cursor) > 4096):
        raise ValueError("cursor must be None or a nonempty string of at most 4096 characters")


def nonempty(value: str) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class Capability:
    name: str
    mutating: bool
    risk: Risk

    def __post_init__(self) -> None:
        if not nonempty(self.name) or type(self.mutating) is not bool or self.risk not in ("low", "high"):
            raise ValueError("invalid capability")
        reserved = RESERVED_CAPABILITIES.get(self.name)
        if reserved is not None:
            if reserved != (self.mutating, self.risk):
                raise ValueError("reserved capability risk cannot change")
        elif EXTENSION_NAME.fullmatch(self.name) is None:
            raise ValueError("custom capabilities require a namespaced identifier")


@dataclass(frozen=True)
class Manifest:
    service_id: str
    version: str
    capabilities: tuple[Capability, ...]
    sdk_version: int = SDK_VERSION

    def __post_init__(self) -> None:
        if type(self.sdk_version) is not int or self.sdk_version != SDK_VERSION:
            raise ValueError("unsupported adapter SDK version")
        if (not nonempty(self.service_id) or not nonempty(self.version)
                or not isinstance(self.capabilities, tuple)
                or not self.capabilities
                or any(not isinstance(c, Capability) for c in self.capabilities)):
            raise ValueError("invalid manifest")
        for capability in self.capabilities:
            capability.__post_init__()
        if len({c.name for c in self.capabilities}) != len(self.capabilities):
            raise ValueError("duplicate capability")


@dataclass(frozen=True)
class Event:
    service_id: str
    account_id: str
    external_id: str
    kind: str
    timestamp: datetime
    conversation: str
    title: str
    body: str
    attributes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(nonempty(v) for v in (self.service_id, self.account_id, self.external_id, self.kind)):
            raise ValueError("invalid event identity")
        if not isinstance(self.timestamp, datetime) or self.timestamp.utcoffset() is None:
            raise ValueError("event timestamp must be timezone-aware")
        if not all(isinstance(v, str) for v in (self.conversation, self.title, self.body)):
            raise ValueError("event text must be strings")
        if not isinstance(self.attributes, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in self.attributes.items()
        ):
            raise ValueError("event attributes must be string pairs")


@dataclass(frozen=True)
class PollResult:
    events: tuple[Event, ...]
    cursor: str | None


class Adapter(Protocol):
    """Trusted read-only polling code; accounts are stable opaque IDs."""
    manifest: Manifest
    accounts: tuple[str, ...]

    def poll(self, account_id: str, cursor: str | None) -> PollResult: ...


@dataclass(frozen=True)
class ActionIntent:
    service_id: str
    account_id: str
    operation: str
    target: str
    payload: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not all(nonempty(v) for v in (
            self.service_id, self.account_id, self.operation, self.target, self.idempotency_key
        )) or not isinstance(self.payload, str):
            raise ValueError("invalid intent")


@dataclass(frozen=True)
class ApprovalRule:
    """Caller-supplied explicit user approval; no fuzzy or wildcard matching.

    Only trusted application code may supply rules. Content and model output
    must never be converted into approval rules automatically.
    """
    service_id: str
    account_id: str
    operation: str
    target: str
    payload: str
    approved_by: str

    def __post_init__(self) -> None:
        if not all(nonempty(v) for v in (
            self.service_id, self.account_id, self.operation, self.target, self.approved_by
        )) or not isinstance(self.payload, str):
            raise ValueError("invalid approval rule")


@dataclass(frozen=True)
class Decision:
    status: Literal["deny", "review", "preapproved", "allowed"]
    reason: str
