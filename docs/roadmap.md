# Roadmap

**Project state:** pre-alpha proof of platform contracts; not production ready.
GitHub Issues is the live authoritative task tracker; this page records only
stage sequencing and canonical issues. A stage or label is not a delivery claim.

## Foundation
- Issue: publish initial scaffold with CI, documented workflow, secret hygiene.
- Follow-up: [TBD issue] authenticated core service API, event schema and adapter SDK.
- Follow-up: [TBD issue] security model for credentials, audit and permissions.

## Connectors
- [TBD issue] Gmail account adapter (OAuth, safe read-only initial scope).
- [TBD issue] Telegram user accounts adapter (session security and read-only test).
- [TBD issue] VK API feasibility (personal vs community differences).
- [TBD issue] generic site/API/RSS ingestion.
- [TBD issue] GitHub provider adapter.
- [TBD issue] optional device agents via restricted remote protocols.

## Experience
- [TBD issue] authenticated self-hosted web UI: unified inbox and approvals.

## Automation
- [TBD issue] LLM classification and drafts, preserving deterministic policy.
- [TBD issue] publisher/media-center for Telegram/VK, with scoped publishing.
- [TBD issue] idempotent dispatch, retry/reconciliation and human approval.

## Already implemented (demo only)

Synthetic adapter, account-scoped event ingest, cursor state, SQLite storage,
deterministic permission decisions, idempotent intent recording, audit-only
review, CLI, unittest checks, local public-tree hygiene.

No external provider, deployment, license, production date or compatibility
commitment is claimed. Refer to [workflow](workflow.md) for Issue lifecycle.
