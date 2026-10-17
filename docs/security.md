# Security assumptions and limitations

This is not production software. It has no external dispatch, network access,
real provider credentials or language-model permission path. The independent
`security` package checks session request proofs and a synthetic owner-password
login admission proof offline; it is not wired into the CLI or core.
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
