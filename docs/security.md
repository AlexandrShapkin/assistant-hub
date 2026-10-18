# Security assumptions and limitations

This is not production software. It has no external dispatch. Network access is limited to opt-in public readers
and the isolated, explicitly called GitHub App token transport described below.
No real provider credentials are included or used in tests, and there is no
language-model permission path. The independent
`security` package checks session request proofs and a synthetic owner-password
login admission proof, now also used by the separate localhost application below.
Untrusted event text is data and cannot create approval rules or capabilities.
Rules must come from trusted application code after explicit user approval;
`approved_by` is a local claim, not cryptographic proof. Reviewers are likewise
caller-supplied labels. Do not expose this CLI as a multi-user service.

The registry is explicit enablement of trusted code, not a sandbox. A malicious
Python adapter could bypass core policy through its own code. Capability
manifests declare permission metadata; they do not prove adapter behavior.
Polling adapters must be read-only. Invalid or cross-scope events reject the
entire batch before cursor advancement. SQL values use bound parameters.

Database files use mode 0600 on the supported POSIX environment. The store rejects
symlink paths and nonregular files. New state directories request 0700; existing
parent directories are not repaired. SQLite rollback journals follow SQLite's
local-file behavior. The database and audit log are neither encrypted nor
tamper-evident. Filesystem owners can edit them. Path checks are not a defense
against hostile concurrent replacement in an attacker-controlled directory.
Use a trusted private directory. Backups and terminal output can expose content.

The audit log contains intent keys, decisions, collection counts, and review
labels. Intent payloads and event bodies are stored in plaintext. This scaffold
has no retention, export-redaction, or deletion policy. Use synthetic data only.
Explicit local registry bindings allowlist account capabilities before polling
and planning. They do not authenticate callers or prove account ownership.
Unknown capabilities deny; high-risk actions always require review,
including when an exact low-risk-style rule would otherwise match.

`.gitignore` and `scripts/check_public_tree.py` reduce accidental publication of
state and common key material. The script reads only Git-listed paths, rejects
symlinks before reading, bounds file sizes, and prints categories and paths rather
than matched content. It cannot detect every secret, private message, URL, or
sensitive fact. Review staged diffs manually. Never add real credentials,
sessions, personal messages, subscription links, or deployment access details.


## First request boundary (Issue #2)

Scope: stdlib-only `SessionManager` and composable `RequestGuard`, exercised
without a listening server. Acceptance is deterministic denial of anonymous,
expired, idle, revoked, forged, cross-mode and cross-scope proofs; exact origin
checks and CSRF on every unsafe browser request. For that first slice, login, UI,
provider credentials, persistence, network transport and dispatch were non-goals.
The offline password continuation below adds only verifier persistence and local
login admission. Validation uses the repository unittest, compileall, doctor,
public-tree and diff checks.

Threat model: an unauthenticated remote caller, stolen/replayed bearer proof,
cross-site browser request, malformed/duplicate headers and spoofed forwarding
headers. This assumes trusted Python code, trusted issuance and a faithful HTTP
adapter. It does not defend against malicious adapters, process compromise,
XSS, credential theft, or denial of service at a future network layer. Host and
Origin are request constraints, not authentication: nonbrowser clients can forge
them but still need an unpredictable session token.

Trusted code calls `issue(subject, mode="bearer", scope="api")` or
`issue(subject, mode="cookie", scope="web")` only after separately authenticating
the stable opaque subject. Never derive this identity or scope from request
content or LLM output. Configure distinct API and browser scopes. Tokens and
browser CSRF secrets use `secrets.token_urlsafe(32)` (256 random bits). The grant
returns plaintext once for delivery and hides it from repr; callers must not
log, serialize or retain it unnecessarily. Manager state stores only SHA-256
hashes of tokens and CSRF secrets. Proof comparisons use `hmac.compare_digest`.
Possession of the hash alone is not accepted as a bearer proof.

