# Architecture

Status: pre-alpha local prototype; [Adapter SDK v1](adapter-sdk.md) is the
versioned polling boundary. No real providers or dispatch exist.

`CLI -> Hub -> Registry -> Adapter.poll(account, cursor)` collects a `PollResult`.
The registry contains only explicitly supplied adapter instances. There is no
entry-point discovery, plugin import by name, subprocess execution, or provider
configuration loader. Adapter code is trusted code, not sandboxed code.

The store validates every event against the requested service/account before any
write. Event insertion, cursor advancement, and collection audit are one SQLite
transaction. `(service, account, external_id)` identifies an event; the first
stored version wins. Cursors are opaque strings scoped by service and account.
Registry validates the SDK version, reserved capability safety constraints and
open-ended namespaced operations, snapshots service/account identities, and
requires explicit per-account capability bindings.
Hub checks the binding before poll and denies unbound planning operations.
Registration without bindings authorizes no accounts. Trusted application code
supplies this configuration; it does not authenticate an account owner.

The demo recognizes two synthetic accounts and returns one event per account,
then an empty result for the saved cursor. A second fake bulletin provider has
distinct identities and overlapping, out-of-order pages. Neither requires
provider branches in the core mechanisms. Polling itself is not transactional
with an external service; future adapters must tolerate replay. Core never
retries automatically. Typed transient, permanent, authentication and rate-limit
errors propagate without changing committed state. Valid cursors are None or
nonblank strings up to 4096 characters; established cursors cannot reset to None.
The shared runtime conformance validator rejects malformed pages and spoofed
scope before writes. SQL failures also roll back events, cursor and audit.

`Hub.plan(intent, rules)` evaluates policy and stores an intent plus decision.
The idempotency key is global within a database: replaying identical intent data
returns the original decision, even if rules changed; different data with the
same key fails. Persisted decisions are historical observations, not execution
authority. A new evaluation needs a new key.

Permission precedence: unknown service/capability denies; high risk requires
review; a declared low-risk read is allowed; a low-risk mutation requires review
unless a trusted caller supplies an explicit exact rule. Rule matching compares
service, account, operation, stable target, and payload without normalization,
wildcards, fuzzy matching, or inference. `approved_by` records the claimed human
source; it is not an authenticated identity. An action target must already be a
stable identifier supplied by trusted code, not a display name resolved here.

Human review appends an audit entry only for an intent with a review decision.
Repeated and conflicting reviews remain as history, with no final execution
state. Neither planning, preapproval, nor review invokes an executor. No executor
exists. Events, payloads, audit records, and attributes remain local data.

The core owns contracts and mechanisms. Future provider packages would own
protocol translation and account semantics, explicitly enabled by applications.
The core has no dependency on a particular provider, device, UI, or LLM.

## Offline browser preview

The independent [`web/` preview](../web/README.md), scoped to Issue #20 (related
to #3), uses static HTML, CSS and ES modules without dependencies. Generic
synthetic events retain source/account/id identity. `view-model.mjs` owns pure
filtering, sorting, counters and immutable, validated status/simulation updates;
`app.mjs` binds these to DOM nodes using textContent. There are no provider parsing
branches, core/backend bindings or dispatch paths.

Draft, review request and approval/rejection are explicitly labelled simulations
in JavaScript memory only. Refresh resets all state. Local file serving loads
only preview resources; CSP denies application connections and workers. No
external resources, storage or service workers exist. Authentication/logout, real APIs and browser access to private data are NOT
implemented. GitHub Pages can serve an explicitly allowlisted set of synthetic
static files only; it does not expose the Python application or device agents.
Python session/password proofs are not connected to this UI.
