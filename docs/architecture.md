# Architecture

Status: pre-alpha local prototype; [Adapter SDK v1](adapter-sdk.md) is the
versioned polling boundary. An optional public GitHub reader exists; no dispatch exists.

`CLI -> Hub -> Registry -> Adapter.poll(account, cursor)` collects a `PollResult`.
The registry contains only explicitly supplied adapter instances. There is no
entry-point discovery, plugin import by name, subprocess execution, or provider
configuration loader. Adapter code is trusted code, not sandboxed code.

The store validates every event against the requested service/account before any
write. Event insertion, cursor advancement, and collection audit are one SQLite
transaction. `(service, account, external_id)` identifies an event; the first
stored version wins. Cursors are opaque strings scoped by service and account.
Registry validates the SDK version, reserved capability safety constraints and
open-ended namespaced operations, snapshots service/account identities, and
requires explicit per-account capability bindings.
Hub checks the binding before poll and denies unbound planning operations.
Registration without bindings authorizes no accounts. Trusted application code
supplies this configuration; it does not authenticate an account owner.

The demo recognizes two synthetic accounts and returns one event per account,
then an empty result for the saved cursor. A second fake bulletin provider has
distinct identities and overlapping, out-of-order pages. Neither requires
provider branches in the core mechanisms. Polling itself is not transactional
with an external service; future adapters must tolerate replay. Core never
retries automatically. Typed transient, permanent, authentication and rate-limit
errors propagate without changing committed state. Valid cursors are None or
nonblank strings up to 4096 characters; established cursors cannot reset to None.
The shared runtime conformance validator rejects malformed pages and spoofed
scope before writes. SQL failures also roll back events, cursor and audit.

`Hub.plan(intent, rules)` evaluates policy and stores an intent plus decision.
The idempotency key is global within a database: replaying identical intent data
returns the original decision, even if rules changed; different data with the
same key fails. Persisted decisions are historical observations, not execution
authority. A new evaluation needs a new key.

Permission precedence: unknown service/capability denies; high risk requires
review; a declared low-risk read is allowed; a low-risk mutation requires review
unless a trusted caller supplies an explicit exact rule. Rule matching compares
service, account, operation, stable target, and payload without normalization,
wildcards, fuzzy matching, or inference. `approved_by` records the claimed human
source; it is not an authenticated identity. An action target must already be a
stable identifier supplied by trusted code, not a display name resolved here.

Human review appends an audit entry only for an intent with a review decision.
Repeated and conflicting reviews remain as history, with no final execution
state. Neither planning, preapproval, nor review invokes an executor. No executor
exists. Events, payloads, audit records, and attributes remain local data.

The core owns contracts and mechanisms. Future provider packages would own
protocol translation and account semantics, explicitly enabled by applications.
The core has no dependency on a particular provider, device, UI, or LLM.

## Offline browser preview

The independent [`web/` preview](../web/README.md), scoped to Issue #20 (related
to #3), uses static HTML, CSS and ES modules without dependencies. Generic
synthetic events retain source/account/id identity. `view-model.mjs` owns pure
filtering, sorting, counters and immutable, validated status/simulation updates;
`app.mjs` binds these to DOM nodes using textContent. There are no provider parsing
branches, core/backend bindings or dispatch paths.

Draft, review request and approval/rejection are explicitly labelled simulations
in JavaScript memory only. Refresh resets all state. Local file serving loads
only preview resources; CSP denies application connections and workers. No
external resources, storage or service workers exist. Authentication/logout, real APIs and browser access to private data are NOT
implemented. GitHub Pages serves an explicitly allowlisted set of synthetic
static files only; it does not expose the Python application or device agents.
Python session/password proofs are not connected to this UI.


## Local authenticated vertical slice (Issue #26)