Absolute TTL and idle timeout expire at the boundary, using an injected monotonic
seconds clock. Successful complete authorization refreshes only idle time;
failed proofs do not. Clock rollback/nonfinite readings invalidate all sessions.
The default capacity is 128; expired records are pruned before issuance and
checks, and a full store rejects issuance without evicting live sessions.
`revoke(token)` invalidates one session immediately; `revoke_all(subject)` removes
all modes/scopes for that exact subject, and `revoke_all()` removes everything.
Restart loses all sessions. An RLock serializes issuance, proof checks and
revocation in one process; a returned identity is a point-in-time result, not a
transaction or authority to execute an external action. Recheck at future action
boundaries. No distributed session consistency or durable session audit exists.

Each guard requires an explicit origin allowlist. Both modes require exact
`Origin` and matching `Host`, including explicit ports. Missing Origin denies
even machine requests and safe browser requests. No suffix matching, wildcard,
implicit default port, forwarded-header fallback, or normalization is applied.
Configuration accepts canonical lowercase ASCII HTTPS origins without paths,
userinfo, query or fragments. Only exact `http://localhost[:port]` is permitted
with the explicit development flag; loopback IP aliases are not supported.

The adapter must pass raw header pairs, preserving duplicates, and the actual
uppercase method before any method override. Headers are bounded (64 fields,
4096 characters per value), ASCII and free of control characters; duplicates
deny. Never merge or discard duplicate security headers upstream. Verify TLS and
request authority at the transport boundary; ignore client-supplied forwarding
claims. The guard intentionally supports a narrow HTTP representation.

Machine mode accepts only `Authorization: Bearer <token>`, with no Cookie header.
Browser mode accepts only `Cookie: __Host-session=<token>`, with no Authorization
header. This first slice deliberately rejects additional cookies and ambiguous
cookie syntax. Every method except GET, HEAD and OPTIONS requires the per-session
`X-CSRF-Token` proof, plus the exact Origin/Host checks. Safe methods must never
mutate state. Tokens and CSRF proofs cannot be interchanged across sessions.
Never put tokens in URLs. A future HTTPS browser adapter must set
`__Host-session=<token>; Path=/; HttpOnly; Secure; SameSite=Strict`, with no Domain,
expire cookies on logout, and deliver CSRF material only to the same-origin
client without exposing the bearer cookie to JavaScript. The localhost HTTP
exception is an offline/dev guard test facility, not an implemented browser
cookie transport or permission to weaken production cookie flags.

## Remaining secrets and deployment gates

Credential vault encryption at rest, key custody, provider-secret rotation,
retention and secure deletion are **TODO**. There is no provider-secret store. Future rotation must support
revocation, bounded overlap and incident recovery without logging key material.
Optional 2FA enrollment, recovery and reauthentication are also TODO; no 2FA
claim is made. Real deployment requires a reviewed authentication/login flow,
TLS, HTTP adapter integration, authorization routing, rate limiting, secure
cookie delivery, redacted security audit events, and independent security review.
The local CLI remains unsuitable as a multi-user service.

Application backup/restore remains TODO: use synthetic data only. The limited
verifier-file recovery procedure below does not implement application backups.
Future backups must encrypt sensitive state, separate keys, restrict access and retention, and test restores.
Restoring application data must not resurrect sessions, revoked tokens or old
credentials; force fresh authentication and verify rotation/revocation state
before enabling access. Neither these primitives nor passing tests establish
production readiness. Core deterministic policy remains a separate requirement;
external action dispatch still does not exist.


## Offline owner password proof

Issue #2 continuation after PR #18, implemented in `security/credentials.py`.
Only synthetic passwords are supported for this proof. No real account, default
password, provider secret, OS account lookup, network call, listener or hidden
home-path selection exists. The API takes an explicit path in an existing trusted
private directory. The frozen `OwnerVerifier` repr hides salt and hash; passwords
are never retained in records, logged or interpolated into errors. Python does
not offer reliable memory erasure: strings and derived material can remain in
process memory. Callers must not log passwords, verifier encodings or grants.

Reproduce bootstrap, reopen, login, scope binding and rotation without persistent
artifacts (all literals below are deliberately fake):

