# Optional executor protocol (draft for #52)

Status: proposed; no live executor or deployment is enabled.

## Product boundary

Assistant Hub assigns work and maintains its own durable assignment/event state.
Codex Smart independently executes tasks, owns its worktrees/checkpoints, and
must continue to work with no Hub installed. Integration is an optional adapter,
not a shared database or a direct import of either product's internals.

## Versioned messages

All messages are JSON objects with `protocol_version` (integer, initially `1`),
`message_id` (opaque UUID), `task_id` (Hub-owned opaque identifier),
`executor_id` (instance identity), and `occurred_at` (UTC RFC3339 timestamp).
Commands additionally carry `idempotency_key` and `assignment_generation`.
Reject unknown protocol versions and malformed or oversized messages before
changing any state. Avoid placing credentials or task prompts in logs.

Supported commands: `capabilities`, `assign`, `request_cancel`, `status`.
Supported events: `accepted`, `started`, `heartbeat`, `progress`, `completed`,
`failed`, `cancel_requested`, `cancelled`. An `assign` carries a bounded task
reference, expected repository, requested capabilities, and execution limits;
it never authorizes merges, credential changes, or external actions by itself.
The executor responds with a result/error envelope and explicit capabilities.

## Delivery, leases, and recovery

Hub records assignment and outbox event in one SQLite transaction, then wakes
the adapter. A periodic watchdog only recovers missed wakeups. Delivery is at
least once: the executor deduplicates by `(executor_id, idempotency_key)` and
replies with the original accepted task identity for retries. The Hub deduplicates
incoming events by `message_id`; a monotonic per-task event sequence rejects
out-of-order state regression. Every lease has a deadline and generation;
expired leases mark an assignment `needs_reconciliation`, never implicitly
start a second job. Resume requires querying executor status and matching its
recorded generation before issuing another command.

## Authority and safety

A Codex Smart instance can have exactly one assignment authority at a time:
Hub-managed or standalone. Handshake reports current authority and active task;
Hub refuses assignment on conflict. Switching modes while work is active is
refused until explicitly reconciled. Cancellation is a request, not evidence of
termination. UI shows last heartbeat, event lag, lease, task/branch/worktree,
blocker, and independently verified PR/CI status; unknown stays unknown.

## Acceptance gates before activation

1. Synthetic adapter tests: duplicate delivery, out-of-order events, rejected
   versions, stale leases, cancellation races, and restart reconciliation.
2. Prove standalone Codex Smart CLI/API remains functional without Hub.
3. Demonstrate one bounded end-to-end task and process restart recovery.
4. Review authorization, localhost-only UI exposure, event redaction and audit.
5. Explicitly authorize any real executor activation; no production migration
   or replacement of the existing runner based on this document alone.
