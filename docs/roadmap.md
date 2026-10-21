# Roadmap

**Status:** pre-alpha. GitHub [Issues](https://github.com/AlexandrShapkin/assistant-hub/issues) is the live source of truth for task state. This page describes sequencing and links, not a second queue. Milestones group stages and do not certify production readiness.

## M0 — Foundation

- [#1](https://github.com/AlexandrShapkin/assistant-hub/issues/1) — adapter SDK and read-only conformance.
- [#2](https://github.com/AlexandrShapkin/assistant-hub/issues/2) — authenticated access and secrets lifecycle.
- [#12](https://github.com/AlexandrShapkin/assistant-hub/issues/12) — auditable, idempotent outbound execution (disabled until safely authorized).

## M1 — Connectors

- [#4](https://github.com/AlexandrShapkin/assistant-hub/issues/4) — Gmail metadata-only reader, private two-account OAuth flow and bounded inbox/history mirror implemented and tested synthetically; live consent, retention policy, account setup and unattended scheduling remain pending.
- [#5](https://github.com/AlexandrShapkin/assistant-hub/issues/5) — Telegram user-account read-only integration.
- [#6](https://github.com/AlexandrShapkin/assistant-hub/issues/6) — VK API capability assessment.
- [#7](https://github.com/AlexandrShapkin/assistant-hub/issues/7) — general site, RSS and API ingestion; remains OPEN until scheduling/backoff and general site APIs are completed.
- [#46](https://github.com/AlexandrShapkin/assistant-hub/issues/46) — Google Calendar private read-only projection completed as offline foundation; opt-in Desktop PKCE OAuth plus one-shot Google API read and private allowlist available; owner consent, live validation, scheduling and university publishing pending.
- [#41](https://github.com/AlexandrShapkin/assistant-hub/issues/41) — university timetable: manual local .ics import plus opt-in public .ics subscription foundation; a provider-permitted URL and live format verification remain unresolved.\n- [#36](https://github.com/AlexandrShapkin/assistant-hub/issues/36) — child of #7: bounded multi-feed catalog and explicit scheduled read-only polling; no general site APIs.
- [#32](https://github.com/AlexandrShapkin/assistant-hub/issues/32) — child of #7: optional manually polled public HTTPS RSS2/Atom/JSON Feed snapshots; owner-authenticated localhost collection, bounded reads and conditional validators, no actions.
- [#8](https://github.com/AlexandrShapkin/assistant-hub/issues/8) — parent GitHub adapter scope remains open for private GitHub App authentication and revocation.
- [#34](https://github.com/AlexandrShapkin/assistant-hub/issues/34) — child of #8: isolated GitHub App installation auth foundation, fake-only validation; no registered app, live exchange or private adapter. Parent #8 remains open. See [setup limits](github-app-setup.md).
- [#28](https://github.com/AlexandrShapkin/assistant-hub/issues/28) — optional anonymous public GitHub repository snapshots in the authenticated localhost app; bounded manual reads, no private access or dispatch.

## M2 — Experience

- [#3](https://github.com/AlexandrShapkin/assistant-hub/issues/3) — authenticated self-hosted unified inbox.
- [#24](https://github.com/AlexandrShapkin/assistant-hub/issues/24) — RU/EN localization for the synthetic UI.
- [#20](https://github.com/AlexandrShapkin/assistant-hub/issues/20) — [offline synthetic UI preview](../web/README.md), related to #3; implemented and verified in PR #21. No authentication or real API access.
- [#22](https://github.com/AlexandrShapkin/assistant-hub/issues/22) — verified public static preview from PR #23; no private data or backend.

- [#26](https://github.com/AlexandrShapkin/assistant-hub/issues/26) — local authenticated
  browser/API/SQLite vertical slice: scoped memory-only bearer sessions, explicitly
  read-bound synthetic collection, durable per-event workflow statuses and audit.
  Separate `local_web/` app; public offline preview unchanged. Local verification
  requires loopback sockets; implementation does not certify production readiness.

## M3 — Automation

- [#9](https://github.com/AlexandrShapkin/assistant-hub/issues/9) — isolated remote-device agent contracts.
- [#10](https://github.com/AlexandrShapkin/assistant-hub/issues/10) — model-assisted suggestions, drafts and prioritization.
- [#11](https://github.com/AlexandrShapkin/assistant-hub/issues/11) — Telegram-channel media publishing workflow.

## Implemented in bootstrap (synthetic demonstration only)

Typed provider-neutral contracts, explicit adapter registry, account-scoped
event ingest, persisted cursors, SQLite state and deduplication, deterministic
permissions, idempotent intent record, audit-only review, CLI, unit tests,
CI and public-tree checks.

Beyond the optional public GitHub and public feed readers, no real provider integration, external sending, model calls, deployments,
production dates, provider compatibilities or license grants are claimed.

See [development workflow](PROJECT_WORKFLOW.md) for Issue/PR lifecycle, testing,
evidence requirements and security boundaries.
