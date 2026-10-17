"""Explicit, single-owner GitHub App auth foundation; no adapter/server binding.

Injected signers and transports are trusted code. No credential exchange is made
until get_token() is explicitly called. This is not a vault or a production API.
"""
from base64 import b64decode, urlsafe_b64encode
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_RESPONSE = 16 * 1024
ERROR = 'GitHub App authentication failed'
_PERMISSIONS = ('issues', 'pull_requests', 'actions', 'metadata')


class GitHubAppError(ValueError):
    """Generic failure; never includes provider responses or credentials."""


@dataclass(frozen=True)
class AppInstallation:
    app_id: int
    installation_id: int
    repository: str
    private_key_path: Path = field(repr=False)

    def __post_init__(self):
        repo = self.repository
        if (type(self.app_id) is not int or self.app_id <= 0 or
                type(self.installation_id) is not int or self.installation_id <= 0 or
                not isinstance(repo, str) or len(repo) > 140):
            raise GitHubAppError(ERROR)
        parts = repo.split('/')
        if (len(parts) != 2 or
                re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', parts[0]) is None or
                re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', parts[1]) is None or
                '..' in parts[1] or parts[1] == '.' or
                not isinstance(self.private_key_path, Path) or
                not self.private_key_path.is_absolute() or
                '..' in self.private_key_path.parts):
            raise GitHubAppError(ERROR)
        object.__setattr__(self, 'repository', repo.lower())
        # Reject repository storage, including nested/worktree .git markers.
        if any((parent / '.git').is_file() or (parent / '.git' / 'HEAD').is_file()
               for parent in self.private_key_path.parents):
            raise GitHubAppError(ERROR)


@contextmanager
def _key_file(config):
    """Pin every directory, reject symlinks; never repair permissions or create keys."""
    directory = fd = None
    try:
        path = config.private_key_path
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
            info = os.fstat(directory)
            # Root-owned sticky temporary ancestry is allowed; final parent is not.
            if (info.st_uid not in (0, os.geteuid()) or
                    (info.st_mode & 0o022 and not
                     (info.st_uid == 0 and info.st_mode & stat.S_ISVTX))):
                raise ValueError()
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError()
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or
                not 1 <= info.st_size <= 32768):
            raise ValueError()
        yield fd
    except Exception:
        raise GitHubAppError(ERROR) from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory is not None:
            os.close(directory)


def _rsa_pem(fd):
    """Recognize unencrypted PKCS#1 or RSA PKCS#8; OpenSSL validates full key."""
    data = os.read(fd, 32769)
    lines = data.strip().splitlines()
    if len(lines) < 3:
        raise ValueError()
    label = lines[0]
    rsa_label = b'-----BEGIN ' + b'RSA PRIVATE KEY' + b'-----'
    pkcs8_label = b'-----BEGIN ' + b'PRIVATE KEY' + b'-----'
    if label not in (rsa_label, pkcs8_label):
        raise ValueError()
    if lines[-1] != label.replace(b'BEGIN', b'END'):
        raise ValueError()
    der = b64decode(b''.join(lines[1:-1]), validate=True)
    if label == pkcs8_label:
        # Version INTEGER followed by rsaEncryption AlgorithmIdentifier. Limit
        # inspection to the envelope, before the private-key OCTET STRING.
        offset = 2 + (der[1] & 127) if der[1] & 128 else 2
        if der[offset:offset + 18] != bytes.fromhex('020100300d06092a864886f70d0101010500'):
            raise ValueError()
    if not der or der[0] != 0x30:
        raise ValueError()


class OpenSSLSigner:
    """Explicit absolute system executable; no PATH lookup or implicit default."""
    def __init__(self, executable):
        if not isinstance(executable, Path) or not executable.is_absolute():
            raise GitHubAppError(ERROR)
        self._executable = executable

    def __call__(self, config, signing_bytes):
        try:
            with _key_file(config) as fd:
                _rsa_pem(fd)
                result = subprocess.run(
                    [str(self._executable), 'dgst', '-sha256', '-sign',
                     str(config.private_key_path)], input=signing_bytes, shell=False,
                    timeout=6, capture_output=True, check=True)
                return result.stdout
        except Exception:
            raise GitHubAppError(ERROR) from None


def _now(clock):
    now = clock()
    if type(now) not in (int, float) or not math.isfinite(now) or not 60 <= now <= 253402300000:
        raise GitHubAppError(ERROR)
    return now


