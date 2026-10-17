# 0002: Independent session and request authorization boundary

Status: accepted for a bounded nonproduction first slice of Issue #2.

## Decision

Keep stdlib-only `security.SessionManager` and `security.RequestGuard` independent
of core contracts and deterministic policy. Trusted code issues stable subject,
mode and scope identities after a future authentication step. A successful guard
result proves possession of a session request proof; it does not grant adapter
capabilities, approve an action, or provide an authenticated web UI.

Use unpredictable opaque bearer tokens, SHA-256-only session state, constant-time
proof comparisons, absolute and idle expiry, explicit revocation and bounded
in-memory capacity. Return raw delivery material once with redacted repr. Keep
machine Authorization and browser cookie modes separate and configure different
scopes. Require exact configured HTTPS Origin and matching Host for both modes;
only explicitly enabled localhost HTTP is available for offline/dev tests.
Reject duplicate or malformed headers, mixed credentials and fallback attempts.
Require a per-session CSRF proof for every unsafe browser method. A future HTTPS
cookie must use HttpOnly, Secure, SameSite=Strict, Path=/ and no Domain; never
place tokens in URLs. No listening server or cookie delivery is implemented.

## Threat model and consequences

Untrusted callers, forged proofs, replay after expiry/revocation, cross-site
requests and header ambiguity are addressed by deterministic offline tests.
Trusted in-process code and faithful raw HTTP metadata are assumptions. A stolen
live bearer is replayable until timeout or revocation; this slice does not defend
against XSS, compromised Python code, or network denial of service. Origin and
Host alone never establish identity. Sessions disappear on restart; concurrent
operations are serialized within one process only. An identity returned before
revocation is a point-in-time result, not an execution transaction.

Encryption at rest, provider-secret lifecycle, rotation, retention, deletion,
redacted durable audit and optional 2FA remain TODO. Backup restore must never
resurrect sessions or revoked credentials and needs encrypted backups, separate
key custody and recovery drills before real use. Login, HTTP integration, TLS,
rate limiting, cookie delivery and independent review are deployment gates.
No production readiness, real credentials, provider integration, authenticated
web UI or external dispatch is claimed. See [security](../security.md) for the
API contract, threat assumptions and remaining gates.

## Validation

Deterministic injected-clock unittest cases cover anonymous/forged access,
TTL/idle boundaries, failed-proof idle behavior, revocation/replay, mode/scope
separation, CSRF, exact Host/Origin, localhost opt-in, malformed headers, capacity
and hash-only state. Run the repository's full documented local checks; local
success is not CI or deployment evidence.
