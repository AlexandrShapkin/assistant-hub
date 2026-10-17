# Assistant Hub

**Pre-alpha, nonproduction scaffold.** A Python 3.11+ standard-library-only
prototype for collecting account-scoped events and recording permission decisions.
Both adapters are **fake, synthetic fixtures**. There are no network calls,
credentials, outgoing sends, model integrations, or external action executors.

The platform is independent of any messaging, mail, social, source-control, or
device provider. Earlier isolated remote-demo experiments informed the boundary;
no deployment configuration, private data, or provider integration is included.

The independent [request authorization primitives](docs/security.md) provide
bounded in-memory bearer/browser sessions and CSRF proof checks in offline tests.
They do not provide login or an authenticated web UI; no web UI or HTTP server
exists in this repository. Core policy and audit-only review remain separate.

## Quickstart

From the repository root, without installation or third-party packages:

```sh
export PYTHONPATH=src
python -m assistant_hub doctor
python -m assistant_hub services
python -m assistant_hub collect-demo demo-one
python -m assistant_hub collect-demo demo-two
python -m assistant_hub collect-bulletin bulletin-alpha
python -m assistant_hub inbox
python -m assistant_hub plan-demo --target synthetic-thread --payload 'Synthetic reply' --key example-1
python -m assistant_hub intents
python -m assistant_hub review approve example-1 --reviewer local-user
```

Default state is `~/.local/share/assistant-hub/hub.sqlite3`, outside the repository.
Use the global `--db /path/to/local.sqlite3` argument before a subcommand to change
it. The database is created with mode 0600. `doctor` uses a temporary database and
does not touch the default state. Synthetic accounts are `demo-one` and `demo-two`;
both intentionally reuse an external event ID to demonstrate account separation.

`plan-demo` defaults to the high-risk `reply` capability. Optional
`--operation exact-template` selects a low-risk mutation, still requiring review
unless trusted application code supplies an exact `ApprovalRule`. The CLI does
not create rules. Approval records never send, execute, change a stored policy
decision, or grant future permission. All displayed demo content is fake.

## Framework layout

- `src/assistant_hub/core/contracts.py`: typed dataclasses and adapter protocol.
- `core/registry.py`, `core/demo.py`: explicit account bindings and two synthetic adapters.
- [Adapter SDK v1](docs/adapter-sdk.md): extensible capability names, cursors, typed failures,
  example registration and reusable offline conformance checks.
- `core/policy.py`: deterministic permissions, separate from language models.
- `core/store.py`, `core/hub.py`: local persistence and orchestration.
- `src/assistant_hub/cli.py`: local demonstration commands.
- `tests/`, `scripts/`: regression evidence and public-tree hygiene checks.
- `docs/`: boundaries, security assumptions, decisions, and future scope.
- [Development workflow](docs/workflow.md): Issues as live tasks, scoped PRs,
  explicit CI checks and autonomous routine engineering.
- [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE): bug and feature intake.
- [Roadmap](docs/roadmap.md): stage sequencing and Issue references.

## Verification

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests scripts
PYTHONPATH=src python -m assistant_hub doctor
python scripts/check_public_tree.py --include-untracked
```

CI declares Python 3.11, 3.12, and 3.13. A configured matrix is not evidence that
all versions have passed locally. The hygiene script checks tracked files by
default; `--include-untracked` also checks nonignored new files during bootstrap.
It is a bounded heuristic, not a full secret scanner. Ignored and untracked
private files are not evidence of public-tree safety; review what is staged.

No license has been selected by the owner, so no LICENSE file or open-source
license grant is provided. Public visibility alone does not grant reuse rights.
