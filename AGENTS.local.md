# Project-local rules

Read the canonical interface through root AGENTS.md first. These retained native
rules may strengthen it; shared lifecycle policy belongs to Project Template.
This migration grants no merge, deployment or runtime authority.

# Engineering instructions for Assistant Hub agents

Start by locating this repository's actual root, inspecting HEAD, branch,
`git status --short`, current origin and the owning GitHub Issue. Read
[docs/PROJECT_WORKFLOW.md](docs/PROJECT_WORKFLOW.md), then only the relevant architecture,
security, decision and roadmap sections. Do not silently switch clones or
overwrite unrelated work.

## Product invariant

Assistant Hub is an expandable **platform** rather than a mail, Telegram or
device-management monolith. Core defines stable mechanism; individually
registered adapters/apps provide provider-specific behavior. Preserve
service/account identity, deterministic policy independent of LLM output,
strict event deduplication, auditability and predictable error handling.

Maturity is **pre-alpha and localhost-only**. Two adapters use fictional data
by default. An optional explicit GitHub public-repository reader (Issue #28)
can make anonymous, read-only HTTPS requests for public Issues, PRs and CI runs
when configured at local-server startup, and persists them to local SQLite. Up to eight public feeds may also be
explicitly selected with optional read-only scheduled collection; defaults remain
manual and synthetic. It has no GitHub App/OAuth/private-repository access,
no background GitHub collection,
no external mutation/dispatch, and no production-facing deployment. Public
GitHub Pages remains a separate synthetic-only offline interface.
Do not conflate a verified public read-only source with unrestricted account access.

## Autonomous development authority

The owner has approved routine repository changes: Issues, branches, commits,
PRs, CI configuration and documentation may proceed
without individual permission requests. Prefer well-scoped, verifiable changes,
not speculative infrastructure. Never bypass a failing gate or publish secrets.

Personal external communications, identity access, finances, destructive
device actions and production deployments have their own explicit runtime
approval and verification boundaries. No general developer authorization
overrides these. The consumer license remains an owner decision; upstream MIT notices apply only to imported material.

## Work loop

1. Search GitHub open and closed Issues; reuse an existing owning Issue.
2. Record scope, non-goals, acceptance and validation before substantial work.
3. Implement on a feature branch from verified main; preserve unrelated changes.
4. Add focused tests and run the documented checks.
5. Inspect the full staged diff and public-tree hygiene.
6. Open a Draft PR linked to the Issue; inspect final-head CI; await independent review. No merge authority is granted.
7. Update docs/roadmap.md pointers or ADRs only for durable changes.

Start with native git/rg, not external tools that alter the environment.
Unknown evidence remains unknown; don't infer CI success from local execution.

## Checks

    PYTHONPATH=src python -m unittest discover -s tests -v
    python -m compileall -q src tests scripts
    PYTHONPATH=src python -m assistant_hub doctor
    python scripts/check_public_tree.py --include-untracked
    git diff --check

Do not commit private iCalendar uploads, university class schedules or personal group identifiers.\nDo not commit: VPN subscriptions, API keys, tokens, user messages, environment
files, session storage, personal addresses/identifiers, local SQLite databases
or production configuration. No automatic installing providers, fetching user
data, external message sending, hidden dispatch or privileged side effects.

## Mandatory cleanup after each task

Prevent disk exhaustion: on task closeout, abandonment or replacement, promptly
audit and remove **verified obsolete** local worktrees, task branches, generated
build/test outputs and caches. Check disk space and inventory candidate paths
before another expensive task when storage is low. For worktrees and branches,
verify actual Git state, active tasks/PRs, dirty or untracked files, running
processes and recoverability of commits before removing anything. Only delete
known project-owned artifacts that are reproducible and not needed as evidence.
Never delete active/default/protected branches, open or Draft PR branches,
unknown work, checkpoints, user data, reference material or unique test data.
Do not use blanket `git clean -fdx`, forceful worktree removal, guessed
recursive paths or automatic age-based cleanup. Remote branch deletion,
device cleanup and uncertain/destructive operations require separate authority.
Record exact candidates, actions and measured reclaimed space; if any
precondition is unknown, preserve the item and report it for review.


Keep dashboard/executor runtime isolated. No tools, executors, providers,
services or deployments are activated by administrative instructions.
Also run Node syntax checks and `node --test web/tests/*.test.mjs`.