The independent `local_server` entry point provides bootstrap and serve commands
using only Python 3.11's standard library. See the [root setup commands](../README.md#local-authenticated-application-issue-26)
and [request boundary](security.md#localhost-application-issue-26). Bootstrap uses
interactive double `getpass` and VerifierStore's exclusive creation. Serve requires
a verifier and DB, binds only 127.0.0.1 and serves an allowlisted `local_web/`
application. The public `web/` preview and Pages publication remain independent.

`local_web/app.mjs → local_server → Hub → Registry → synthetic Adapter.poll → Store`
uses existing mechanisms, with no alternate collection or dispatch path. By default only
DemoAdapter and BulletinAdapter are registered, with explicit per-account read
bindings. `/api/services` lists these synthetic bindings. GET `/api/inbox`,
`/api/services`, `/api/session` require a scoped in-memory bearer session;
POST `/api/login` authenticates through LoginService. POST `/api/collect`,
`/api/status`, `/api/logout` require both bearer authorization and strict
Host/Origin proof. Safe GET shares duplicate-free header/Host validation but
allows absent Origin because browser fetch normally omits it. No cookies or
CORS fallback. The only public endpoints are static assets and minimal healthz.

Store adds `event_states(service, account, external_id, status, updated_at)` with
a composite primary key and allowed-status SQL constraint. `set_status` requires
an existing event; parameterized upsert and actor audit are one transaction.
`inbox()` retains its previous source dictionaries; `inbox_with_status()` joins
state and supplies default `new` without rewriting source events. No workflow
status changes intent decisions, policy or executor authority.

A shared server lock serializes request authorization and operations; each Store
connection lives within a request thread and is closed afterward. SessionManager
retains its own thread safety. This deliberately favors a small single-process
local demo over throughput. Cursors, deduplication and event states survive
restart; passwords and bearer sessions are never stored in the DB. The browser
module retains its token in memory, uses textContent for dynamic event data,
and reauthenticates after refresh. The optional GitHub source described below performs public reads; no sends or model calls exist.

## Public GitHub snapshot provider (#28)

`adapters/github_public.py` is an explicitly instantiated SDK v1 provider with
only the low-risk nonmutating `read` capability. The optional localhost serve
flag registers one lowercased owner/repo account with an explicit read Binding;
Hub, Registry and Store need no provider-specific branches. Services identify
this provider as `synthetic: false`. Repository metadata must confirm public
visibility and matching identity before any source endpoint is read.

Every poll returns a complete bounded snapshot or typed PollError. Versioned
external IDs distinguish issue, pull and workflow identities plus UTC updated
instant; workflow IDs also include attempt/status. Store's existing transaction
atomically commits events, `latest-v1` cursor and audit, and deduplicates replay.
The rolling 30-per-source snapshot can miss updates and is not lossless history.
No background collection, pagination, dispatch or GitHub authentication exists.

## Public feed snapshots (Issue #32, parent #7)

`adapters/public_feed.py:PublicFeedAdapter` implements SDK v1 with service
`public-feed` and only `Capability('read', False, 'low')`. Explicit local serve
options register up to eight canonical URL-derived accounts and read bindings
within one adapter service, each with independent cursor and deduplication. Core Hub,
Registry, Store and schema remain provider neutral and unchanged. Default startup
registers no feeds and configured startup/GET never polls. Authenticated manual
POST collection is always available. A separate worker is opt-in using a bounded
`--poll-interval`; it shares the server lock and per-poll Store transactions,
with per-source backoff, no credentials and no dispatch. GitHub and feeds coexist.

The injectable transport returns an immutable five-field tuple (status,
content-type, raw bytes, ETag, Last-Modified). The default transport pins a vetted
DNS answer to a verified TLS socket; see the security document for restrictions.
RSS channel items, Atom entries and JSON Feed v1/1.1 items normalize to inert
`feed.item` events. IDs hash the canonical source, item ID (or deterministic safe
text/link digest) and supplied timestamp. Poll receipt time never affects identity.
Versioned JSON cursors replace validators on 200 and remain identical on 304;
no established cursor resets to None. Every item, including items beyond the
40-event output cap, is validated before returning the tuple. Snapshots are
bounded and may miss history. No implicit scheduling, transport retries or content URL traversal.
The independent public Pages synthetic preview remains unchanged.

## Isolated GitHub App auth foundation (Issue #34)

`security/github_app.py` supplies immutable app/installation/repository config,
redacted JWT and installation-token values, an injectable signer/REST transport,
and a locked memory-only token manager. An optional explicitly configured system
OpenSSL signer supports RSA PEM keys in trusted owner-only storage outside Git.
The sole implemented credentialed request creates a tightly scoped installation
token; response scope/expiry validation precedes caching. Local revoke/clear is
not remote revocation. There is no adapter registration, server route, account
configuration persistence or private repository read integration. Existing public
GitHub collection and the offline `web/` demo remain unchanged. See
[setup and limitations](github-app-setup.md); parent #8 remains open.


## Owner-uploaded weekly timetable (Issue #41, manual portion)

`calendar_import.py` parses a bounded, explicit UTF-8 iCalendar 2.0 file
without network I/O. The owner-only localhost API validates session, exact
Host/Origin, upload size and all events before touching SQLite. One-week
replacement is transactional in `Store.import_calendar_week`, leaving other
weeks and provider cursors unchanged. It reuses the existing inbox and
workflow-status storage, with a separate `calendar_weeks` table for manual
import freshness. The same transaction records before/after timetable changes
in a private calendar_changes table, retaining the last 500 changes;
initial weekly imports create no alerts and source-provenance-only changes do
not appear as timetable changes. GET /api/calendar/changes requires owner
authentication. The local UI presents seven weekday groups and a per-week
change history, with an explicit local-only Refresh saved data action.
A pure JavaScript calendar_overview module computes current Monday
using Asia/Barnaul civil time regardless of device timezone, prefers the
current/upcoming week, checks the 48-hour import snapshot age, and derives
up to three future lessons from already authenticated inbox data across
two weeks. The dashboard has no remote calls, timers, subscriptions,
notifications or real provider freshness guarantee.

This input is an **import**, not an adapter polling a remote provider.
The local-calendar identity has no `read` registry binding or scheduled
worker; clicking Collect does not fetch the timetable website.
The currently supported format has no recurrence expansion or official
university API connector. Private owner data never enters GitHub Pages.

## Optional iCalendar URL poller (Issue #41)

calendar_sync.py reads a trusted owner-private URL file and schedules one
read-only iCalendar source after an explicit interval. The transport
reuses DNS-pinned public HTTPS request handling; it validates a full week
before the same Store.import_calendar_week transaction used by manual imports.
Provider I/O is outside the owner/API lock, while SQLite writes are serialized.
This does not grant permission to crawl any university site and does not
configure the user's actual timetable until a permitted feed/API is known.

## Google Calendar offline sync boundary (Issue #46, initial stage)

google_calendar_mirror.py converts already authorized, paginated Events API
data into the private SQLite events table, supporting full baseline,
nextSyncToken deltas, cancelled entries, recurring instances and full 410
recovery. It has an injected transport instead of any actual OAuth client,
auth secrets or direct Google HTTP requests. No automatic sync starts with
the service, and no Google events are mutated. Independent user-approved
OAuth, calendar allowlist, polling and opted-in lesson publication remain
future stages.
