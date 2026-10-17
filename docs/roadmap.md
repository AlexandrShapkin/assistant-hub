# Roadmap

**Status:** pre-alpha. GitHub [Issues](https://github.com/AlexandrShapkin/assistant-hub/issues) is the live source of truth for task state. This page describes sequencing and links, not a second queue. Milestones group stages and do not certify production readiness.

## M0 — Foundation

- [#1](https://github.com/AlexandrShapkin/assistant-hub/issues/1) — adapter SDK and read-only conformance.
- [#2](https://github.com/AlexandrShapkin/assistant-hub/issues/2) — authenticated access and secrets lifecycle.
- [#12](https://github.com/AlexandrShapkin/assistant-hub/issues/12) — auditable, idempotent outbound execution (disabled until safely authorized).

## M1 — Connectors

- [#4](https://github.com/AlexandrShapkin/assistant-hub/issues/4) — Gmail read-only synchronization.
- [#5](https://github.com/AlexandrShapkin/assistant-hub/issues/5) — Telegram user-account read-only integration.
- [#6](https://github.com/AlexandrShapkin/assistant-hub/issues/6) — VK API capability assessment.
- [#7](https://github.com/AlexandrShapkin/assistant-hub/issues/7) — general site, RSS and API ingestion.
- [#8](https://github.com/AlexandrShapkin/assistant-hub/issues/8) — GitHub adapter.

## M2 — Experience

- [#3](https://github.com/AlexandrShapkin/assistant-hub/issues/3) — authenticated self-hosted unified inbox.
- [#20](https://github.com/AlexandrShapkin/assistant-hub/issues/20) — [offline synthetic UI preview](../web/README.md), related to #3; implementation prepared for review, not marked complete before merge. No authentication or real API access.

## M3 — Automation

- [#9](https://github.com/AlexandrShapkin/assistant-hub/issues/9) — isolated remote-device agent contracts.
- [#10](https://github.com/AlexandrShapkin/assistant-hub/issues/10) — model-assisted suggestions, drafts and prioritization.
- [#11](https://github.com/AlexandrShapkin/assistant-hub/issues/11) — Telegram-channel media publishing workflow.

## Implemented in bootstrap (synthetic demonstration only)

Typed provider-neutral contracts, explicit adapter registry, account-scoped
event ingest, persisted cursors, SQLite state and deduplication, deterministic
permissions, idempotent intent record, audit-only review, CLI, unit tests,
CI and public-tree checks.

No real provider integration, external sending, model calls, deployments,
production dates, provider compatibilities or license grants are claimed.

See [development workflow](workflow.md) for Issue/PR lifecycle, testing,
evidence requirements and security boundaries.
