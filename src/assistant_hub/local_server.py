"""Single-process, loopback-only synthetic browser application. No dispatch."""
import argparse
import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
from socketserver import TCPServer
import stat
import threading
import warnings

from .core.demo import BulletinAdapter, DemoAdapter
from .core.hub import Hub
from .core.registry import Binding, Registry
from .core.store import Store
from .security import RequestGuard, SessionManager
from .security.credentials import LoginService, VerifierStore

SCOPE = "local-web"
MAX_BODY = 16384
STATIC = Path(__file__).with_name("local_web")
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.mjs": ("app.mjs", "text/javascript; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8")}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
       "connect-src 'self'; img-src 'none'; font-src 'none'; object-src 'none'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; worker-src 'none'")


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("absolute path required")
    return path


def private_verifier(path):
    path = absolute(path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("trusted 0700 verifier directory required")
    finally:
        os.close(directory)
    return VerifierStore(path)


def headers_map(pairs):
    """Validate raw headers once for every route, preserving duplicate detection."""
    result = {}
    for index, (name, value) in enumerate(pairs):
        if (index >= 64 or re.fullmatch(r"[A-Za-z0-9-]{1,64}", name) is None or
                len(value) > 4096 or any(ord(c) < 32 or ord(c) > 126 for c in value)):
            raise ValueError("invalid headers")
        name = name.lower()
        if name in result:
            raise ValueError("duplicate header")
        result[name] = value
    return result


def reject_constant(value):
    raise ValueError("invalid JSON constant")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True

    def __init__(self, verifier, db, port=18770):
        verifier, self.db_path = absolute(verifier), absolute(db)
        if verifier.resolve() == self.db_path.resolve():
            raise ValueError("separate paths required")
        store = private_verifier(verifier)
        owner = store.read().subject  # Refuse startup without a trusted verifier.
        self.lock = threading.RLock()
        self.sessions = SessionManager()
        self.login = LoginService(store, self.sessions, subject=owner, mode="bearer", scope=SCOPE)
        self.registry = Registry()
        self.bindings = []
        for adapter in (DemoAdapter(), BulletinAdapter()):
            self.registry.enable(adapter, tuple(Binding(a, ("read",)) for a in adapter.accounts))
            self.bindings.extend((adapter.manifest.service_id, a) for a in adapter.accounts)
        initial = Store(self.db_path)
        initial.close()
        super().__init__(("127.0.0.1", port), Handler)
        self.host = f"localhost:{self.server_port}"
        self.origin = f"http://{self.host}"
        self.guard = RequestGuard(self.sessions, mode="bearer", scope=SCOPE,
                                  allowed_origins=(self.origin,), allow_localhost_http=True)

    def server_bind(self):
        # HTTPServer's default bind performs getfqdn(); avoid DNS entirely.
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        # Never emit exception traces, request targets, headers or secrets.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "AssistantHub"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"error": "request denied"})

    def reply(self, code, value, content_type="application/json; charset=utf-8"):
        data = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(data)

    def body(self, headers, keys):
        if headers.get("content-type") != "application/json":
            raise ValueError("invalid content type")
        length = headers.get("content-length", "")
        if not length.isascii() or not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
            raise ValueError("invalid body size")
        data = self.rfile.read(int(length))
        if len(data) != int(length):
            raise ValueError("incomplete body")
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                         parse_constant=reject_constant)
        if type(obj) is not dict or set(obj) != set(keys):
            raise ValueError("invalid object")
        if any(type(v) is not str or not v or len(v) > 1024 for v in obj.values()):
            raise ValueError("invalid fields")
        return obj

    def authorized(self, headers):
        # Bearer is not ambient browser authority. GET commonly has no Origin;
        # never synthesize one. POST always goes through strict RequestGuard.
        if self.command == "POST":
            return self.server.guard.authorize(self.command, self.headers.raw_items())
        auth = headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return None
        return self.server.sessions.authorize(auth[7:], mode="bearer", scope=SCOPE)

    def handle_request(self):
        try:
            # Serialize authorization, revocation and SQLite work; each request
            # owns its connection, so no connection crosses thread boundaries.
            with self.server.lock:
                self.route()
        except (ValueError, KeyError, UnicodeError, RecursionError):
            self.reply(400, {"error": "request denied"})
        except Exception:
            self.reply(500, {"error": "request failed"})

    def route(self):
        if self.requestline.split()[1] != self.path:
            self.reply(404, {"error": "request denied"})
            return
        if self.headers.defects:
            raise ValueError("malformed headers")
        h = headers_map(self.headers.raw_items())
        if (h.get("host") != self.server.host or "cookie" in h or
                "transfer-encoding" in h or
                ("origin" in h and h["origin"] != self.server.origin)):
            self.reply(403, {"error": "request denied"})
            return
        if self.command == "GET":
            if "content-length" in h:
                raise ValueError("unexpected body")
            if self.path == "/healthz":
                self.reply(200, {"label": "synthetic-only"})
                return
            if self.path in ASSETS:
                name, content_type = ASSETS[self.path]
                directory = os.open(STATIC, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                    with os.fdopen(fd, "rb") as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            raise ValueError("invalid asset")
                        data = stream.read()
                finally:
                    os.close(directory)
                self.reply(200, data, content_type)
                return
        routes = {"GET": {"/api/inbox", "/api/services", "/api/session"},
                  "POST": {"/api/login", "/api/collect", "/api/status", "/api/logout"}}
        if self.path not in routes.get(self.command, set()):
            self.reply(404, {"error": "request denied"})
            return
        if self.command == "POST" and h.get("origin") != self.server.origin:
            self.reply(403, {"error": "request denied"})
            return
        if self.path == "/api/login":
            if "authorization" in h:
                raise ValueError("unexpected authorization")
            grant = self.server.login.login(self.body(h, ("password",))["password"])
            self.reply(200 if grant else 401, {"token": grant.token} if grant else {"error": "login denied"})
            return
        identity = self.authorized(h)
        if identity is None:
            self.reply(401, {"error": "request denied"})
            return
        if self.path == "/api/session":
            self.reply(200, {"subject": identity.subject, "scope": identity.scope})
        elif self.path == "/api/services":
            self.reply(200, [{"service": s, "account": a, "capabilities": ["read"],
                              "synthetic": True} for s, a in self.server.bindings])
        elif self.path == "/api/logout":
            self.body(h, ())
            self.server.sessions.revoke(h["authorization"][7:])
            self.reply(200, {"logged_out": True})
        else:
            store = Store(self.server.db_path)
            try:
                if self.path == "/api/inbox":
                    self.reply(200, store.inbox_with_status())
                elif self.path == "/api/collect":
                    obj = self.body(h, ("service", "account"))
                    if (obj["service"], obj["account"]) not in self.server.bindings:
                        raise ValueError("synthetic binding required")
                    inserted = Hub(self.server.registry, store).collect(obj["service"], obj["account"])
                    self.reply(200, {"inserted": inserted})
                else:
                    obj = self.body(h, ("service", "account", "external_id", "status"))
                    store.set_status(**obj, actor=identity.subject)
                    self.reply(200, {"status": obj["status"]})
            finally:
                store.close()

    do_GET = handle_request
    do_POST = handle_request
    do_HEAD = handle_request
    do_OPTIONS = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request
    do_PATCH = handle_request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--verifier", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--verifier", required=True)
    serve.add_argument("--db", required=True)
    serve.add_argument("--port", type=int, default=18770)
    args = parser.parse_args(argv)
    try:
        verifier = absolute(args.verifier)
        if args.command == "bootstrap":
            store = private_verifier(verifier)
            # Refuse getpass's fallback to potentially echoed standard input.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                first = getpass.getpass("Owner password: ")
                second = getpass.getpass("Repeat password: ")
            if first != second:
                raise ValueError("password mismatch")
            store.bootstrap("owner", first)
            print("Owner verifier created.")
        else:
            if not 1 <= args.port <= 65535:
                raise ValueError("invalid port")
            with LocalServer(verifier, args.db, args.port) as server:
                print(f"Synthetic-only application: {server.origin}", flush=True)
                server.serve_forever()
    except (OSError, ValueError, sqlite3.Error, EOFError, getpass.GetPassWarning):
        parser.exit(1, "Local operation refused; check private paths and configuration.\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
