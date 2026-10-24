# Issue #52: persistent development reporting slice

Base: verified GitHub main `69c61ee17a1c30d3934e0c90af5ecf2395d34de9`.
PR #53 is a proposed protocol document, not a runtime implementation; this
slice is independent of that unmerged proposal.

Scope: owner-authenticated report ingestion, durable task/evidence projection,
structured event timeline, and durable pause/resume **requests** in the existing
localhost UI. Only assistant-hub and codex-smart are active projects; rustcraft
is a candidate with controls blocked pending readiness/stage authorization.
No fixture tasks are seeded. Reports are explicitly attributed owner submissions,
not independently verified agent execution or GitHub checks.

Acceptance: anonymous/cross-origin writes fail; malformed, conflicting duplicate
and out-of-order reports leave state unchanged; exact replay is idempotent and
does not refresh heartbeat; reports, audit and control requests survive restart;
stale reports never imply a live agent; UI displays unknown PR/CI verification;
candidate controls fail. Browser refresh reads SQLite without fetching providers.

Non-goals: assignment/lease delivery, executor activation, raw stdout ingestion,
worktree access, GitHub collection, approvals/merges, changes to other repos,
deployment, or replacing the standalone runner. No command consumer exists;
pause/resume requests remain pending and convey no execution authority.

Validation: focused ledger and loopback HTTP tests, JS rendering tests, then all
documented repository checks and diff/public-tree review. Keep #52 open. Open a
draft implementation PR only after duplicate check and validation.

Read-only external audit (2026-10-18): codex-smart main AGENTS.md preserves the
PR #125 merge ban. GitHub reports #125 open/unmerged at head
`9c3090eab03d7673752e39362568552f4c19d7a6`; its body still cites approval/check
evidence for an older head, so that evidence cannot establish current approval.
Rustcraft main AGENTS.md requires authorized stage/batch and original checkout;
readiness is not established. Neither repository was modified or executed.
