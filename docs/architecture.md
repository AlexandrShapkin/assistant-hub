# Architecture

Status: pre-alpha local prototype; interfaces may change.

`CLI -> Hub -> Registry -> Adapter.poll(account, cursor)` collects a `PollResult`.
The registry contains only explicitly supplied adapter instances. There is no
entry-point discovery, plugin import by name, subprocess execution, or provider
configuration loader. Adapter code is trusted code, not sandboxed code.

The store validates every event against the requested service/account before any
write. Event insertion, cursor advancement, and collection audit are one SQLite
transaction. `(service, account, external_id)` identifies an event; the first
stored version wins. Cursors are opaque strings scoped by service and account.
The demo recognizes two synthetic accounts and returns one event per account,
then an empty result for the saved cursor. Polling itself is not transactional
with an external service; future adapters must tolerate retries.

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
