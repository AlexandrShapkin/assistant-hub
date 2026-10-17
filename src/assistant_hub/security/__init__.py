"""Offline request authorization primitives; no server or dispatch."""
from dataclasses import dataclass, field
import hashlib
import hmac
import math
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})


def _digest(token):
    if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).digest()


@dataclass(frozen=True)
class Identity:
    """Stable identity supplied only by trusted session-issuing code."""
    subject: str
    scope: str


@dataclass(frozen=True)
class SessionGrant:
    """One-time delivery material: caller must not log or persist this object."""
    token: str = field(repr=False)
    csrf: str | None = field(repr=False)


@dataclass
class _Session:
    token_hash: bytes
    identity: Identity
    mode: str
    csrf_hash: bytes | None
    created: float
    touched: float


class SessionManager:
    """Bounded in-memory sessions, serialized with revocation and validation.

    Clock returns monotonic seconds. Backward/nonfinite clock values fail closed.
    Only successful complete authorization refreshes idle time.
    """
    def __init__(self, *, ttl=3600, idle_timeout=900, max_sessions=128,
                 clock=time.monotonic):
        if (any(isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) or v <= 0 for v in (ttl, idle_timeout))
                or type(max_sessions) is not int or max_sessions < 1):
            raise ValueError("invalid session limits")
        self._ttl, self._idle = ttl, idle_timeout
        self._limit, self._clock = max_sessions, clock
        self._sessions = {}
        self._last = float("-inf")
        self._lock = threading.RLock()

    def _now(self):
        now = self._clock()
        if not math.isfinite(now) or now < self._last:
            self._sessions.clear()
            raise ValueError("invalid session clock")
        self._last = now
        return now

    def _prune(self, now):
        for key, session in list(self._sessions.items()):
            if now - session.created >= self._ttl or now - session.touched >= self._idle:
                del self._sessions[key]

    def issue(self, subject, *, mode, scope):
        """Trusted issuance only, after a trusted authentication step."""
        if (mode not in ("bearer", "cookie") or
                any(not isinstance(v, str) or not v.strip() or len(v) > 256
                    for v in (subject, scope))):
            raise ValueError("invalid session identity or mode")
        with self._lock:
            now = self._now()
            self._prune(now)
            if len(self._sessions) >= self._limit:
                raise ValueError("session capacity reached")
            token = secrets.token_urlsafe(32)
            while _digest(token) in self._sessions:
                token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32) if mode == "cookie" else None
            self._sessions[_digest(token)] = _Session(
                _digest(token), Identity(subject, scope), mode, _digest(csrf), now, now)
            return SessionGrant(token, csrf)

    def authorize(self, token, *, mode, scope, csrf=None, require_csrf=False):
        with self._lock:
            try:
                now = self._now()
            except ValueError:
                return None
            self._prune(now)
            digest = _digest(token)
            session = self._sessions.get(digest)
            if (session is None or not hmac.compare_digest(digest, session.token_hash)
                    or session.mode != mode or session.identity.scope != scope):
                return None
            if require_csrf:
                proof = _digest(csrf)
                if proof is None or session.csrf_hash is None or not hmac.compare_digest(
                        proof, session.csrf_hash):
                    return None
            session.touched = now
            return session.identity

    def revoke(self, token):
        with self._lock:
            return self._sessions.pop(_digest(token), None) is not None

    def revoke_all(self, subject=None):
        """Revoke every session, or every mode/scope for an exact subject."""
        with self._lock:
            for key, session in list(self._sessions.items()):
                if subject is None or session.identity.subject == subject:
                    del self._sessions[key]


def _origin(value, allow_localhost_http):
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError("invalid origin")
    # Deliberately canonical, exact ASCII authorities; no URL normalization fallback.
    if re.fullmatch(r"https?://[a-z0-9.-]+(?::[0-9]{1,5})?", value) is None:
        raise ValueError("invalid origin")
    parts = urlsplit(value)
    if (not parts.hostname or parts.hostname.startswith(".") or
            parts.hostname.endswith(".") or ".." in parts.hostname or
            (parts.port is not None and not 1 <= parts.port <= 65535)):
        raise ValueError("invalid authority")
    if parts.scheme != "https" and not (
            allow_localhost_http and parts.hostname == "localhost"):
        raise ValueError("HTTPS required")
    return parts.netloc


class RequestGuard:
    """Exact Host + Origin checks, no proxy-header trust or credential fallback.

    Headers are raw (name, value) pairs so duplicate fields remain detectable.
    A guard has one mode and one scope; use distinct scopes for each mode.
    """
    def __init__(self, sessions, *, mode, scope, allowed_origins=(),
                 allow_localhost_http=False):
        if mode not in ("bearer", "cookie") or not isinstance(scope, str) or not scope.strip():
            raise ValueError("invalid guard mode or scope")
        self._sessions, self._mode, self._scope = sessions, mode, scope
        self._origins = {origin: _origin(origin, allow_localhost_http)
                         for origin in allowed_origins}

    def authorize(self, method, headers):
        """Return stable Identity or None. Missing/malformed evidence denies."""
        if not isinstance(method, str) or re.fullmatch(r"[A-Z]{1,32}", method) is None:
            return None
        parsed = {}
        try:
            for index, (name, value) in enumerate(headers):
                if (index >= 64 or not isinstance(name, str) or
                        re.fullmatch(r"[A-Za-z0-9-]{1,64}", name) is None or
                        not isinstance(value, str) or len(value) > 4096 or
                        any(ord(c) < 32 or ord(c) > 126 for c in value)):
                    return None
                name = name.lower()
                if name in parsed:
                    return None
                parsed[name] = value
        except (TypeError, ValueError):
            return None
        origin = parsed.get("origin")
        if origin not in self._origins or parsed.get("host") != self._origins[origin]:
            return None
        if self._mode == "bearer":
            if "cookie" in parsed:
                return None
            auth = parsed.get("authorization", "")
            if not auth.startswith("Bearer "):
                return None
            token = auth[7:]
        else:
            if "authorization" in parsed:
                return None
            # A dedicated session cookie only; duplicates and ambiguous syntax deny.
            cookie = parsed.get("cookie", "")
            if not cookie.startswith("__Host-session="):
                return None
            token = cookie[len("__Host-session="):]
        return self._sessions.authorize(
            token, mode=self._mode, scope=self._scope,
            csrf=parsed.get("x-csrf-token"),
            require_csrf=self._mode == "cookie" and method not in _SAFE)
