# Persistent development reports (Issue #52, first slice)

Start the existing authenticated [localhost application](../README.md#local-authenticated-application-issue-26)
with its owner verifier and private SQLite database. After login, the Development
control panel reads real persisted reports every 15 seconds. With no reports it
shows no known activity. It does not populate demonstration tasks. Refreshing
this panel never polls GitHub or reads another checkout.

Only `assistant-hub` and `codex-smart` are active project identities. `rustcraft`
is a candidate; it can be monitored but its controls fail closed. This catalog
is not an authorization to execute tasks in any repository.

## Owner reporting API

`GET /api/development` returns projects, latest task reports and the latest 200
structured report/control events. Older events remain in SQLite. This is an
owner reporting API, **not** the optional executor command protocol proposed in
PR #53. No executor is registered, no lease or assignment is granted, and
Codex Smart has no runtime dependency on this module.

`POST /api/development/report` requires the existing owner bearer session,
exact localhost Host/Origin and `Content-Type: application/json`. All fields
are bounded strings; unknown/missing fields fail. Example shape (replace these
values with actual observed evidence; do not submit this as real progress):

```json
{
  "protocol_version": "1",
  "message_id": "59144201-55c0-46c7-a0d8-d06e8a63358e",
  "task_id": "bounded-task-id",
  "project": "assistant-hub",
  "executor_id": "owner-reporter",
  "sequence": "1",
  "status": "running",
  "issue": "52",
  "branch": "unknown",
  "head_sha": "unknown",
  "pr": "unknown"
}
```

Use a new canonical UUID per report; retry the identical envelope on uncertain
delivery. Task IDs and executor IDs use ASCII letters/digits/dot/underscore/dash,
at most 64 characters. Sequences start at 1 and increment exactly by 1. Task
project, executor and issue are immutable. Status is `running`, `blocked`,
`completed` or `failed`; terminal reports cannot regress. Head SHA is full
lowercase 40-character hex or `unknown`; PR is a positive number or `unknown`.
Branches are at most 128 ASCII letters/digits/dot/underscore/slash/dash. Task
capacity is 100; this slice provides no destructive cleanup API.

Receipt time is assigned by Hub. A receipt no older than 90 seconds is labelled
`recent report`, not proof that an agent is alive. Exact replay never refreshes
receipt time. Clock rollback produces `stale / unknown`. A changed message with
the same ID, skipped sequence, unknown project or unsupported version fails
without changing task, event or audit state.

PR numbers, branch and commit are owner-submitted evidence, not independently
verified facts. PR verification, CI and worktree stay `unknown`. The timeline
contains structured lifecycle events; raw process output, prompts, credentials,
arbitrary metadata and personal paths are not accepted. Do not place sensitive
information in identifiers or branch names. This API cannot reliably detect
secrets encoded in otherwise valid identifiers. SQLite is not encrypted at rest.

Use the existing in-memory owner login; never place a session in a URL, command
line, repository file or log. No unattended agent token provisioning exists.
An optional least-privilege executor transport needs its own security review.

## Safe requests and recovery

`POST /api/development/control` accepts exactly `message_id` (UUID), `task_id`
and `action` (`pause` or `resume`). It durably records an audited request and
returns `delivery: pending`. Exact retries are idempotent. Candidate, unknown
and terminal tasks reject requests. A request never changes the reported task
status. No consumer, acknowledgement, executor cancellation or resumption exists;
the UI explicitly displays `pending, not delivered`. There is no approval,
merge, shell, worktree or deployment endpoint.

Each report/task projection/audit update is one SQLite transaction. Stop and
restart the server with the same DB to recover reports and requests; log in
again because sessions deliberately do not survive restart. The reporting
source must retain its task/message IDs and next sequence. A report retry
returns the original acceptance even after subsequent reports. Snapshot event
IDs are durable local ordering; GET does not advance heartbeat or task state.

## Remaining gates

Issue #52 remains open: least-privilege executor handshake and event forwarding,
assignment authority and leases, command acknowledgements, verified PR/CI,
real process logs/exit status and one end-to-end executor task with restart
reconciliation remain unimplemented. Keep the standalone runner in place.
PR #125 exact-head owner authorization and rustcraft stage/worktree authorization
remain independent gates.
