# Engineering instructions for Assistant Hub agents

Start by locating this repository's actual root, inspecting HEAD, branch,
`git status --short`, current origin and the owning GitHub Issue. Read
[docs/workflow.md](docs/workflow.md), then only the relevant architecture,
security, decision and roadmap sections. Do not silently switch clones or
overwrite unrelated work.

## Product invariant

Assistant Hub is an expandable **platform** rather than a mail, Telegram or
device-management monolith. Core defines stable mechanism; individually
registered adapters/apps provide provider-specific behavior. Preserve
service/account identity, deterministic policy independent of LLM output,
strict event deduplication, auditability and predictable error handling.

Maturity is pre-alpha: current functionality is **synthetic demo only**.
No real provider integration, network operations or dispatch implementation
exists. Do not imply otherwise.

## Autonomous development authority

The owner has approved routine repository changes: Issues, branches, commits,
PRs, CI configuration, documentation, and check-gated merges may proceed
without individual permission requests. Prefer well-scoped, verifiable changes,
not speculative infrastructure. Never bypass a failing gate or publish secrets.

Personal external communications, identity access, finances, destructive
device actions and production deployments have their own explicit runtime
approval and verification boundaries. No general developer authorization
overrides these. No LICENSE chosen: never choose a license on behalf of owner.

## Work loop

1. Search GitHub open and closed Issues; reuse an existing owning Issue.
2. Record scope, non-goals, acceptance and validation before substantial work.
3. Implement on a feature branch from verified main; preserve unrelated changes.
4. Add focused tests and run the documented checks.
5. Inspect the full staged diff and public-tree hygiene.
6. Open a PR linked to the Issue; inspect final-head CI; merge when accepted.
7. Update docs/roadmap.md pointers or ADRs only for durable changes.

Start with native git/rg, not external tools that alter the environment.
Unknown evidence remains unknown; don't infer CI success from local execution.

## Checks

    PYTHONPATH=src python -m unittest discover -s tests -v
    python -m compileall -q src tests scripts
    PYTHONPATH=src python -m assistant_hub doctor
    python scripts/check_public_tree.py --include-untracked
    git diff --check

Do not commit: VPN subscriptions, API keys, tokens, user messages, environment
files, session storage, personal addresses/identifiers, local SQLite databases
or production configuration. No automatic installing providers, fetching user
data, external message sending, hidden dispatch or privileged side effects.
