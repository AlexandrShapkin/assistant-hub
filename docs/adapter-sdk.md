# Adapter SDK v1 (synthetic pre-alpha)

Issue [#1](https://github.com/AlexandrShapkin/assistant-hub/issues/1) defines this
bounded contract: explicit versioned adapters, least-privilege account activation,
read-only polling, deterministic validation and fake conformance evidence.
Acceptance is integration of a second fake provider without provider branches in
Hub, Store or Registry, plus replay, failure, identity and cursor tests. Validation
uses the workflow's offline checks. Real providers, network access, credentials,
dispatch, discovery and database migrations are outside this change.

## Registration and identity

An `Adapter` implements `manifest: Manifest`, `accounts: tuple[str, ...]`, and
`poll(account_id: str, cursor: str | None) -> PollResult`. It is trusted Python
code, explicitly instantiated by an application; the SDK provides no sandbox or
package loader. Polling must perform only reads. Capability declarations are
metadata, not evidence that arbitrary code is safe.

`Manifest(service_id, version, capabilities, sdk_version=1)` separates the
adapter's nonempty implementation version from the integer SDK version. Only SDK
1 is accepted. SDK-incompatible interface or cursor rule changes require a new
SDK version. New provider-defined, namespaced capability names are permitted
without changing the core SDK. Stable service/account IDs are opaque,
nonempty strings compared exactly without normalization. They must survive
restarts; display names and rotating tokens are unsuitable. An adapter must not
reassign an ID to another account. Identity lists and manifests cannot change
after registration; create a new application registry to change configuration.

V1 reserves the following compatibility capability names and semantics:

| Name | mutating | risk | Meaning |
| --- | --- | --- | --- |
| `read` | false | low | Read-only polling / permission metadata |
| `reply` | true | high | Future reply intent, always reviewed |
| `exact-template` | true | low | Future exact approved template intent |

Additional operations use a lowercase namespaced identifier such as
`issues.create`, `feed.fetch`, `devices.status`, or `posts.publish`. Such names
are **open-ended**, and each trusted adapter declares its own `mutating` and
`risk` metadata; no core changes are needed to add a provider operation.
Names without a namespace are rejected unless reserved above. Unknown operations
not declared in the manifest and bound for the specific account are denied.

Only `read` is needed for a read-only connector. Mutation declarations do not
provide an executor. Bindings grant a per-account subset of declared names.
Registration without bindings enables no accounts. Unsupported accounts,
duplicate accounts/bindings, undeclared capabilities and missing poll methods
fail closed. Collection checks the binding and identity before polling; planning
also denies operations outside the binding. This is local application
configuration, not authentication or proof of account ownership.

## Minimal adapter and application

```python
from assistant_hub.core.contracts import Capability, Manifest, PollResult
from assistant_hub.core.contracts import PermanentPollError
from assistant_hub.core.registry import Binding, Registry

class EmptyFixture:
    manifest = Manifest("empty-fixture", "1.0", (Capability("read", False, "low"),))
    accounts = ("fixture-a",)

    def poll(self, account_id: str, cursor: str | None) -> PollResult:
        if account_id not in self.accounts or cursor not in (None, "complete"):
            raise PermanentPollError("unsupported fixture scope or cursor")
        return PollResult((), "complete")

registry = Registry()
registry.enable(EmptyFixture(), (Binding("fixture-a"),))
# Hub(registry, store).collect("empty-fixture", "fixture-a")
```

`DemoAdapter` and `BulletinAdapter` in `core/demo.py` are executable synthetic
examples. Bulletin uses distinct service/accounts, out-of-order timestamps and
overlapping pages; its integration adds only fixture/application code, with no
provider-specific Hub, Store or Registry logic. The CLI explicitly registers
both and offers `collect-bulletin bulletin-alpha`; `collect-demo` is unchanged.

## Pages, cursors and failures

`PollResult.events` is a tuple of validated `Event` objects in the requested
service/account. Events use timezone-aware timestamps. The entire result is
validated before writes. Mutable event attributes are revalidated at ingestion.
Deduplication uses `(service, account, external_id)`; first stored content wins,
regardless of arrival/timestamp order. Providers must keep external IDs stable
across overlapping and repeated pages. An updated event with the same ID is not
an update operation in v1.

Cursors are opaque, provider-owned strings of 1–4096 characters (not all
whitespace), scoped to one service/account. `None` means initial/unestablished
state. An initial empty poll may keep `None`; after a string is saved, returning
`None` is rejected. Empty and terminal pages retain or advance the cursor; there
is no universal terminal token or core pagination loop. Each collect polls once.
Core does not compare or parse tokens, require timestamp order, or prove that a
provider's opaque token moves forward. A provider must reject invalid tokens
rather than silently starting over, and must not put credentials in cursors.
No reset API or state migration is provided. Existing demo `done` tokens remain
valid with the unchanged database schema.

Providers raise `TransientPollError`, `PermanentPollError`,
`AuthenticationPollError`, or `RateLimitPollError` (all `PollError`). Categories
are descriptive and contain no credentials or provider response bodies. Core
propagates these exceptions and performs **no automatic retry**, reset, refresh,
backoff or account acquisition. The application decides whether/when to collect
again. A later collection receives the last committed cursor. Unexpected Python
exceptions also propagate; core does not guess their category. Malformed SDK
values raise `ValueError`; unknown services use `KeyError` at registry lookup.

Event insertion, cursor replacement and successful collection audit are a single
SQLite transaction. Validation, polling and SQL failures leave that transaction's
state unchanged. Failed polls have no collection audit entry in v1. Polling is
outside the transaction: providers must tolerate replay after a crash or failure.
This guarantees local atomicity, not an external exactly-once delivery protocol.

## Offline conformance

`core/conformance.py:validate_poll_result(service, account, result,
previous_cursor)` is the reusable runtime validator used by Store. It never
polls or writes. `tests/test_adapter_sdk.py:assert_read_conformance` is a reusable
unittest fixture runner accepting a fresh deterministic fake factory, expected
unique count per account and bounded page count. It validates and replays every
page, then collects through Hub. Fake fixtures must reach a repeatable terminal
page within that bound. Add another factory to `test_fixture_conformance` or use
the helper in an adapter's own offline tests.

The suite additionally injects all typed errors, invalid pages, spoofed scope,
disabled accounts, changed identities and an SQLite audit failure. These checks
are finite examples, not certification of read-only behavior, account ownership,
provider correctness or production readiness. CI's Python 3.11–3.13 matrix still
needs to run on any eventual PR; local success does not establish CI success.
