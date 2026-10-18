"""Real loopback transport tests. All credentials and events are synthetic."""
import contextlib
import http.client
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from assistant_hub.core.store import Store
from assistant_hub.local_server import LocalServer, main
from assistant_hub.security.credentials import VerifierStore

SYNTHETIC_PASSWORD = "synthetic-test-owner-only"


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.verifier = self.root / "owner.json"
        self.db = self.root / "hub.sqlite3"
        VerifierStore(self.verifier).bootstrap("owner", SYNTHETIC_PASSWORD)
        self.opener = build_opener(ProxyHandler({}))
        self.start()
        self.token = None

    def start(self):
        self.server = LocalServer(self.verifier, self.db, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.url = self.server.origin

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop()
        self.temp.cleanup()

    def request(self, path, body=None, *, method=None, origin=True, headers=None, raw=None):
        h = {}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        if origin:
            h["Origin"] = self.url if origin is True else origin
        data = None
        if body is not None:
            h["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if raw is not None:
            data = raw
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        req = Request(self.url + path, data=data, headers=h, method=method)
        try:
            response = self.opener.open(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read()
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
            if method != "HEAD" and response.headers.get_content_type() == "application/json":
                payload = json.loads(payload)
            return response.status, payload

    def login(self):
        code, data = self.request("/api/login", {"password": SYNTHETIC_PASSWORD})
        self.assertEqual(code, 200)
        self.token = data["token"]
        return self.token

    def collect(self, service="demo", account="demo-one"):
        return self.request("/api/collect", {"service": service, "account": account})

    def status(self, status="done", service="demo", account="demo-one", external_id="synthetic-1"):
        return self.request("/api/status", dict(service=service, account=account,
                                               external_id=external_id, status=status))

    def test_loopback_and_minimal_health(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(self.request("/healthz", origin=False), (200, {"label": "synthetic-only"}))

    def test_login_valid_and_scope(self):
        self.login()
        self.assertEqual(self.request("/api/session", origin=False),
                         (200, {"subject": "owner", "scope": "local-web"}))

    def test_calendar_manual_import_authenticated_atomic_and_local_only(self):
        from tests.test_calendar_import import calendar, event
        from assistant_hub.calendar_import import SERVICE, ACCOUNT
        raw = calendar(event("synthetic-uid"))
        self.assertEqual(self.request("/api/calendar/weeks")[0], 401)
        self.assertEqual(self.request("/api/calendar/changes", origin=False)[0], 401)
        self.assertEqual(self.request("/api/calendar/import", {"ical": raw})[0], 401)
        self.login()
        self.assertEqual(self.request("/api/calendar/import", {"ical": raw}, origin=False)[0], 403)
        self.assertEqual(self.request("/api/calendar/import", method="GET")[0], 404)
        self.assertEqual(self.request("/api/calendar/weeks")[1], [])
        self.assertEqual(self.request("/api/calendar/changes")[1], [])
        self.assertEqual(self.collect(SERVICE, ACCOUNT)[0], 400)  # never fetches outside data
        code, result = self.request("/api/calendar/import", {"ical": raw})
        self.assertEqual((code, result["week"], result["count"], result["added"]),
                         (200, "2026-10-12", 1, 1))
        week = self.request("/api/calendar/weeks")[1][0]
        self.assertEqual((week["week"], week["count"]), ("2026-10-12", 1))
        inbox = self.request("/api/inbox")[1]
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["attributes"]["time_local"], "11:20–12:50")
        self.assertEqual(inbox[0]["status"], "new")
        self.assertEqual(self.request("/api/calendar/import", {"ical": raw})[1]["added"], 0)
        self.assertEqual(self.request("/api/calendar/import", {"ical": raw})[1]["changed"], 0)
        self.assertEqual(self.request("/api/calendar/changes")[1], [])
        self.assertEqual(self.status("done", SERVICE, ACCOUNT, inbox[0]["external_id"])[0], 200)
        newer = calendar(event("synthetic-uid", title="Updated class"))
        self.assertEqual(self.request("/api/calendar/import", {"ical": newer})[1]["changed"], 1)
        edited = self.request("/api/inbox")[1]
        self.assertEqual(edited[0]["title"], "Updated class")
        self.assertEqual(edited[0]["status"], "done")
        history = self.request("/api/calendar/changes", origin=False)[1]
        self.assertEqual(len(history), 1)
        self.assertEqual((history[0]["kind"], history[0]["week"]), ("updated", "2026-10-12"))
        self.assertEqual(history[0]["before"]["title"], "Synthetic lecture")
        self.assertEqual(history[0]["after"]["title"], "Updated class")
        self.assertEqual(self.request("/api/calendar/changes", origin="https://foreign.example")[0], 403)

    def test_calendar_rejects_oversize_recurring_or_wrong_shape_without_writes(self):
        from tests.test_calendar_import import calendar, event
        self.login()
        good = calendar(event("uid"))
        for bad in (
            {"ical": ""},
            {"ical": "something else"},
            {"ical": good.replace("END:VEVENT", "RRULE:FREQ=WEEKLY\\r\\nEND:VEVENT")},
            {"ical": good, "remote_url": "https://university.example/"},
            {"ical": 42},
            {"ical": good + "x" * 100000},
        ):
            with self.subTest(bad=tuple(bad)):
                self.assertEqual(self.request("/api/calendar/import", bad)[0], 400)
        self.assertEqual(self.request("/api/calendar/weeks")[1], [])
        self.assertEqual(self.request("/api/inbox")[1], [])

    def test_wrong_and_invalid_passwords_generic(self):
        for value in ("short", "wrong-synthetic-password", "", 42, None):
            code, data = self.request("/api/login", {"password": value})
            self.assertIn(code, (400, 401))
            self.assertNotIn("token", data)
            if value:
                self.assertNotIn(str(value), str(data))

    def test_login_rate_budget(self):
        for _ in range(5):
            self.assertEqual(self.request("/api/login", {"password": "synthetic-wrong-password"})[0], 401)
        self.assertEqual(self.request("/api/login", {"password": SYNTHETIC_PASSWORD})[0], 401)

    def test_gets_without_auth(self):
        for path in ("/api/inbox", "/api/services", "/api/session", "/api/calendar/changes"):
            self.assertEqual(self.request(path, origin=False)[0], 401)

    def test_get_without_origin_with_token(self):
        self.login()
        self.assertEqual(self.request("/api/inbox", origin=False), (200, []))
        bindings = self.request("/api/services", origin=False)[1]
        self.assertEqual(len(bindings), 5)
        self.assertIn({"service": "local-calendar", "account": "weekly-ics",
                       "capabilities": [], "synthetic": False}, bindings)

    def test_get_foreign_origin_rejected(self):
        self.login()
        self.assertEqual(self.request("/api/inbox", origin="http://foreign.invalid")[0], 403)

    def test_all_posts_require_exact_origin(self):
        self.login()
        for origin in (False, "http://foreign.invalid", "null"):
            for path, body in (("/api/login", {"password": SYNTHETIC_PASSWORD}),
                               ("/api/collect", {"service": "demo", "account": "demo-one"}),
                               ("/api/status", {}), ("/api/logout", {})):
                self.assertEqual(self.request(path, body, origin=origin)[0], 403)
        self.assertEqual(self.request("/api/inbox")[1], [])

    def test_mutations_require_token(self):
        for path in ("/api/collect", "/api/status", "/api/logout"):
            self.assertEqual(self.request(path, {})[0], 401)

    def test_spoofed_host(self):
        self.login()
        for host in ("evil.invalid", "127.0.0.1:" + str(self.server.server_port), "localhost", self.server.host + ".evil"):
            self.assertEqual(self.request("/api/inbox", headers={"Host": host})[0], 403)

    def duplicate(self, name, value):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.putrequest("GET", "/api/inbox", skip_host=True)
        conn.putheader("Host", self.server.host)
        conn.putheader("Authorization", "Bearer " + self.token)
        conn.putheader("Origin", self.url)
        conn.putheader(name, value)
        conn.endheaders()
        response = conn.getresponse()
        code = response.status
        response.read()
        conn.close()
        return code

    def test_duplicate_sensitive_headers(self):
        self.login()
        for name, value in (("authorization", "Bearer " + self.token),
                            ("HOST", self.server.host), ("Origin", self.url),
                            ("origin", self.url)):
            self.assertEqual(self.duplicate(name, value), 400)

    def test_malformed_header_fails_closed(self):
        self.login()
        self.assertEqual(self.duplicate("Bad Name", "ignored"), 400)

    def test_cookie_and_auth_format_denied(self):
        self.login()
        self.assertEqual(self.request("/api/inbox", headers={"Cookie": "anything=x"})[0], 403)
        for value in ("bearer " + self.token, "Bearer  " + self.token, "Bearer invalid", "Basic abc"):
            self.assertEqual(self.request("/api/inbox", headers={"Authorization": value})[0], 401)

    def test_wrong_scope_and_mode_denied(self):
        for mode, scope in (("cookie", "local-web"), ("bearer", "other")):
            self.token = self.server.sessions.issue("owner", mode=mode, scope=scope).token
            self.assertEqual(self.request("/api/inbox")[0], 401)

    def test_oversize_json(self):
        code, data = self.request("/api/login", raw=b' ' * 16385)
        self.assertEqual(code, 400)
        self.assertEqual(data, {"error": "request denied"})

    def test_bad_json_shape_encoding_and_duplicate_keys(self):
        for data in (b'{', b'[]', b'null', b'{"password":true}', b'{"password":"a","extra":1}',
                     b'{"password":"a","password":"b"}', b'{"password":"\xff"}',
                     b'{"password":NaN}', b'[' * 1100):
            self.assertEqual(self.request("/api/login", raw=data)[0], 400)

    def test_content_type_and_transfer_encoding(self):
        self.assertEqual(self.request("/api/login", {}, headers={"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.request("/api/login", {}, headers={"Transfer-Encoding": "chunked"})[0], 403)

    def test_methods_and_unimplemented_endpoints(self):
        self.login()
        for path in ("/api/collect", "/api/status", "/api/logout", "/api/login"):
            self.assertEqual(self.request(path, method="GET")[0], 404)
        for method in ("PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
            self.assertEqual(self.request("/api/inbox", method=method)[0], 404)
        self.assertEqual(self.request("/api/send", {})[0], 404)
        self.assertEqual(self.request("/api/ingest", {})[0], 404)
        self.assertEqual(self.request("/api/inbox")[1], [])

    def test_only_explicit_synthetic_bindings(self):
        self.login()
        for service, account in (("gmail", "demo-one"), ("demo", "unknown"), ("bulletin", "demo-one")):
            self.assertEqual(self.collect(service, account)[0], 400)
        self.assertEqual(self.request("/api/inbox")[1], [])

    def test_dedup_cursors_and_no_dispatch(self):
        self.login()
        self.assertEqual(self.collect(), (200, {"inserted": 1}))
        self.assertEqual(self.collect(), (200, {"inserted": 0}))
        for expected in (2, 1, 0):
            self.assertEqual(self.collect("bulletin", "bulletin-alpha"), (200, {"inserted": expected}))
        store = Store(self.db)
        try:
            self.assertEqual(store.cursor("demo", "demo-one"), "done")
            self.assertEqual(store.cursor("bulletin", "bulletin-alpha"), "complete")
            self.assertEqual(len(store.inbox()), 4)
            self.assertEqual(store.intents(), [])
            self.assertEqual(len(store.audit()), 5)
        finally:
            store.close()

    def test_composite_identity_isolation_and_repeat_status(self):
        self.login()
        self.collect()
        self.collect(account="demo-two")
        self.collect("bulletin", "bulletin-alpha")
        for _ in range(2):
            self.assertEqual(self.status(), (200, {"status": "done"}))
        events = self.request("/api/inbox")[1]
        for event in events:
            expected = "done" if (event["service_id"], event["account_id"]) == ("demo", "demo-one") else "new"
            self.assertEqual(event["status"], expected)
        store = Store(self.db)
        try:
            self.assertNotIn("status", store.inbox()[0])
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM event_states").fetchone()[0], 1)
            audit = [a for a in store.audit() if a["kind"] == "status"]
            self.assertEqual(len(audit), 2)
            self.assertEqual(json.loads(audit[0]["data"]), {"status": "done", "actor": "owner"})
            self.assertEqual(store.intents(), [])
        finally:
            store.close()

    def test_status_validation_unknown_event(self):
        self.login()
        for status in ("approve", "send", "", 12, ["done"]):
            self.assertEqual(self.status(status)[0], 400)
        self.assertEqual(self.status()[0], 400)
        store = Store(self.db)
        try:
            self.assertEqual(store.audit(), [])
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM event_states").fetchone()[0], 0)
        finally:
            store.close()

    def test_all_allowed_statuses(self):
        self.login()
        self.collect()
        for status in ("review", "deferred", "done", "new"):
            self.assertEqual(self.status(status)[0], 200)
            self.assertEqual(self.request("/api/inbox")[1][0]["status"], status)

    def test_atomic_status_audit_failure(self):
        self.login()
        self.collect()
        store = Store(self.db)
        try:
            store.db.execute("CREATE TRIGGER fail_status BEFORE INSERT ON audit WHEN NEW.kind='status' BEGIN SELECT RAISE(ABORT, 'test'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                store.set_status("demo", "demo-one", "synthetic-1", "done", "owner")
            self.assertEqual(store.inbox_with_status()[0]["status"], "new")
            self.assertEqual(len(store.audit()), 1)
        finally:
            store.close()

    def test_persistence_restart_relogin(self):
        self.login()
        self.collect()
        self.status("deferred")
        old = self.token
        self.stop()
        self.start()
        self.assertEqual(self.request("/api/inbox")[0], 401)
        self.token = None
        self.login()
        self.assertNotEqual(old, self.token)
        self.assertEqual(self.request("/api/inbox")[1][0]["status"], "deferred")
        self.assertEqual(self.collect(), (200, {"inserted": 0}))

    def test_logout_replay(self):
        self.login()
        self.assertEqual(self.request("/api/logout", {})[0], 200)
        self.assertEqual(self.request("/api/inbox")[0], 401)
        self.assertEqual(self.collect()[0], 401)

    def test_traversal_and_private_paths(self):
        for path in ("/../README.md", "/%2e%2e/README.md", "/app.mjs/../owner.json",
                     "/owner.json", "/hub.sqlite3", "/.git/config", "/src/assistant_hub/core/store.py", "/i18n.mjs?locale=ru",
                     "//index.html", "/index.html?token=anything", "/%2findex.html", "/styles.css%00", "/calendar_overview.mjs?utm_source=chatgpt.com",
                     "/calendar_overview.mjs/../owner.json"):
            self.assertEqual(self.request(path)[0], 404, path)

    def test_static_headers_and_safe_ui(self):
        for path, marker in (("/", b"Synthetic demo"), ("/app.mjs", b"textContent"), ("/i18n.mjs", b"DEFAULT_LOCALE"),
                             ("/calendar_overview.mjs", b"currentCalendarWeek"),
                             ("/styles.css", b"@media")):
            code, data = self.request(path, origin=False)
            self.assertEqual(code, 200)
            self.assertIn(marker, data)
        source = (Path(__file__).parents[1] / "src/assistant_hub/local_web/app.mjs").read_text()
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "localStorage", "sessionStorage", "document.cookie", "eval("):
            self.assertNotIn(forbidden, source)
        self.assertIn("credentials: 'omit'", source)
        self.assertIn("redirect: 'error'", source)

    def test_static_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").symlink_to(self.verifier)
            with patch("assistant_hub.local_server.STATIC", root):
                code, data = self.request("/")
                self.assertEqual(code, 500)
                self.assertEqual(data, {"error": "request failed"})

    def test_startup_requires_private_verifier_explicit_paths(self):
        for verifier in (self.root / "missing.json", Path("relative.json")):
            with self.assertRaises((OSError, ValueError)):
                LocalServer(verifier, self.db, 0)
        with self.assertRaises(ValueError):
            LocalServer(self.verifier, Path("relative.db"), 0)
        with self.assertRaises(ValueError):
            LocalServer(self.verifier, self.verifier, 0)
        for mode in (0o755, 0o500):
            self.root.chmod(mode)
            try:
                with self.assertRaises(ValueError):
                    LocalServer(self.verifier, self.db, 0)
            finally:
                self.root.chmod(0o700)

    def test_bootstrap_interactive_twice_and_refuses_overwrite(self):
        path = self.root / "second.json"
        with patch("assistant_hub.local_server.getpass.getpass", side_effect=[SYNTHETIC_PASSWORD] * 2) as prompt:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                main(["bootstrap", "--verifier", str(path)])
            self.assertEqual(prompt.call_count, 2)
            self.assertNotIn(SYNTHETIC_PASSWORD, output.getvalue())
        original = path.read_bytes()
        with patch("assistant_hub.local_server.getpass.getpass", return_value=SYNTHETIC_PASSWORD):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["bootstrap", "--verifier", str(path)])
        self.assertEqual(path.read_bytes(), original)


class LocalPersistenceTests(unittest.TestCase):
    """Filesystem/SQLite checks independent of permission to open sockets."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "state.sqlite3"
        self.store = Store(self.path)
        from assistant_hub.core.demo import DemoAdapter
        for account in DemoAdapter.accounts:
            self.store.ingest("demo", account, DemoAdapter().poll(account, None))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_durable_state_and_account_isolation(self):
        self.store.set_status("demo", "demo-one", "synthetic-1", "done", "owner")
        self.store.close()
        self.store = Store(self.path)
        events = self.store.inbox_with_status()
        self.assertEqual([e["status"] for e in events], ["done", "new"])
        self.assertTrue(events[0]["updated_at"])
        self.assertNotIn("status", self.store.inbox()[0])
        self.assertEqual(self.store.intents(), [])
        audit = self.store.audit()[-1]
        self.assertEqual(audit["kind"], "status")
        self.assertEqual(json.loads(audit["subject"]), ["demo", "demo-one", "synthetic-1"])
        self.assertEqual(json.loads(audit["data"]), {"actor": "owner", "status": "done"})

    def test_audit_rollback_preserves_previous_status(self):
        self.store.set_status("demo", "demo-one", "synthetic-1", "review", "owner")
        before = self.store.audit()
        self.store.db.execute("CREATE TRIGGER fail BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.set_status("demo", "demo-one", "synthetic-1", "done", "owner")
        self.assertEqual(self.store.inbox_with_status()[0]["status"], "review")
        self.assertEqual(self.store.audit(), before)

    def test_parameterized_identity_and_unknown_event_do_not_write(self):
        before = self.store.audit()
        for service, account, external_id in (("demo", "unknown", "synthetic-1"),
                                              ("unknown", "demo-one", "synthetic-1"),
                                              ("demo", "demo-one", "' OR 1=1 --")):
            with self.assertRaises(ValueError):
                self.store.set_status(service, account, external_id, "done", "owner")
        self.assertEqual(self.store.audit(), before)
        self.assertEqual([e["status"] for e in self.store.inbox_with_status()], ["new", "new"])

    def test_existing_database_migration_preserves_events_cursors_audit(self):
        original = self.store.inbox()
        audit = self.store.audit()
        self.store.db.execute("DROP TABLE event_states")
        self.store.db.commit()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.inbox(), original)
        self.assertEqual(self.store.audit(), audit)
        self.assertEqual(self.store.cursor("demo", "demo-one"), "done")
        self.assertEqual([e["status"] for e in self.store.inbox_with_status()], ["new", "new"])
        for status in ("review", "deferred", "done", "new"):
            self.store.set_status("demo", "demo-one", "synthetic-1", status, "owner")
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM event_states").fetchone()[0], 1)

    def test_bootstrap_mismatch_and_missing_serve_verifier_fail_safely(self):
        verifier = self.root / "owner.json"
        with patch("assistant_hub.local_server.getpass.getpass", side_effect=[SYNTHETIC_PASSWORD, "synthetic-other-password"]):
            with contextlib.redirect_stderr(io.StringIO()) as output, self.assertRaises(SystemExit):
                main(["bootstrap", "--verifier", str(verifier)])
        self.assertFalse(verifier.exists())
        self.assertNotIn(SYNTHETIC_PASSWORD, output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["serve", "--verifier", str(verifier), "--db", str(self.path)])


if __name__ == "__main__":
    unittest.main()
