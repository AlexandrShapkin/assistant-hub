"""Synthetic offline owner-password proof; trusted POSIX filesystem only."""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import stat
import threading
import time

MAX_PASSWORD_BYTES = 1024
MAX_RECORD_BYTES = 4096


def _password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= MAX_PASSWORD_BYTES:
        raise ValueError("invalid password")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid password") from None
    if not value.strip() or len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("invalid password")
    return encoded


def _subject(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("invalid owner subject")


def _derive(password, salt):
    return hashlib.scrypt(_password(password), salt=salt, n=2**14, r=8, p=1, dklen=32)


@dataclass(frozen=True)
class OwnerVerifier:
    """Version 1 fixes all scrypt parameters; no password is retained."""
    subject: str
    salt: bytes = field(repr=False)
    password_hash: bytes = field(repr=False)
    version: int = 1

    def __post_init__(self):
        _subject(self.subject)
        if (type(self.version) is not int or self.version != 1 or
                type(self.salt) is not bytes or len(self.salt) != 32 or
                type(self.password_hash) is not bytes or len(self.password_hash) != 32):
            raise ValueError("invalid verifier record")

    @classmethod
    def create(cls, subject, password):
        _subject(subject)
        salt = secrets.token_bytes(32)
        return cls(subject, salt, _derive(password, salt))

    def verify(self, password):
        try:
            return hmac.compare_digest(self.password_hash, _derive(password, self.salt))
        except (ValueError, TypeError):
            return False

    def _encode(self):
        return json.dumps(dict(version=self.version, subject=self.subject,
                               salt=self.salt.hex(), hash=self.password_hash.hex()),
                          ensure_ascii=True).encode("ascii")

    @classmethod
    def _decode(cls, data):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result
        try:
            obj = json.loads(data, object_pairs_hook=unique)
            if type(obj) is not dict or set(obj) != {"version", "subject", "salt", "hash"}:
                raise ValueError()
            for name in ("salt", "hash"):
                value = obj[name]
                if (not isinstance(value, str) or len(value) != 64 or
                        any(c not in "0123456789abcdef" for c in value)):
                    raise ValueError()
            return cls(obj["subject"], bytes.fromhex(obj["salt"]),
                       bytes.fromhex(obj["hash"]), obj["version"])
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ValueError("invalid verifier record") from None


class VerifierStore:
    """Explicit path, no directory creation or permission repair; no cached record."""
    def __init__(self, path):
        self._path = Path(path)

    def _directory(self):
        fd = os.open(self._path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o7077:
                raise ValueError("private owner directory required")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _read(self, directory):
        fd = os.open(self._path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) & 0o7177 or info.st_nlink != 1 or
                    info.st_size > MAX_RECORD_BYTES):
                raise ValueError("invalid verifier file")
            data = stream.read(MAX_RECORD_BYTES + 1)
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError("invalid verifier file")
        return OwnerVerifier._decode(data)

    def read(self):
        directory = self._directory()
        try:
            return self._read(directory)
        finally:
            os.close(directory)

    @staticmethod
    def _write(directory, name, record):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(record._encode())
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            os.unlink(name, dir_fd=directory)
            raise

    def bootstrap(self, subject, password):
        record = OwnerVerifier.create(subject, password)
        directory = self._directory()
        try:
            self._write(directory, self._path.name, record)
            os.fsync(directory)
        finally:
            os.close(directory)
        return record

    def rotate(self, old_password, new_password):
        """Caller must revoke sessions, including after uncertain durability errors."""
        directory = self._directory()
        temporary = None
        try:
            previous = self._read(directory)
            if not previous.verify(old_password):
                raise ValueError("credential operation denied")
            record = OwnerVerifier.create(previous.subject, new_password)
            name = ".verifier-" + secrets.token_hex(16)
            self._write(directory, name, record)
            temporary = name
            os.replace(name, self._path.name, src_dir_fd=directory, dst_dir_fd=directory)
            temporary = None
            os.fsync(directory)
            return record
        finally:
            try:
                if temporary is not None:
                    os.unlink(temporary, dir_fd=directory)
            finally:
                os.close(directory)


class LoginService:
    """One configured identity, mode and scope; bounded process-local admission.

    Returns a SessionGrant or None for any admission failure. No client identity
    table, IP inference, persistent counters or cross-process synchronization.
    """
    def __init__(self, store, sessions, *, subject, mode, scope,
                 max_attempts=5, window=60, clock=time.monotonic):
        _subject(subject)
        _subject(scope)
        if (mode not in ("bearer", "cookie") or type(max_attempts) is not int or
                max_attempts < 1 or isinstance(window, bool) or
                not isinstance(window, (int, float)) or not math.isfinite(window) or window <= 0):
            raise ValueError("invalid login configuration")
        self._store, self._sessions = store, sessions
        self._subject, self._mode, self._scope = subject, mode, scope
        self._limit, self._window, self._clock = max_attempts, window, clock
        self._start, self._last, self._attempts = None, float("-inf"), 0
        self._lock = threading.RLock()

    def _admit(self):
        now = self._clock()
        if not math.isfinite(now) or now < self._last:
            return False
        self._last = now
        if self._start is None or now - self._start >= self._window:
            self._start, self._attempts = now, 0
        if self._attempts >= self._limit:
            return False
        self._attempts += 1
        return True

    def login(self, password):
        with self._lock:
            try:
                if not self._admit():
                    return None
                record = self._store.read()
                if record.subject != self._subject or not record.verify(password):
                    return None
                return self._sessions.issue(self._subject, mode=self._mode, scope=self._scope)
            except (ValueError, TypeError, OSError):
                return None

    def rotate(self, old_password, new_password):
        """Same admission budget as login; revokes this subject in every scope."""
        with self._lock:
            try:
                if not self._admit() or self._store.read().subject != self._subject:
                    return False
                self._store.rotate(old_password, new_password)
                return True
            except (ValueError, TypeError, OSError):
                return False
            finally:
                # Even a post-replace fsync failure must not leave old sessions live.
                self._sessions.revoke_all(self._subject)
