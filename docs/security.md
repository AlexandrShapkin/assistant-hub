# Security assumptions and limitations

This is not production software. It has no external dispatch, network access,
real credentials, login service, or language-model permission path. The independent
`security` package checks session request proofs offline; it is not wired into
the CLI or core and does not establish how a human authenticates.
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
checks and CSRF on every unsafe browser request. Login, UI, provider credentials,
persistence, network transport and dispatch are non-goals. Validation uses the
repository unittest, compileall, doctor, public-tree and diff checks.

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

Secrets encryption at rest, key custody, rotation, retention and secure deletion
are **TODO**. There is no provider-secret store. Future rotation must support
revocation, bounded overlap and incident recovery without logging key material.
Optional 2FA enrollment, recovery and reauthentication are also TODO; no 2FA
claim is made. Real deployment requires a reviewed authentication/login flow,
TLS, HTTP adapter integration, authorization routing, rate limiting, secure
cookie delivery, redacted security audit events, and independent security review.
The local CLI remains unsuitable as a multi-user service.

Backup/restore remains TODO: use synthetic data only. Future backups must encrypt
sensitive state, separate keys, restrict access and retention, and test restores.
Restoring application data must not resurrect sessions, revoked tokens or old
credentials; force fresh authentication and verify rotation/revocation state
before enabling access. Neither these primitives nor passing tests establish
production readiness. Core deterministic policy remains a separate requirement;
external action dispatch still does not exist.
