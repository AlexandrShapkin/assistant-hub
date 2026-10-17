# Assistant Hub

**Pre-alpha, nonproduction scaffold.** A Python 3.11+ standard-library-only
prototype for collecting account-scoped events and recording permission decisions.
The default adapters are **fake, synthetic fixtures**. Optional public GitHub reads
are available only in the localhost app; there are no outgoing actions,
provider credentials, outgoing sends, model integrations, or external action executors.

The platform is independent of any messaging, mail, social, source-control, or
device provider. Earlier isolated remote-demo experiments informed the boundary;
no deployment configuration or private data is included.

The independent [request authorization primitives](docs/security.md) provide
bounded in-memory bearer/browser sessions and CSRF proof checks in offline tests.
An owner-password verifier admits scoped sessions for a separate localhost-only
application (Issue #26). The separate [offline UI preview](web/README.md)
uses invented data and in-memory simulations only. The local application connects
a browser to a Python API and SQLite (synthetic by default). Core policy and audit-only
review remain separate.

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

## Local authenticated application (Issue #26)

Python 3.11 standard library only; no installation or dependencies. Example
commands below are setup instructions, not an enrollment performed for you.
Create a trusted owner-only directory outside the repository (0700), then use
absolute paths for both verifier and database:

```sh
install -d -m 700 "$HOME/.local/share/assistant-hub-private"
PYTHONPATH=src python3 -m assistant_hub.local_server bootstrap --verifier "$HOME/.local/share/assistant-hub-private/owner.json"
PYTHONPATH=src python3 -m assistant_hub.local_server serve --verifier "$HOME/.local/share/assistant-hub-private/owner.json" --db "$HOME/.local/share/assistant-hub-private/hub.sqlite3" --port 18770
```

Bootstrap prompts twice via `getpass` (minimum 12 characters), creates a verifier
with mode 0600, and refuses an existing file. No default password is supplied.
Open **http://localhost:18770/** on the same computer. The listener binds only
127.0.0.1; the exact `localhost:18770` Host is required, so a browser URL using
127.0.0.1 is rejected. Sign in, explicitly collect synthetic events, select an
item and save its workflow status: `new`, `review`, `deferred` or `done`.
Collection fetches one synthetic page per selected account; repeat to advance
bulletin pagination. Search and service/account/status filters operate on the
stored inbox. These statuses never authorize actions or send messages.

Refresh intentionally discards the bearer token. Sign in again to see persisted
statuses and cursors; server restart preserves SQLite state but revokes sessions.
Logout revokes the current token. Tokens stay in JavaScript memory only; no
cookies, browser storage or URL tokens. The browser must send an exact Origin
on POST; if it omits Origin the request fails closed. Safe GET may omit Origin.
See [security limits](docs/security.md#localhost-application-issue-26).

This remains a single-owner, single-process local pre-alpha demo. No
public interface, production/public TLS setup, private provider links, provider
credentials or message sending exist. Do not forward the port or deploy it to
a VPS. The public Pages/offline `web/` preview stays independent and unchanged.

## Offline browser preview

**[Open the live synthetic UI preview](https://alexandrshapkin.github.io/assistant-hub/)** (works on phones; public demo only, no connected accounts).

A provider-neutral, static [Assistant Hub preview](web/README.md) demonstrates an
inbox, account/service filters and an explicit draft/review simulation. View locally:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory web
```

Open `http://127.0.0.1:8765`. All content is synthetic; state resets on refresh.
No external data, credentials, browser persistence or application network calls
are used by that independent preview. It has no login or backend connection.
A separate Pages workflow may publish the static synthetic preview; no user or
provider data is available there. The static file server is only a local viewing tool.

## Offline password proof (synthetic only)

Run the isolated proof from the repository root:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p test_credentials.py -v
```

For an executable bootstrap/login/rotation example using a temporary private
path, see [offline owner proof instructions](docs/security.md#offline-owner-password-proof).
The verifier uses scrypt (N=16384, r=8, p=1, 32-byte output, approximately 16 MiB
working memory per derivation). This is not a credential vault: encryption,
2FA and production readiness are absent. Use synthetic data only.

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

## Optional public GitHub reader (Issue #28)

Append `--github-public-repo OWNER/REPO` to the existing **local_server serve**
command, for example:

```sh
PYTHONPATH=src python3 -m assistant_hub.local_server serve --verifier "$HOME/.local/share/assistant-hub-private/owner.json" --db "$HOME/.local/share/assistant-hub-private/hub.sqlite3" --port 18770 --github-public-repo octocat/Hello-World
```

Disabled by default. Sign in and explicitly collect `github-public`; startup and
GET requests never poll GitHub. One canonical owner/repo account reads public
repository metadata, Issues, PRs and Actions runs through the official API and
stores normalized events in SQLite. No GitHub login, tokens, private repositories,
repository file downloads, outgoing actions or production readiness are provided.
Synthetic adapters and the separate static Pages demo remain available unchanged.

Each manual poll reads at most 30 records per source (issues, PRs, runs), with no
pagination or retries. This is **not lossless incremental history**: rolling
snapshots can miss updates and anonymous API requests are rate limited. Issues
and PRs sort by updated time; Actions uses GitHub's default run ordering. The
`latest-v1` cursor marks snapshot collection, not a historical watermark. Replays
deduplicate; changed update timestamps produce independent event versions.

## Optional public feed reader (Issue #32)

Append `--public-feed https://hnrss.org/frontpage` to the local
`python3 -m assistant_hub.local_server serve` command above. Exactly one feed
can be configured, alongside the optional GitHub reader. Startup makes no feed
requests. Sign in as the local owner and explicitly collect `public-feed` to
read one RSS2, Atom or JSON Feed v1/1.1 snapshot into local SQLite.

Only public HTTPS names on port 443 are accepted; credential query parameters,
IP literals, local names, redirects and nonpublic DNS answers are refused.
No credentials, ambient proxies, cookies, embedded resources or item links are
fetched. Feed text is displayed as inert text. Each poll accepts at most 512 KiB
and emits at most 40 events. Valid ETag/Last-Modified values enable conditional
requests. Repeated versions deduplicate; a changed item timestamp yields a new
version. Undated IDs remain stable across polls, with receipt time used only
for display. This is a **rolling snapshot, not lossless synchronization**.
There is no scheduling, retry/backoff, discovery or provider action. The default
app remains synthetic, and public `web/` / GitHub Pages remains unchanged.
See [security boundaries](docs/security.md#public-feed-reader-issue-32).

## GitHub App auth foundation (Issue #34)

An isolated stdlib authentication module provides configured app/installation/
repository bindings, redacted RS256 JWTs, strictly scoped installation-token
requests and a locked memory-only cache. Signing can use an explicitly selected
system OpenSSL executable and an owner-only RSA key outside Git. All tests use
fake signers/transports and synthetic tokens; no real app registration, live
credential exchange or private repository integration has been verified. It has
no server or adapter binding. Local clear/revoke does not revoke at GitHub.
Key custody, rotation and production vault design remain unresolved. See
[owner setup and security limits](docs/github-app-setup.md). Public collection
and the synthetic `web/` preview remain unchanged; parent Issue #8 remains open.
