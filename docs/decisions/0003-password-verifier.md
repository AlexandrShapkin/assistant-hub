# 0003: Offline owner verifier and login admission

Status: accepted for synthetic proof of concept (Issue #2, continuation of PR #18).

Use Python 3.11 stdlib scrypt with fixed parameters in a strict versioned JSON
record, separate from in-memory sessions and deterministic core policy. A stable
owner subject is trusted configuration. LoginService fixes its mode and scope at
construction and issues through SessionManager only after verification. It never
accepts a caller-selected identity or permission scope.

Scope and acceptance: explicit private-path bootstrap, bounded strict reads,
password verification, bounded admission, atomic verifier rotation and same-owner
session revocation, tested with synthetic passwords and temporary directories.
Non-goals: HTTP/UI, provider secrets, OS accounts, network integrations, vault
encryption, 2FA and production authentication. Validation is the repository's
unittest, compileall, doctor, public-tree and diff checks.

One service owns one identity and one fixed-window counter, avoiding an unbounded
client identity table. Attempts include successful logins and rotation attempts.
All configured entry points for an identity must share admission state; separate
instances or processes do not share limits or synchronize rotation. A service
lock serializes login and rotation. External replacement requires coordination
and explicit revoke_all(subject); an old verifier backup can restore an old
password. No filesystem defense against a compromised host is claimed.

See ../security.md for exact format, usage, durability and recovery limitations.
