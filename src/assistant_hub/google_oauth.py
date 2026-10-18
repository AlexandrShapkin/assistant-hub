"""Explicit desktop PKCE enrollment for Google Calendar, read-only.

Does not run from the localhost web server, and never has access to the
independently authorized ChatGPT connection. Tokens stay in owner-only files.
"""
from base64 import urlsafe_b64encode
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
# Google still includes this older, official auth_uri in downloaded Desktop JSON.
DESKTOP_JSON_AUTH_URIS = (AUTH_URI, "https://accounts.google.com/o/oauth2/auth")
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
)
GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.metadata",)


def _validated_scopes(value):
    if value not in (SCOPES, GMAIL_SCOPES):
        raise ValueError("unsupported Google read-only consent scopes")
    return value


CLIENT_RE = re.compile(r"[A-Za-z0-9._-]{10,200}\.apps\.googleusercontent\.com")
MAX_RESPONSE = 16_384


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _parse_json(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
        raise ValueError("invalid OAuth JSON size")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(value, dict):
        raise ValueError("invalid OAuth JSON")
    return value


def _private_dir(path):
    if not isinstance(path, (str, Path)):
        raise ValueError("absolute private path required")
    path = Path(path)
    if not path.is_absolute() or path.name in ("", ".", ".."):
        raise ValueError("absolute private path required")
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(directory)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(directory)
        raise ValueError("private OAuth directory must be owner-only")
    return path, directory


def read_private(path, max_bytes=MAX_RESPONSE):
    name, parent = _private_dir(path)
    try:
        fd = os.open(name.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > max_bytes):
                raise ValueError("untrusted OAuth file")
            with os.fdopen(fd, "rb", closefd=False) as inp:
                result = inp.read(max_bytes + 1)
            if len(result) > max_bytes:
                raise ValueError("oversized OAuth file")
            return result
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def write_private(path, data):
    """Atomic, owner-only replacement; refuse symlink or insecure old file."""
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_RESPONSE:
        raise ValueError("invalid private OAuth payload")
    name, parent = _private_dir(path)
    temporary = ".oauth-" + secrets.token_hex(16)
    try:
        try:
            old = os.stat(name.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            old = None
        if old is not None and (not stat.S_ISREG(old.st_mode)
                                or old.st_uid != os.geteuid()
                                or stat.S_IMODE(old.st_mode) != 0o600):
            raise ValueError("unsafe OAuth target file")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as output:
                output.write(data)
                output.flush()
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, name.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def load_desktop_client(path):
    record = _parse_json(read_private(path))
    if set(record) != {"installed"} or not isinstance(record["installed"], dict):
        raise ValueError("Google Desktop OAuth client JSON required")
    client = record["installed"]
    identifier = client.get("client_id")
    if not isinstance(identifier, str) or not CLIENT_RE.fullmatch(identifier):
        raise ValueError("invalid Google Desktop client ID")
    if client.get("auth_uri") not in (None, *DESKTOP_JSON_AUTH_URIS):
        raise ValueError("invalid Google auth endpoint")
    if client.get("token_uri") not in (None, TOKEN_URI):
        raise ValueError("invalid Google token endpoint")
    secret = client.get("client_secret")
    if secret is not None and (not isinstance(secret, str) or
                               not 1 <= len(secret) <= 512 or
                               any(ord(c) < 33 or ord(c) > 126 for c in secret)):
        raise ValueError("invalid desktop client secret")
    return {"client_id": identifier, "client_secret": secret}


def pkce_pair():
    verifier = secrets.token_urlsafe(64)  # 86 unreserved characters.
    challenge = urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(client_id, redirect_uri, challenge, state, *, scopes=SCOPES):
    _validated_scopes(scopes)
    if not isinstance(client_id, str) or not CLIENT_RE.fullmatch(client_id):
        raise ValueError("invalid Google client")
    uri = urlsplit(redirect_uri)
    if (uri.scheme != "http" or uri.hostname != "127.0.0.1" or
            not uri.port or uri.netloc != "127.0.0.1:" + str(uri.port) or
            uri.username is not None or uri.password is not None or
            uri.path != "/oauth2callback" or uri.query or uri.fragment):
        raise ValueError("desktop loopback redirect required")
    if not isinstance(challenge, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge):
        raise ValueError("invalid PKCE challenge")
    if not isinstance(state, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state):
        raise ValueError("invalid OAuth state")
    parameters = {
        "client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": " ".join(scopes),
        "access_type": "offline", "prompt": "consent",
        "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return AUTH_URI + "?" + urlencode(parameters)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def post_token(form):
    """Fixed-Google-host verified TLS POST; no ambient proxy or redirect."""
    if not isinstance(form, dict) or any(not isinstance(v, str) for v in form.values()):
        raise ValueError("invalid OAuth request")
    payload = urlencode(form).encode("ascii")
    if len(payload) > 4096:
        raise ValueError("oversized OAuth request")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                          NoRedirect())
    request = Request(TOKEN_URI, data=payload, method="POST",
                      headers={"Accept": "application/json",
                               "Content-Type": "application/x-www-form-urlencoded",
                               "User-Agent": "assistant-hub-readonly-oauth/1"})
    try:
        with opener.open(request, timeout=12) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError("Google token endpoint refused request")
            raw = response.read(MAX_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise ValueError("Google token request failed") from None
    return _parse_json(raw)


def authorized_tokens(response, client_id, *, scopes=SCOPES):
    """Persist only refresh grant; never an access token or auth code."""
    _validated_scopes(scopes)
    if (not isinstance(response, dict) or
            not isinstance(response.get("token_type"), str) or
            response["token_type"].lower() != "bearer"):
        raise ValueError("OAuth bearer token required")
    granted_scopes = response.get("scope")
    if not isinstance(granted_scopes, str) or set(granted_scopes.split()) != set(scopes):
        raise ValueError("Google did not grant exactly the requested read-only scopes")
    refresh = response.get("refresh_token")
    access = response.get("access_token")
    if (not isinstance(refresh, str) or not 8 <= len(refresh) <= 4096 or
            not isinstance(access, str) or not 8 <= len(access) <= 4096):
        raise ValueError("refresh and access tokens required")
    return {"version": 1, "client_id": client_id,
            "refresh_token": refresh, "scopes": list(scopes)}


def authorize_with_browser(client, token_path, *, timeout=300, announce=print,
                           exchange=post_token, scopes=SCOPES):
    """Run only on the owner's interactive desktop; never inside public Hub."""
    _validated_scopes(scopes)
    if type(timeout) is not int or not 30 <= timeout <= 600:
        raise ValueError("invalid consent timeout")
    # Refuse consent before any browser interaction if token target is unsafe.
    token_name, token_directory = _private_dir(token_path)
    try:
        try:
            old = os.stat(token_name.name, dir_fd=token_directory, follow_symlinks=False)
        except FileNotFoundError:
            old = None
        if old is not None and (not stat.S_ISREG(old.st_mode)
                                or old.st_uid != os.geteuid()
                                or stat.S_IMODE(old.st_mode) != 0o600):
            raise ValueError("unsafe Google grant target")
    finally:
        os.close(token_directory)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    code_holder = []
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            expected_host = "127.0.0.1:" + str(self.server.server_port)
            if self.headers.get("Host") != expected_host:
                self.send_response(403)
                self.end_headers()
                return
            parsed = urlsplit(self.path)
            if parsed.path != "/oauth2callback" or parsed.fragment:
                self.send_response(404)
                self.end_headers()
                return
            try:
                pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True,
                                  max_num_fields=5)
                query = _unique(pairs)
                if (set(query) - {"state", "code", "scope", "iss"} or
                        ("iss" in query and query["iss"] != "https://accounts.google.com") or
                        query.get("state") != state or
                        not isinstance(query.get("code"), str) or
                        not re.fullmatch(r"[A-Za-z0-9_./~-]{1,2048}", query["code"])):
                    raise ValueError()
            except ValueError:
                self.send_response(400)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            code_holder.append(query["code"])
            content = b"Consent received. Return to the Assistant Hub setup terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

    with HTTPServer(("127.0.0.1", 0), Callback) as http:
        redirect = "http://127.0.0.1:" + str(http.server_port) + "/oauth2callback"
        url = authorization_url(client["client_id"], redirect, challenge, state, scopes=scopes)
        announce("Open in the same computer's browser: " + url)
        stop = time.monotonic() + timeout
        http.timeout = 1
        while not code_holder and time.monotonic() < stop:
            http.handle_request()
        if not code_holder:
            raise TimeoutError("Google consent timed out")
    form = {"grant_type": "authorization_code", "code": code_holder[0],
            "client_id": client["client_id"], "code_verifier": verifier,
            "redirect_uri": redirect}
    if client.get("client_secret"):
        form["client_secret"] = client["client_secret"]
    response = exchange(form)
    vault = authorized_tokens(response, client["client_id"], scopes=scopes)
    write_private(token_path, json.dumps(vault, sort_keys=True).encode("utf-8"))
    return True


def load_refresh_grant(path, expected_client_id, *, scopes=SCOPES):
    _validated_scopes(scopes)
    value = _parse_json(read_private(path))
    if (set(value) != {"version", "client_id", "refresh_token", "scopes"}
            or value["version"] != 1
            or value["client_id"] != expected_client_id
            or value["scopes"] != list(scopes)
            or not isinstance(value["refresh_token"], str)
            or not 8 <= len(value["refresh_token"]) <= 4096):
        raise ValueError("invalid private read-only OAuth grant")
    return value


def refresh_access_token(client, token_path, *, exchange=post_token, scopes=SCOPES):
    """A Google API caller gets ephemeral access token; files retain refresh only."""
    _validated_scopes(scopes)
    grant = load_refresh_grant(token_path, client["client_id"], scopes=scopes)
    form = {"grant_type": "refresh_token", "client_id": client["client_id"],
            "refresh_token": grant["refresh_token"]}
    if client.get("client_secret"):
        form["client_secret"] = client["client_secret"]
    result = exchange(form)
    if not isinstance(result, dict) or str(result.get("token_type", "")).lower() != "bearer":
        raise ValueError("OAuth refresh failed")
    value = result.get("access_token")
    if not isinstance(value, str) or not 8 <= len(value) <= 4096:
        raise ValueError("invalid Google access token")
    if "scope" in result and (
        not isinstance(result["scope"], str) or set(result["scope"].split()) != set(scopes)
    ):
        raise ValueError("Google refresh scopes changed")
    if "refresh_token" in result:
        updated = dict(grant)
        rotated = result["refresh_token"]
        if not isinstance(rotated, str) or not 8 <= len(rotated) <= 4096:
            raise ValueError("invalid rotated refresh token")
        updated["refresh_token"] = rotated
        write_private(token_path, json.dumps(updated, sort_keys=True).encode())
    return value


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Local owner-only Google Calendar OAuth enrollment")
    parser.add_argument("--client", required=True, help="private Google Desktop app client JSON")
    parser.add_argument("--tokens", required=True, help="0600 token vault in 0700 directory")
    parser.add_argument("--check", action="store_true", help="check local setup, never contact Google")
    args = parser.parse_args(argv)
    try:
        client = load_desktop_client(args.client)
        if args.check:
            print("Google Desktop client valid; read-only consent not started.")
            return 0
        authorize_with_browser(client, args.tokens)
        print("Private read-only Google grant saved; no calendars have been changed.")
        return 0
    except (ValueError, OSError, TimeoutError):
        parser.exit(1, "Google Calendar authorization failed; check private configuration.\n")


if __name__ == "__main__":
    raise SystemExit(main())
