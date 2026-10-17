import hashlib
import unittest

from assistant_hub.security import RequestGuard, SessionManager


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.sessions = SessionManager(ttl=20, idle_timeout=5, max_sessions=3,
                                       clock=lambda: self.now)
        self.machine = self.sessions.issue('synthetic-user', mode='bearer', scope='api')
        self.browser = self.sessions.issue('synthetic-user', mode='cookie', scope='web')
        self.api = RequestGuard(self.sessions, mode='bearer', scope='api',
                                allowed_origins=('https://hub.example',))
        self.web = RequestGuard(self.sessions, mode='cookie', scope='web',
                                allowed_origins=('https://hub.example',))

    def headers(self, browser=False):
        base = [('Host', 'hub.example'), ('Origin', 'https://hub.example')]
        return base + ([('Cookie', '__Host-session=' + self.browser.token),
                        ('X-CSRF-Token', self.browser.csrf)] if browser else
                       [('Authorization', 'Bearer ' + self.machine.token)])

    def test_valid_identity_and_all_unsafe_methods(self):
        identity = self.api.authorize('GET', self.headers())
        self.assertEqual((identity.subject, identity.scope), ('synthetic-user', 'api'))
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'CUSTOM'):
            self.assertEqual(self.web.authorize(method, self.headers(True)).scope, 'web')
            self.assertIsNone(self.web.authorize(method, self.headers(True)[:-1]))
            self.assertIsNone(self.web.authorize(method, self.headers(True)[:-1] +
                                                [('X-CSRF-Token', 'x' * 43)]))
        self.assertIsNotNone(self.web.authorize('GET', self.headers(True)[:-1]))

    def test_anonymous_forged_and_malformed(self):
        for headers in ([], self.headers()[:2], None, {}, [('Host',)],
                        self.headers() + [('host', 'hub.example')],
                        self.headers() + [('X-Forwarded-Host', 'hub.example\r\n')]):
            self.assertIsNone(self.api.authorize('GET', headers))
        for token in ('', 'x' * 43, 'x' * 10000, '\n', self.machine.token + ' '):
            self.assertIsNone(self.api.authorize('GET', self.headers()[:2] +
                                                [('Authorization', 'Bearer ' + token)]))
        for method in ('get', '', 'POST\r\n', None):
            self.assertIsNone(self.api.authorize(method, self.headers()))

    def test_origin_host_no_fallback(self):
        for field in ('Host', 'Origin'):
            for value in ('', 'null', 'https://hub.example.evil', 'evil',
                          'https://hub.example/', 'https://hub.example:443'):
                headers = [(k, value if k == field else v) for k, v in self.headers()]
                self.assertIsNone(self.api.authorize('GET', headers))
            headers = [(k, v) for k, v in self.headers() if k != field]
            headers += [('X-Forwarded-Host', 'hub.example'),
                        ('Forwarded', 'host=hub.example;proto=https')]
            self.assertIsNone(self.api.authorize('GET', headers))

    def test_modes_scopes_and_mixed_credentials(self):
        self.assertIsNone(self.api.authorize('GET', self.headers(True)))
        self.assertIsNone(self.web.authorize('GET', self.headers()))
        self.assertIsNone(self.api.authorize('GET', self.headers() + self.headers(True)[2:]))
        self.assertIsNone(self.web.authorize('GET', self.headers(True) + self.headers()[2:]))
        for cookie in ('__Host-session=' + self.browser.token + '; x=y',
                       '__Host-session=' + self.browser.token + '; __Host-session=x'):
            self.assertIsNone(self.web.authorize('GET', self.headers(True)[:2] + [('Cookie', cookie)]))
        wrong = RequestGuard(self.sessions, mode='bearer', scope='web',
                             allowed_origins=('https://hub.example',))
        self.assertIsNone(wrong.authorize('GET', self.headers()))
        self.assertIsNone(self.sessions.authorize(self.browser.token, mode='bearer', scope='web'))

    def test_idle_absolute_expiry_and_failed_proofs_do_not_refresh(self):
        self.now = 104
        self.assertIsNone(self.web.authorize('POST', self.headers(True)[:-1]))
        self.now = 105
        self.assertIsNone(self.web.authorize('GET', self.headers(True)))
        self.assertIsNone(self.api.authorize('GET', self.headers()))
        grant = self.sessions.issue('synthetic-user', mode='bearer', scope='api')
        for now in (109, 113, 117, 121, 124):
            self.now = now
            self.assertIsNotNone(self.sessions.authorize(grant.token, mode='bearer', scope='api'))
        self.now = 125
        self.assertIsNone(self.sessions.authorize(grant.token, mode='bearer', scope='api'))

    def test_revocation_and_replay(self):
        self.assertTrue(self.sessions.revoke(self.machine.token))
        self.assertFalse(self.sessions.revoke(self.machine.token))
        self.assertIsNone(self.api.authorize('GET', self.headers()))
        self.sessions.revoke_all('other')
        self.assertIsNotNone(self.web.authorize('GET', self.headers(True)))
        self.sessions.revoke_all('synthetic-user')
        self.assertIsNone(self.web.authorize('GET', self.headers(True)))
        grant = self.sessions.issue('other', mode='bearer', scope='api')
        self.sessions.revoke_all()
        self.assertIsNone(self.sessions.authorize(grant.token, mode='bearer', scope='api'))

    def test_capacity_hash_only_and_redacted_repr(self):
        other = self.sessions.issue('other', mode='bearer', scope='api')
        self.assertNotEqual(other.token, self.machine.token)
        with self.assertRaises(ValueError):
            self.sessions.issue('other', mode='bearer', scope='api')
        key = hashlib.sha256(self.machine.token.encode()).digest()
        self.assertIn(key, self.sessions._sessions)
        for grant in (self.machine, self.browser):
            self.assertNotIn(grant.token, repr(self.sessions.__dict__))
            self.assertNotIn(grant.token, repr(grant))
        self.assertNotIn(self.browser.csrf, repr(self.sessions.__dict__))
        self.now = 105
        self.sessions.issue('other', mode='bearer', scope='api')
        self.assertEqual(len(self.sessions._sessions), 1)

    def test_localhost_and_empty_allowlist(self):
        for origin in ('http://hub.example', 'http://localhost.evil',
                       'https://user@hub.example', 'https://hub.example/path',
                       'https://hub.example:99999', 'https://hub.example#x'):
            with self.assertRaises(ValueError):
                RequestGuard(self.sessions, mode='bearer', scope='api',
                             allowed_origins=(origin,), allow_localhost_http=True)
        with self.assertRaises(ValueError):
            RequestGuard(self.sessions, mode='bearer', scope='api',
                         allowed_origins=('http://localhost:8080',))
        local = RequestGuard(self.sessions, mode='bearer', scope='api',
                             allowed_origins=('http://localhost:8080',),
                             allow_localhost_http=True)
        headers = [('Host', 'localhost:8080'), ('Origin', 'http://localhost:8080')] + self.headers()[2:]
        self.assertIsNotNone(local.authorize('POST', headers))
        empty = RequestGuard(self.sessions, mode='bearer', scope='api')
        self.assertIsNone(empty.authorize('GET', self.headers()))

    def test_clock_rollback_and_invalid_limits(self):
        self.now = 99
        self.assertIsNone(self.api.authorize('GET', self.headers()))
        self.now = 100
        self.assertIsNone(self.api.authorize('GET', self.headers()))
        for options in ({'ttl': 0}, {'idle_timeout': float('nan')}, {'max_sessions': True}):
            with self.assertRaises(ValueError):
                SessionManager(**options)