```sh
PYTHONPATH=src python3 - <<'PYCODE'
from pathlib import Path
from tempfile import TemporaryDirectory
from assistant_hub.security import SessionManager
from assistant_hub.security.credentials import VerifierStore, LoginService

with TemporaryDirectory() as private:
    path = Path(private) / "owner.json"
    VerifierStore(path).bootstrap("synthetic-owner", "synthetic-password-one")
    store = VerifierStore(path)  # strict reopen, no cached verifier
    sessions = SessionManager()
    login = LoginService(store, sessions, subject="synthetic-owner",
                         mode="bearer", scope="offline-api")
    assert login.login("synthetic-wrong-password") is None
    grant = login.login("synthetic-password-one")
    assert grant is not None
    assert sessions.authorize(grant.token, mode="bearer", scope="offline-api").subject == "synthetic-owner"
    assert login.rotate("synthetic-password-one", "synthetic-password-two")
    assert sessions.authorize(grant.token, mode="bearer", scope="offline-api") is None
    assert login.login("synthetic-password-two") is not None
print("synthetic offline proof passed")
PYCODE
```

Version 1 has exactly four JSON keys: `version` (integer 1), `subject` (nonblank
stable owner ID, at most 256 characters), `salt` and `hash` (each exactly 64
lowercase hexadecimal characters). Duplicate/unknown fields, alternate versions,
invalid types and encodings reject. Algorithm parameters are fixed by version:
`hashlib.scrypt(N=2**14, r=8, p=1, dklen=32)`, with 32 random salt bytes from
`secrets`, and `hmac.compare_digest` verification. Each derivation uses roughly
16 MiB of working memory plus implementation overhead and synchronous CPU time;
latency varies by host. There is no benchmark or concurrency-wide memory bound.
Passwords require at least 12 Unicode characters, nonblank content, valid UTF-8,
and at most 1024 encoded bytes; a preliminary 1024-character cap bounds encoding
work. No normalization or trimming changes the password. Stored metadata includes
only version/subject plus salt/hash, never plaintext passwords or sessions.

POSIX file operations require the effective user's private parent directory
(no group/other permissions or special mode bits) and reject a symlink immediate
parent. The directory is pinned by descriptor. Bootstrap uses
`O_EXCL|O_NOFOLLOW`, requires a nonexistent destination, and writes mode 0600.
Reads use `O_NOFOLLOW|O_NONBLOCK`, require an owned regular single-link file,
reject executable/special/group/other mode bits, and bound reads to 4096 bytes.
Rotation verifies the old password, preserves subject, creates a random temporary
0600 file in the same directory, fsyncs it, atomically replaces the destination,
then fsyncs the directory. Failed writes/replacements remove temporary files;
pre-replacement failures preserve the old record. A directory fsync failure after
replacement has uncertain durability: the new record may already be installed.
Bootstrap directory fsync failure may similarly leave a complete new record;
inspect/reopen it rather than blindly retrying or deleting it. There is no
rollback guarantee after successful replacement, and crash remnants may require
private-directory inspection. Unlinking is not secure erasure.

These checks assume a trusted directory ancestry, filesystem, process and host.
They do not defend against a compromised host or concurrent hostile parent
filesystem changes. Intermediate ancestor symlinks are not prohibited. Directory
ownership/modes alone cannot prove ancestry trust. No automatic permission repair,
directory creation or privileged operation occurs.

`LoginService.login(password)` returns a grant or generic `None`; failed attempts
never call session authorization or refresh idle time. Identity, mode and scope
are trusted constructor inputs, checked against the stored subject. The default
budget is five attempts per fixed 60-second monotonic window, including successful
logins and rotations. Blocked attempts do not extend the window. Clock rollback
or nonfinite time denies. The bounded state is one counter per configured owner;
there is no attacker-controlled identity map or IP/header assumption. This is a
local CPU admission demonstration, not remote brute-force or DoS protection.
Restart, additional instances and additional processes bypass the budget; timing
is not uniform between malformed, blocked and wrong-password failures. Use one
shared service per owner; additional frontends need shared limiting and trusted
routing. Failed issuance (including full session capacity) returns `None`.

