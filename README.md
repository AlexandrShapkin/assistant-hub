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
- [Development workflow](docs/PROJECT_WORKFLOW.md): Issues as live tasks, scoped PRs,
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

## Optional public feed catalog and schedule (Issues #32, #36)

Append one `--public-feed HTTPS_URL` per explicitly selected public RSS 2,
Atom or JSON Feed v1/1.1 source (maximum **eight**), for example:

```sh
PYTHONPATH=src python3 -m assistant_hub.local_server serve \
  --verifier "$HOME/.local/share/assistant-hub-private/owner.json" \
  --db "$HOME/.local/share/assistant-hub-private/hub.sqlite3" \
  --public-feed https://hnrss.org/frontpage \
  --public-feed https://www.python.org/blogs/rss/
```

The default is **no feeds and no background collection**. The login-protected
UI permits manual `public-feed` reads from explicitly enabled sources; each
source has a stable canonical URL-derived account ID, independent
ETag/Last-Modified cursor and deduplication state. The sample sources are
examples, not an automatically enabled or verified installation. Check each
provider's acceptable use policy before adding it.

To opt into **background read-only collection**, add `--poll-interval 1800`
(30 minutes) to that command. Allowed interval: 900–86400 seconds. The first
scheduled request happens *after* one full interval, never during startup.
One bounded worker serializes its SQLite writes with owner requests. Failure
backoff is independent per source (up to 24 hours); permanent validation errors
suspend that source until server restart. There is no automatic polling unless
the flag is present, and no automatic outbound messages or actions.

To disable scheduling, remove `--poll-interval` and restart the local service.
To disable one feed, remove only its `--public-feed` option; existing events,
audit entries and cursor remain in the database without further collection.
Configuration changes require a service restart. Backoff timers are in memory,
not persistent across restarts, and there is no lossless catch-up or historical
pagination.