def _b64(data):
    return urlsafe_b64encode(data).rstrip(b'=')


@dataclass(frozen=True)
class AppJWT:
    value: str = field(repr=False)


def build_app_jwt(config, signer, clock=time.time):
    """Signer(config, bytes) must return an RSA SHA-256 signature; no default key."""
    try:
        if type(config) is not AppInstallation:
            raise ValueError()
        with _key_file(config):
            now = int(_now(clock))
            header = _b64(b'{"alg":"RS256","typ":"JWT"}')
            payload = _b64(json.dumps(dict(iat=now - 60, exp=now + 480,
                                          iss=config.app_id), separators=(',', ':')).encode('ascii'))
            signing = header + b'.' + payload
            signature = signer(config, signing)
            if not isinstance(signature, bytes) or not 1 <= len(signature) <= 16384:
                raise ValueError()
            return AppJWT((signing + b'.' + _b64(signature)).decode('ascii'))
    except Exception:
        raise GitHubAppError(ERROR) from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_token(url, method, headers, body):
    """Fixed-endpoint caller only; fresh no-proxy/no-cookie/no-redirect opener."""
    try:
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        request = Request(url, data=body, headers=headers, method=method)
        with opener.open(request, timeout=8) as response:
            return response.status, response.read(MAX_RESPONSE + 1)
    except Exception:
        raise GitHubAppError(ERROR) from None


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError()
        obj[key] = value
    return obj


@dataclass(frozen=True)
class InstallationToken:
    value: str = field(repr=False)
    expires_at: float


class InstallationTokenManager:
    """One immutable app/installation/repository binding per manager, memory only.

    clear/revoke forget local references; they do NOT revoke at GitHub or erase
    Python memory. No arbitrary URL from a response is ever followed.
    """
    def __init__(self, config, signer, transport=post_token, clock=time.time):
        if type(config) is not AppInstallation:
            raise GitHubAppError(ERROR)
        self._config = config
        self._signer = signer
        self._transport = transport
        self._clock = clock
        self._cached = None
        self._last_now = None
        self._lock = threading.RLock()

    def clear(self):
        with self._lock:
            self._cached = None

    revoke = clear

    def get_token(self):
        with self._lock:
            try:
                now = _now(self._clock)
                if self._last_now is not None and now < self._last_now:
                    raise ValueError()
                self._last_now = now
                if self._cached is not None and now < self._cached.expires_at - 90:
                    return self._cached
                self._cached = None
                jwt = build_app_jwt(self._config, self._signer, lambda: now)
                status, raw = self._transport(
                    f'https://api.github.com/app/installations/{self._config.installation_id}/access_tokens',
                    'POST', {'Accept': 'application/vnd.github+json',
                             'X-GitHub-Api-Version': '2026-03-10',
                             'Authorization': 'Bearer ' + jwt.value,
                             'Content-Type': 'application/json',
                             'User-Agent': 'assistant-hub-app-auth'},
                    json.dumps({'repositories': [self._config.repository.split('/')[1]],
                                'permissions': dict.fromkeys(_PERMISSIONS, 'read')},
                               separators=(',', ':')).encode('ascii'))
                if status != 201 or not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
                    raise ValueError()
                obj = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                token = obj['token']
                if (not isinstance(token, str) or not 16 <= len(token) <= 4096 or
                        re.fullmatch(r'[A-Za-z0-9_.\-]+', token) is None):
                    raise ValueError()
                expires = obj['expires_at']
                if (not isinstance(expires, str) or len(expires) > 40 or
                        re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)', expires) is None):
                    raise ValueError()
                expires = datetime.fromisoformat(expires.replace('Z', '+00:00')).timestamp()
                finished = _now(self._clock)
                if finished < now or not 60 < expires - finished <= 3700 or expires - now > 3700:
                    raise ValueError()
                self._last_now = finished
                if obj['permissions'] != dict.fromkeys(_PERMISSIONS, 'read'):
                    raise ValueError()
                repos = obj['repositories']
                if (not isinstance(repos, list) or len(repos) != 1 or
                        not isinstance(repos[0], dict) or
                        (not isinstance(repos[0].get('full_name'), str) or
                         not repos[0]['full_name'].isascii() or
                         repos[0]['full_name'].lower() != self._config.repository)):
                    raise ValueError()
                self._cached = InstallationToken(token, expires)
                return self._cached
            except Exception:
                self._cached = None
                raise GitHubAppError(ERROR) from None
