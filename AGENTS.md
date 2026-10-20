<!-- shared-agent:start -->
# Agent engineering contract

## 1. Purpose and authority

Follow [.github/DEVELOPMENT_INTERFACE.md](.github/DEVELOPMENT_INTERFACE.md), the
single shared workflow interface. These instructions do not grant runtime,
merge, deployment, device, credential or destructive-operation authority.
Preserve stricter product rules in section 10; stop dependent work on a conflict
and continue independent authorized work. Never use RDC for development.

## 2. Repository start (START)

Discover the actual root, full HEAD, branch and Git status. Compare the intended
base SHA with current GitHub evidence; record divergence rather than assuming
freshness. Inventory worktrees, unfinished changes and active PRs, including
intersecting files and dependencies, before creating commits. Do not silently
switch checkout, overwrite unknown work or rewrite existing branch history.

## 3. GitHub task (TASK)

Search open and closed Issues; reuse the owning task and avoid duplicates.
Record goal, scope/non-goals, acceptance, dependencies and risks. Link Issues
and PRs for cross-repository work to the coordinating Issue. Roadmaps and stage
registries provide navigation, not execution authority or a second live queue.

## 4. Necessary context (CONTEXT)

Read AGENTS.md, the shared interface and the product context entrypoint first.
Read only task-relevant contracts, architecture and source; never load the
whole repository by default. Prefer native git/rg and targeted reads for known
locations; use CodeGraph for useful structural context, semantic tools for
symbol questions and Context7 for version-sensitive external APIs when available.
Do not repeat equivalent retrieval or install tools automatically. An absent
tool is a reported limitation, not permission to download or execute it.

## 5. Planning and implementation (IMPLEMENT)

Work on one bounded task/branch from a verified base or explicitly documented
PR dependency. Preserve product architecture and security invariants. Make
minimal coherent changes; add regression and negative tests for behavior.
Create extra clones/worktrees only for a concrete justified need and within
product authorization. Preserve unrelated files, user data and unique evidence.

## 6. Verification and quality (VERIFY)

Run targeted checks first, then the full mandatory product gates in section 10.
A smoke test cannot replace native validation. Report PASS, FAIL, BLOCKED and
UNVERIFIED distinctly; never disable a failing check to obtain green results.
Keep secrets/private data out of source, diagnostics and public reports. CI is
source evidence, not proof of deployment correctness or runtime authority.

## 7. PR, CI, review and acceptance (PR / REVIEW)

Inspect the complete diff, including new files, before committing. Create or
update a scoped PR linked to its Issue; record base and full HEAD SHA, actual
commands/results, exact-head CI, risks and limits. Repeat affected verification
and refresh CI/review evidence after HEAD changes. Keep author verification,
independent technical ACCEPT, formal GitHub APPROVE and merge authority separate.
Never present your own checks as independent review. Keep PRs Draft pending
required independent acceptance. Do not merge, deploy or change GitHub settings
without explicit task authorization and all applicable product gates.

## 8. Temporary resources (CLEANUP)

At completion, abandonment or supersession, inventory obsolete worktrees,
branches and reproducible artifacts; inventory disk usage before expensive work
when space is low. Delete only exact, verified recoverable and unused items
within authority, after checking tasks/PRs, dirty/untracked files and processes.
Never delete active/protected branches, open or Draft PR work, unknown data,
unique results or user files. No blanket git clean, forced worktree removal or
age-based deletion. Preserve uncertain candidates; record what was removed,
what was retained, why, and measured freed space only when actually measured.

## 9. Final evidence (REPORT)

Report: what changed; repository, PR and full SHA; actual tests and CI; remaining
UNVERIFIED evidence; blockers; owner actions; and temporary resources removed
or preserved. Separate source preparation from installation and live-host proof.

## 10. Product-specific rules
<!-- shared-agent:end -->

<!-- agent-project: assistant-hub -->

Context entrypoint: `docs/workflow.md`. Mandatory native gates on Python
3.11–3.13: `PYTHONPATH=src python -m unittest discover -s tests -v`,
`python -m compileall -q src tests scripts`,
`PYTHONPATH=src python -m assistant_hub doctor`,
`python scripts/check_public_tree.py --include-untracked`, `git diff --check`.
Offline Node.js UI gates: syntax checks for web/local-web modules and
`node --test web/tests/*.test.mjs`. Preserve all Python matrix and offline UI CI.
The current task authorizes Draft PRs only; historical standing merge language
below does not authorize merging these changes or any runtime operation.

### Engineering instructions for Assistant Hub agents

Start by locating this repository's actual root, inspecting HEAD, branch,
`git status --short`, current origin and the owning GitHub Issue. Read
[docs/workflow.md](docs/workflow.md), then only the relevant architecture,
security, decision and roadmap sections. Do not silently switch clones or
overwrite unrelated work.

#### Product invariant

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

#### Autonomous development authority

The owner has approved routine repository changes: Issues, branches, commits,
PRs, CI configuration, documentation, and check-gated merges may proceed
without individual permission requests. Prefer well-scoped, verifiable changes,
not speculative infrastructure. Never bypass a failing gate or publish secrets.

Personal external communications, identity access, finances, destructive
device actions and production deployments have their own explicit runtime
approval and verification boundaries. No general developer authorization
overrides these. No LICENSE chosen: never choose a license on behalf of owner.

#### Work loop

1. Search GitHub open and closed Issues; reuse an existing owning Issue.
2. Record scope, non-goals, acceptance and validation before substantial work.
3. Implement on a feature branch from verified main; preserve unrelated changes.
4. Add focused tests and run the documented checks.
5. Inspect the full staged diff and public-tree hygiene.
6. Open a PR linked to the Issue; inspect final-head CI; merge when accepted.
7. Update docs/roadmap.md pointers or ADRs only for durable changes.

Start with native git/rg, not external tools that alter the environment.
Unknown evidence remains unknown; don't infer CI success from local execution.

#### Checks

    PYTHONPATH=src python -m unittest discover -s tests -v
    python -m compileall -q src tests scripts
    PYTHONPATH=src python -m assistant_hub doctor
    python scripts/check_public_tree.py --include-untracked
    git diff --check

Do not commit private iCalendar uploads, university class schedules or personal group identifiers.\nDo not commit: VPN subscriptions, API keys, tokens, user messages, environment
files, session storage, personal addresses/identifiers, local SQLite databases
or production configuration. No automatic installing providers, fetching user
data, external message sending, hidden dispatch or privileged side effects.

#### Mandatory cleanup after each task

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