Only public HTTPS names on port 443 are accepted; credential query parameters,
IP literals, local names, redirects and nonpublic DNS answers are refused.
No credentials, ambient proxies, cookies, embedded resources or item links are
fetched. Feed text is displayed as inert text. Each poll accepts at most 512 KiB
and emits at most 40 events. Valid HTTP validators enable conditional requests.
Repeats deduplicate; changed item timestamps form distinct versions.
This is a **rolling snapshot, not lossless synchronization**. Public `web/`
and GitHub Pages stay synthetic-only. See
[security boundaries](docs/security.md#public-feed-reader-issues-32-36).

## Manual weekly iCalendar import (Issue #41)

The authenticated localhost workspace has a separate **Classes by week** section.
On login, it automatically selects the week beginning Monday in the
`Asia/Barnaul` timezone if available; otherwise the nearest upcoming
imported week, then the most recent past week. The status above the calendar
explicitly warns when **the current week is missing**, or when its last
recorded import was **48 hours ago or earlier**. A recently imported
snapshot is not a guarantee that the university has not changed classes.
The local-only overview shows up to three future lessons found in the next
14 days of imported calendar data, across week boundaries. A blank upcoming
list means **no matching imported events**, not that the university has
cancelled classes. Refresh saved data reads only local SQLite; it does not
request external websites or schedule a poll.
In a browser on the owner's ThinkPad, export the selected week as an `.ics`
file from the timetable website, open `http://localhost:18770/` through the
existing SSH tunnel, sign in and select the exported file. Import is
**owner-initiated and entirely local to Assistant Hub**: the app does not
crawl or request any university pages. File selection does not create a
recurring subscription or remote authorization.

Only a single Monday–Sunday week is accepted per file. The parser supports
bounded UTF-8 iCalendar 2.0 events, `UID`, `DTSTART`, `DTEND`, `SUMMARY`,
`LOCATION` and `DESCRIPTION`, UTC instants and standard IANA `TZID` names.
Floating times default to Altai's `Asia/Barnaul` timezone. It rejects
recurrence rules, unsupported dates, conflicting time zones, malformed files,
empty calendars, over 80 events or over 96 KiB. Real upstream export formats
are **not yet verified**; a site-provided file can reveal needed compatibility
work, and unsupported files must fail closed.

The local timetable also has a **change history** for each imported week.
The first import establishes a baseline without change alerts. Later imports
record added, updated, and removed lessons with before/after subject, time,
and room; identical snapshots create no duplicate change entries. The most
recent 500 changes are retained in the private SQLite database. In the
authenticated UI, select a week to see up to 20 recent changes and use
**Refresh saved data** to read updates committed by any opt-in background
calendar worker (no university request from the browser).

The import replaces only **one selected week** in an atomic SQLite
transaction. Repeating an unchanged file does not add duplicates. Changed
lessons update in place using stable UID-based identities, preserving workflow
statuses. Omitted/cancelled lessons are removed from that week's current
snapshot (including their obsolete workflow statuses); weeks outside the file
remain untouched. Each import is audit-recorded and dated, and the UI displays
that last import time. This is a manually curated **snapshot**, not a live
university calendar, scheduled feed or reliable attendance record.
The owner should check the official source for late changes.

Selected files are read by the browser as text and sent only to the already
authenticated local API over the SSH tunnel. Stored lesson text and audit data
are private SQLite content; weekly backups follow the VPS private-backup
configuration. Uploaded files are not persisted separately, no remote URL is
followed, and no personal timetable identifiers belong in Git or GitHub Pages.
See [calendar security boundaries](docs/security.md#manual-weekly-icalendar-import-issue-41).

## Optional approved HTTPS iCalendar subscription (Issue #41)

Assistant Hub supports a **one-source, opt-in** automatic public iCalendar
subscription when the publisher explicitly allows automated reads and provides
a reusable URL. It is disabled by default. The one-week iCal export button
does not by itself imply an automatically refreshing subscription URL. A
download link may expire or only contain the snapshot from the day of export.

The approved URL must reside in a file outside Git: owned by the service user,
mode 0600, within an owner-owned 0700 directory (the existing private
Assistant Hub directory qualifies). For instance, only if you have a
provider-approved URL (this is an illustrative, **nonfunctional** example):

    printf '%s\\n' 'https://calendar-provider.example.org/export/approved.ics' > \\
      "$HOME/.local/share/assistant-hub-private/calendar-source.url"
    chmod 600 "$HOME/.local/share/assistant-hub-private/calendar-source.url"

Append both options to the existing localhost serve command:

    --calendar-url-file "$HOME/.local/share/assistant-hub-private/calendar-source.url" \\
    --calendar-interval 3600

Polling starts after the first interval (900–86400 seconds), not on startup.
A pinned-DNS, verified HTTPS transport accepts only text/calendar files, checks
file size and complete single-week validity, rejects proxies and redirects,
uses ETag/Last-Modified when present, and applies bounded retry backoff.
Only the represented week is updated; older weeks remain in SQLite. No API
exposes the source URL or lets a browser configure arbitrary remote targets.
The UI shows when the local data was last refreshed, not a provider-certified
timestamp. Manual uploads continue to work independently.

**No authorized automated URL for the АлтГУ timetable has been identified.**
The university's robots.txt disallows crawlers under /timetable/; do not set
that page as a subscription source without permission. Provider-approved URL
and real export-format compatibility remain prerequisites for automatic
refresh of that particular timetable. See
[security boundaries](docs/security.md#opt-in-icalendar-subscription-issue-41).

## Owner-authorized Google Calendar read-only integration (Issue #46)

Desktop OAuth PKCE enrollment and a one-shot Google Events API reader are
implemented as **explicit local commands**, disabled unless invoked by the
owner with private Google Cloud Desktop OAuth credentials. No OAuth grant
exists on ru0 yet. No Google credentials are copied from the independently
connected ChatGPT Google Calendar app.

The owner can authorize read-only calendar-list and event scopes on the
ThinkPad, protect the refresh grant under 0600 permissions, select calendars
in a private allowlist, and then run a bounded one-time Google read into
Hub SQLite on ru0. The owner-only UI will show mirrored calendars as
noncollectable sources. **There is no background Google timer and there are
no write API methods.** Real Google API interoperability still needs testing.
See the full [Google Calendar setup](docs/google-calendar-setup.md).

## Google Calendar offline read-only sync foundation (Issue #46)

A new module, google_calendar_mirror.py, accepts already-authorized Google
Calendar Events API page responses via a caller-supplied transport. It has
NO independent Google OAuth grant, credentials or network requests; the
normal localhost service does not invoke this component yet.

The private Google event mirror stores full or incremental snapshots in local
SQLite using stable per-calendar account hashes and opaque event identities.
It updates changed events, handles recurring event instances and all-day
events, removes cancelled entries, preserves other calendars and existing
local workflow statuses, and persists Google's nextSyncToken only after an
atomic successful transaction. Pagination is bounded (12 pages, at most
1,500 events per sync), and a 410 invalid sync token can trigger a validated
full-calendar replacement. Synthetic offline tests cover these behaviors.

This milestone does not connect the user's account to the VPS. ChatGPT's
Google Calendar connection is separately authorized and cannot be copied to
Assistant Hub. The next implementation stage requires owner-approved,
least-privilege OAuth2, an explicit calendar allowlist and scheduled reading.
Adding university lessons to an owner-writable calendar is a separate,
opt-in WRITE feature that requires an authoritative, permitted schedule
source and a confirmed destination. The existing university subscription is
known not to reflect weekly schedule revisions and is NOT a trusted source.
See GitHub Issue #46 for the staged integration.

## Owner-invoked Gmail metadata read-only foundation (Issue #4)

Assistant Hub now has an opt-in Gmail metadata-only reader for up to two
independently authorized accounts. It uses separate Desktop OAuth grants with
the `gmail.metadata` scope, stable account isolation, bounded inbox baselines,
Gmail `historyId` incremental changes and atomic private SQLite updates.
Subjects, From headers and unread flags are mirrored; **no message bodies,
attachments, snippets or outgoing content are retrieved or persisted**.
The authenticated localhost inbox shows read-only mirrored items, but its
`/api/collect` endpoint cannot start Gmail access. No Gmail account is
authorized, no Gmail timer is enabled, and no Gmail mutations exist at this
milestone. Real owner consent, privacy/retention review and live integration
validation remain prerequisites. See [private Gmail setup](docs/gmail-setup.md).

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