Login and rotation share a service lock. `LoginService.rotate(old, new)` returns
boolean and conservatively calls `revoke_all(subject)` even on denial or failure,
covering post-replacement durability errors. Thus a failed rotation can log out
the owner; a future exposed recovery endpoint needs separate abuse controls.
Successful rotation invalidates every mode/scope for that subject, preserving
other users' sessions. Direct `VerifierStore.rotate` or external replacement is
outside that lock: coordinate all services and explicitly call
`sessions.revoke_all(subject)`, including on uncertain errors, before admitting
further logins. No cross-process coordination is implemented.

For a synthetic backup, stop admission, copy only the verifier file into a trusted
private backup directory with mode 0600, and protect it as password-cracking
material. A salt/hash is not encryption and cannot protect weak passwords from
offline guesses. Restore only while stopped into a trusted private directory,
reject links and permissive modes, reopen with `VerifierStore.read()`, discard all
session managers (or revoke the subject everywhere), then require fresh login.
Restoring an older verifier restores its older password; rotate before admission
if that backup predates revocation or compromise. No backup encryption, freshness
tracking, automation, vault encryption, 2FA, production login or production-ready
security is implemented. Core account authorization remains separate.


## Localhost application (Issue #26)

Scope and acceptance: browser → authenticated stdlib API → Hub/Registry → Store
→ SQLite, with explicit synthetic collection, durable account-isolated status,
audit, logout, bounded requests and safe static assets. Non-goals are public
hosting, TLS provisioning, provider onboarding, event uploads, model permission
paths and any dispatch. Setup commands and the exact browser URL are in the
[root README](../README.md#local-authenticated-application-issue-26).

`local_server` binds only `127.0.0.1` without DNS lookup, requires explicit absolute verifier and DB
paths, and refuses startup without a readable owner verifier. The verifier parent
must be a trusted, owner-owned 0700 directory; the existing `VerifierStore` checks
ownership/modes, no-follow final components and exclusive bootstrap creation.
The local entry point additionally enforces exactly 0700 on the verifier parent
and refuses getpass fallback when terminal input cannot be hidden.
Intermediate ancestry and concurrent hostile filesystem changes remain outside
its protection. Store rejects final-file symlinks and sets DB mode 0600, but
**does not enforce ownership or 0700 on an existing database parent**. Provision
both files in a trusted private directory. No permission repair is performed.

All parsed routes validate raw headers for duplicates, syntax and bounded sizes,
require exact `Host: localhost:PORT`, reject cookies and transfer encoding, and
reject any supplied foreign Origin. POST login requires exact
`Origin: http://localhost:PORT`; authenticated POST additionally uses the existing
`RequestGuard(allow_localhost_http=True)` in bearer mode and `local-web` scope.
A POST with no Origin fails closed, including from browser environments that
omit it. Nonbrowser clients can forge Host/Origin, so these checks complement
rather than replace password/session authentication. Login uses one shared
per-owner `LoginService`: five attempts per 60 seconds, including successes;
process restart resets this local budget. Errors are generic; request targets,
headers, passwords and tokens are never logged. No access logs or stack traces
are emitted by the server. Standard-library parser errors also use generic
responses. Request bodies are capped at 16 KiB with strict UTF-8, JSON object,
exact key/type checks, duplicate-key rejection and exact `application/json`.

GET browser fetches normally omit Origin. Unlike POST, they do not pass through
RequestGuard's strict Origin requirement: they use the same raw header checks,
exact Host, no cookie, an optional exact Origin and exact `Authorization: Bearer`
proof validated by `SessionManager.authorize(mode='bearer', scope='local-web')`.
No Origin is fabricated. Bearer headers are deliberately added by the module;
they are not ambient cookie authority. GET never collects, updates or logs out.
`/healthz` is public and contains only a source-mode label; the public application
shell contains no event content. Every data API requires authentication.

Tokens are delivered only in login JSON and held only in module memory, never
cookies, local/session storage or URLs. Refresh logs out; logout revokes the
session; process restart loses all grants. No CORS allow-origin header exists.
CSP permits only same-origin scripts, styles and API connections, denies frames,
forms, workers and external assets. Responses also set `nosniff`, `no-store` and
frame denial. Static serving is an exact six-path allowlist from `local_web/`,
with no-follow directory/file opens, regular-file checks and no filesystem path
construction from user input. Traversal, encoded paths, query strings and unknown
files deny. Database, repository and verifier are never served.

One server lock serializes authorization, logout, collection and status changes;
each DB operation opens/closes its own SQLite connection in its request thread.
SessionManager also has its own lock. This is not a scalable server or denial of
service defense: threads and connection admission are not globally bounded;
slow clients have a five-second socket timeout. Use one process with synthetic
data on a trusted host only. Browser extensions, XSS, host compromise and other
local processes are outside this demo's protection. No production/public TLS,
reverse proxy, remote deployment or VPS changes are included.

Status is independent UI workflow metadata, never approval or dispatch authority.
Composite service/account/event IDs isolate rows. Event existence is checked
before upsert; status and audit (including authenticated owner actor) commit or
roll back together. Repeating a status keeps one current state row and appends
an audit observation. State remains plaintext and owner-editable. No executor
or event-upload endpoint exists; collection uses explicitly read-bound
DemoAdapter/BulletinAdapter and optionally the public GitHub reader.

Validation: `tests/test_local_server.py` uses ephemeral real loopback HTTP,
private temporary directories and a synthetic test password. Run the repository
checks, `node --check` for both `src/assistant_hub/local_web/*.mjs` modules,
and `node --test web/tests/*.test.mjs`. These tests require a host permitting local
sockets; a sandbox socket denial is a validation blocker, not evidence of success.

## Anonymous public GitHub boundary (#28)

Opt-in scope: public repository metadata, Issues, PRs and workflow runs, manual
collection in the authenticated localhost app, persisted to local SQLite.
Non-goals: private GitHub App authorization/revocation (parent #8), repository
file downloads, tokens, outgoing actions, deployments or production readiness.
Acceptance is bounded normalization, replay deduplication, atomic failure and
existing bearer plus same-origin checks; validation uses offline mocked transport
and the repository Python/Node checks.

Only strict ASCII owner/repo segments configure fixed HTTPS api.github.com
paths. The stdlib GET transport uses an eight-second timeout, no proxy environment,
ambient authentication, cookies, redirects or retries. Each response is bounded
to 2 MiB and each source to 30 items; text is at most 2400 characters and other
stored fields are bounded. Public metadata is checked on every poll. HTTP errors
are typed and surfaced as generic 502/429 without upstream text or stack traces.
No endpoint result is persisted until all endpoints validate.

Provider JSON, titles and bodies remain untrusted data, never permissions or
instructions. Same-repository HTTPS github.com item URLs must match the item's
validated numeric identity; arbitrary URLs are rejected. Local UI renders dynamic
text with textContent and does not interpret provider HTML. Login/bearer and
strict Host/Origin proofs precede collection. Startup, GET, and background tasks
never fetch GitHub. No secrets or GitHub credentials are accepted. Public data
is persisted as plaintext locally; a previously public repository becoming private
does not erase historical local snapshots. Anonymous rate limits and rolling
snapshot gaps remain expected limitations.

## Public feed reader (Issues #32, #36)

The optional `--public-feed HTTPS_URL` localhost sources (one to eight) are
read-only. Manual collection remains behind the owner bearer/Origin boundary.
An explicit `--poll-interval` of 900–86400 seconds also authorizes limited
read-only collection by a separate in-process worker. No sources or scheduler
are enabled implicitly. Each configured URL has a stable account and isolated
HTTP validators; removing a startup binding never erases collected records. No URL is exposed by
public health/static endpoints. The account is a canonical hostname plus URL
SHA-256; cursors contain only versioned bounded HTTP validators, never passwords.
Do not configure secret-bearing URLs. Common credential query keys are rejected;
that filter cannot establish that arbitrary query values are nonsecret.

Each transport call resolves the configured host with `getaddrinfo`, rejects the
entire answer set if any IP is nonglobal, private, reserved, multicast, link-local,
loopback or mapped IPv4, then connects directly to one vetted numeric address.
TLS uses the verified default context and the original canonical hostname for
SNI and certificate validation. It never validates DNS then asks an HTTP client
to resolve again. HTTP status is handled directly: redirects fail closed, with
no proxy, cookie, token, redirect or embedded-resource machinery. Only port 443
is allowed. Responses are bounded to 512 KiB, socket operations to eight seconds;
compressed content is rejected and identity encoding requested.

Only known XML/JSON content types and strict UTF-8 are accepted. XML DTD/entity
declarations are rejected before ElementTree parsing; node, depth and item counts
are bounded. JSON duplicate keys and nonfinite constants fail. All records are
parsed and validated before a result is returned, preserving Store atomicity.
Titles/bodies are control-sanitized and capped at 2000 characters, HTML is stripped
where applicable, and the local UI uses textContent. Display links must pass the
public URL validator and match the configured host; links are never followed.
Only one scheduler worker is used, sharing the same lock as owner requests
but opening its own SQLite connection for each poll. The first attempt waits a
full interval. Source failures are isolated: transient/unknown errors back off
exponentially up to 24 hours, permanent validation errors stop retrying until
a restart. Errors are not logged verbatim. Backoff state is memory-only and
restarts reset it, but the next attempt still waits a full interval. Config
changes require restart; no dynamic discovery or remote URL configuration.
Manual owner polling can deliberately request an extra snapshot. There is
no lossless history guarantee, public deployment or provider mutation.
Tests use fake clocks/transports/DNS/sockets and do not establish live-feed
compatibility.

## GitHub App authentication foundation (Issue #34)

`security/github_app.py` is an isolated, explicit authentication primitive for a
future selected private-repository reader; it is not registered with an adapter,
CLI or server. No real app, credential exchange or private repository integration
has been tested. See [owner setup and API limits](github-app-setup.md).

Configuration carries only numeric app/installation IDs, a strict ASCII
repository slug and a redacted absolute key path. Every signing attempt pins
all path directories with dirfd/O_NOFOLLOW, requires a 0700 effective-owner
parent and a 0600 effective-owner regular single-link file opened O_NOFOLLOW,
and rejects unsafe ancestry and Git working-tree storage. Root-owned sticky
shared temporary ancestry is allowed, but never as the final private parent.
No keys are stored in configuration, generated or added to the project. The
optional explicitly selected system OpenSSL signer receives JWT signing bytes
on stdin, captures signature output, uses no shell, and has a six-second timeout.
Errors omit paths, tokens, JWTs, provider bodies and subprocess diagnostics.

This assumes a trusted single owner, host and filesystem. OpenSSL reopens the
validated absolute pathname; the open descriptor does not make that subprocess
reopen atomic against a malicious same-owner process. No protection against
process compromise, hostile mounts or same-owner replacement is claimed. Key
custody and encrypted-at-rest storage remain unresolved; this is not a vault.
Injected signer/transport code is trusted. JWTs and tokens hide values in repr,
but explicit `.value` access remains sensitive and Python memory is not securely
erased. Tokens remain in memory only, with no persistence or environment lookup.

The only credentialed transport is an explicit fixed GitHub installation-token
POST, confined to one repository and four read permissions. It has no redirects,
proxies, cookies, retries or returned-URL traversal. Strict duplicate-free JSON,
16 KiB responses, status, scope and expiry checks fail closed. Field-shape
compatibility remains unverified. Cache failures erase the local cached reference;
local clear/revoke does not invalidate tokens at GitHub or erase caller copies.
No private API reads, dispatch, listener or production deployment is added.

## Manual weekly iCalendar import (Issue #41)

Owner-selected `.ics` files are uploaded by an authenticated browser only to
`POST /api/calendar/import` on the exact localhost origin, with existing bearer
and strict Host/Origin checks before reading the request body. The maximum
JSON upload request is 128 KiB; the iCalendar payload itself is capped at
96 KiB. All other JSON endpoints retain their prior small-body limit.
Unauthenticated access to the weekly list is denied.

The parser uses only stdlib text, datetime and ZoneInfo; no iCalendar content
causes an HTTP fetch, remote subscription, command execution or HTML execution.
Unfolded line counts, line lengths, component nesting, unique UIDs, duration,
week boundaries and date/time formats are strictly bounded. It does not
expand recurrence or VALARM payloads. It rejects unsupported forms rather than
silently fabricating classes, and renders provider text via `textContent`.
Events are considered private user-provided data (unlike public RSS and GitHub).

Timetable changes are private and visible only through the existing bearer
session at GET /api/calendar/changes. Comparison stores small snapshots of
lesson title, time, location and description from before and after an update
in a bounded 500-row private SQLite table. Initial imports produce no change
alerts; subsequent updates, additions and removals share the week import
transaction. Source/provenance-only changes do not generate false alerts.
The browser renders all change details with textContent and does not poll
the university or other external services when showing/refreshing changes.
Current-week, recent/old-snapshot and upcoming-lesson summaries are
derived entirely within a locally served JavaScript module after bearer
authentication, never from unauthenticated public responses. Calculations
use Asia/Barnaul civil dates, not arbitrary browser timezone. A recent
local import does not certify that the upstream timetable is up-to-date;
missing/stale warnings avoid implying a complete schedule. The module
cannot make network requests, schedule a background poll, store a session,
or expose calendar records to public GitHub Pages.

Every import is a single SQLite transaction, with stable per-week UID hashes,
audit counts, and replacement/removal limited to the specified week. Deleting
an absent class may remove its local status; prior weeks are preserved. Last
import timestamps describe local freshness, not university publication time.
The upload is manual only; automatic polling of university timetable pages is
not implemented, particularly where site crawling is disallowed by robots.txt.
Test fixtures contain only synthetic classes; real exports may require a
separate reviewed compatibility update. No private source URL is committed.

## Opt-in iCalendar subscription (Issue #41)

Scheduled iCal reads are **off** unless both owner-provided CLI flags are
configured: --calendar-url-file and --calendar-interval 900..86400.
Configuration comes from a 0600 owner-only regular file inside a 0700
owner-owned directory, not argv URLs, public APIs, events or Git.
Startup itself makes no external requests. The URL is not logged or returned
by the browser API, and an unauthenticated request cannot change it.

The read-only worker uses the same vetted public feed HTTPS transport with
DNS pinning and certificate verification, no redirects, no ambient proxies
and no nonpublic IP addresses. HTTP Accept requires text/calendar and the
response is limited to a 96 KiB single-week UTF-8 calendar. Everything is
validated before a transactional SQLite import. The worker holds the
shared server lock only for persistence, not remote network I/O.
HTTP validators/backoff are memory-only and reset on restart, but the first
scheduled request is always delayed by a full interval.

Automated collection from АлтГУ /timetable/ HTML is not enabled:
the publisher's robots.txt disallows crawlers there. Only approved public
calendar URLs should be configured. There is no session/cookie reuse,
university authentication, CAPTCHA, scraping, HTML traversal, outgoing
calendar mutation or real-world endpoint tested by these fixtures.

## Offline Google Calendar mirror foundation (Issue #46)

This module is inert unless a future explicitly authorized component calls it.
There is no Google OAuth client, token, network transport, scheduled worker or
write capability yet. ChatGPT's Google connection is not a VPS grant.

Already fetched Google API pages are validated as a complete bounded snapshot
before any private SQLite transaction. Calendar IDs map to stable opaque
account keys. Event updates preserve local workflow status; removals,
cancellations and full resync affect only that calendar account. Sync tokens
are stored only in private SQLite, never provider URLs, logs or public Pages.
All fixtures are synthetic. The stale university calendar subscription must
not be used as a source of current course changes.

## Google Desktop read-only OAuth and network boundary (#46)

Owner consent is never started by the web server. A separate local command
uses Desktop PKCE, loopback callback, strict Host and state verification,
and fixed Google HTTPS token endpoints with verified TLS and no redirects or
ambient proxy. Client JSON, refresh grants and allowlist must be 0600 regular
files within owner-owned 0700 directories; token writes are atomic, reject
symlinks and never persist the ephemeral access token.

Only preselected calendar IDs may be fetched through fixed Google Calendar
Events API GET endpoints, with OAuth bearer headers instead of URL tokens.
The reader validates and bounds each paginated sync before it commits the
private SQLite mirror, preserving independent calendar identities and
existing local workflow statuses. The owner-only services API advertises
mirrored Google accounts without manual collect capabilities. The entire
Google reader is disabled by default; no actual Google authorization,
Google account mutation or scheduled Google polling has been enabled.
