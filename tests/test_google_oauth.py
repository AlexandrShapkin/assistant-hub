"""Owner-only Google Desktop OAuth: offline simulated browser and token server."""
import json
import os
from pathlib import Path
import queue
import stat
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import build_opener, ProxyHandler, Request

from assistant_hub.google_oauth import (
    AUTH_URI, SCOPES, authorization_url, pkce_pair,
    load_desktop_client, authorized_tokens, read_private, write_private,
    authorize_with_browser, refresh_access_token, load_refresh_grant,
    main,
)

CLIENT_ID = "1234567890123-abcxyz.apps.googleusercontent.com"
FAKE_SECRET = "synthetic-desktop-client"
REFRESH = "synthetic-private-refresh-token"
ACCESS = "synthetic-ephemeral-access-token"


def response(refresh=REFRESH):
    return {"token_type": "Bearer", "access_token": ACCESS,
            "refresh_token": refresh, "scope": " ".join(SCOPES), "expires_in": 3600}


class GoogleOAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        os.chmod(self.dir, 0o700)
        self.client_file = self.dir / 'client.json'
        self.token_file = self.dir / 'grant.json'
        client = {"installed": {"client_id": CLIENT_ID, "client_secret": FAKE_SECRET,
                                "auth_uri": AUTH_URI,
                                "token_uri": "https://oauth2.googleapis.com/token"}}
        self.client_file.write_text(json.dumps(client))
        os.chmod(self.client_file, 0o600)
        self.client = load_desktop_client(self.client_file)

    def test_client_and_authorization_pkce_required(self):
        verifier, challenge = pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)
        self.assertEqual(len(challenge), 43)
        redirect = "http://127.0.0.1:18771/oauth2callback"
        params = parse_qs(urlsplit(authorization_url(CLIENT_ID, redirect,
                               challenge, "s" * 42)).query)
        self.assertEqual(params["client_id"], [CLIENT_ID])
        self.assertEqual(params["scope"], [" ".join(SCOPES)])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["prompt"], ["consent"])
        self.assertEqual(params["access_type"], ["offline"])
        self.assertEqual(params["redirect_uri"], [redirect])
        self.assertNotIn("client_secret", params)
        for url in ("http://example.com/oauth2callback",
                    "https://127.0.0.1:18771/oauth2callback",
                    "http://127.0.0.1:18771/other",
                    "http://127.0.0.1:18771/oauth2callback?token=bad",
                    "http://user@127.0.0.1:18771/oauth2callback"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                authorization_url(CLIENT_ID, url, challenge, "s"*42)
        with self.assertRaises(ValueError):
            authorization_url(CLIENT_ID, redirect, "a" * 32, "s" * 42)
        with self.assertRaises(ValueError):
            authorization_url(CLIENT_ID, redirect, challenge, "short")

    def test_bounded_client_file_permission_and_structure(self):
        self.assertEqual(self.client["client_id"], CLIENT_ID)
        with self.assertRaises(OSError):
            load_desktop_client(self.dir / 'missing')
        os.chmod(self.client_file, 0o644)
        with self.assertRaises(ValueError):
            load_desktop_client(self.client_file)
        os.chmod(self.client_file, 0o600)
        self.client_file.write_text(json.dumps({"web": {"client_id": CLIENT_ID}}))
        with self.assertRaises(ValueError):
            load_desktop_client(self.client_file)
        self.client_file.write_text('{"installed": {}, "installed": {}}')
        with self.assertRaises(ValueError):
            load_desktop_client(self.client_file)
        self.client_file.write_text(json.dumps({"installed": {"client_id": CLIENT_ID,
                                 "auth_uri": "https://other.example"}}))
        with self.assertRaises(ValueError):
            load_desktop_client(self.client_file)
        os.chmod(self.dir, 0o755)
        with self.assertRaises(ValueError):
            load_desktop_client(self.client_file)

    def test_owner_file_atomic_and_symlink_protection(self):
        write_private(self.token_file, b'{"version":1}')
        self.assertEqual(stat.S_IMODE(self.token_file.stat().st_mode), 0o600)
        self.assertEqual(read_private(self.token_file), b'{"version":1}')
        write_private(self.token_file, b'{"version":2}')
        self.assertEqual(read_private(self.token_file), b'{"version":2}')
        os.chmod(self.token_file, 0o644)
        with self.assertRaises(ValueError):
            write_private(self.token_file, b'bad')
        with self.assertRaises(ValueError):
            read_private(self.token_file)
        self.token_file.unlink()
        self.token_file.symlink_to(self.client_file)
        with self.assertRaises(ValueError):
            write_private(self.token_file, b'bad')
        with self.assertRaises(OSError):
            read_private(self.token_file)
        with self.assertRaises(ValueError):
            write_private(self.dir / 'large', b'x' * 17000)
        with self.assertRaises(ValueError):
            write_private(Path('relative.txt'), b'x')

    def test_scope_check_and_grant_rotation(self):
        r = authorized_tokens(response(), CLIENT_ID)
        self.assertEqual(set(r["scopes"]), set(SCOPES))
        self.assertNotIn("access_token", r)
        write_private(self.token_file, json.dumps(r).encode())
        self.assertEqual(load_refresh_grant(self.token_file, CLIENT_ID)["refresh_token"], REFRESH)
        captured = []
        def exchange(payload):
            captured.append(payload)
            return {"token_type": "Bearer", "access_token": ACCESS,
                    "refresh_token": "synthetic-rotated-refresh-token",
                    "scope": " ".join(SCOPES)}
        self.assertEqual(refresh_access_token(self.client, self.token_file, exchange=exchange), ACCESS)
        self.assertEqual(load_refresh_grant(self.token_file, CLIENT_ID)["refresh_token"],
                         "synthetic-rotated-refresh-token")
        self.assertEqual(captured[0]["grant_type"], "refresh_token")
        self.assertEqual(captured[0]["client_secret"], FAKE_SECRET)
        self.assertNotIn(ACCESS, self.token_file.read_text())
        for data in (dict(response(), scope=SCOPES[0]),
                     dict(response(), token_type="MAC"),
                     dict(response(), refresh_token=""),
                     dict(response(), access_token="")):
            with self.subTest(data=data), self.assertRaises(ValueError):
                authorized_tokens(data, CLIENT_ID)
        with self.assertRaises(ValueError):
            load_refresh_grant(self.token_file, "other-client")
        with self.assertRaises(ValueError):
            refresh_access_token(self.client, self.token_file,
                                 exchange=lambda _: {"token_type": "Bearer",
                                                     "access_token": ACCESS,
                                                     "scope": "unauthorized"})

    def test_loopback_consent_success_and_rejects_attacker_state(self):
        announced = queue.Queue()
        exchanged = []
        outcome = []
        def exchange(form):
            exchanged.append(form)
            return response()
        def enroll():
            try:
                outcome.append(authorize_with_browser(
                    self.client, self.token_file, timeout=30,
                    announce=announced.put, exchange=exchange))
            except Exception as exc:
                outcome.append(exc)
        thread = threading.Thread(target=enroll, daemon=True)
        thread.start()
        oauth_url = announced.get(timeout=3).rsplit(' ', 1)[-1]
        parsed = urlsplit(oauth_url)
        self.assertEqual(parsed.scheme, 'https')
        values = parse_qs(parsed.query)
        redirect = values['redirect_uri'][0]
        state = values['state'][0]
        opener = build_opener(ProxyHandler({}))
        def callback(values, host=None):
            target = redirect + '?' + urlencode(values)
            req = Request(target, headers={'Host': host} if host else {})
            try:
                with opener.open(req, timeout=3) as response:
                    return response.status
            except HTTPError as e:
                e.close()
                return e.code
        self.assertEqual(callback({'state': 'wrong', 'code': 'synthetic-code'}), 400)
        self.assertEqual(callback({'state': state, 'code': 'synthetic-code'},
                                  host='attacker.example'), 403)
        self.assertEqual(callback({'state': state, 'code': 'synthetic-code'}), 200)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, [True])
        self.assertEqual(len(exchanged), 1)
        self.assertEqual(exchanged[0]['code'], 'synthetic-code')
        self.assertTrue(43 <= len(exchanged[0]['code_verifier']) <= 128)
        self.assertEqual(exchanged[0]['redirect_uri'], redirect)
        self.assertNotIn('access_token', self.token_file.read_text())
        self.assertNotIn('code_verifier', self.token_file.read_text())
        self.assertEqual(load_refresh_grant(self.token_file, CLIENT_ID)['refresh_token'],
                         REFRESH)

    def test_cli_check_never_authorizes(self):
        self.assertEqual(main(["--client", str(self.client_file),
                               "--tokens", str(self.token_file), "--check"]), 0)
        self.assertFalse(self.token_file.exists())


if __name__ == "__main__":
    unittest.main()
