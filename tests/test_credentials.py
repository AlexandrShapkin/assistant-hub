import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assistant_hub.security import SessionManager
from assistant_hub.security.credentials import LoginService, OwnerVerifier, VerifierStore

SYNTHETIC_PASSWORD_VALUE = 'synthetic-password-one'
SYNTHETIC_NEW_PASSWORD_VALUE = 'synthetic-password-two'


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'owner.json'
        self.store = VerifierStore(self.path)
        self.record = self.store.bootstrap('owner-test', SYNTHETIC_PASSWORD_VALUE)
        self.now = 100
        self.sessions = SessionManager(idle_timeout=5, clock=lambda: self.now)
        self.login = LoginService(self.store, self.sessions, subject='owner-test',
                                  mode='bearer', scope='api', max_attempts=3,
                                  window=10, clock=lambda: self.now)

    def authorize(self, grant):
        return self.sessions.authorize(grant.token, mode='bearer', scope='api')

    def write(self, data):
        self.path.write_bytes(data)

    def test_bootstrap_verify_reopen(self):
        self.assertTrue(VerifierStore(self.path).read().verify(SYNTHETIC_PASSWORD_VALUE))
        self.assertFalse(self.record.verify(SYNTHETIC_NEW_PASSWORD_VALUE))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(SYNTHETIC_PASSWORD_VALUE.encode(), self.path.read_bytes())
        with self.assertRaises(FileExistsError):
            self.store.bootstrap('owner-test', SYNTHETIC_NEW_PASSWORD_VALUE)

    def test_password_constraints(self):
        for password in ('short', ' ' * 12, 'x' * 1025, '😀' * 257, '\ud800' * 12, None):
            with self.subTest(kind=type(password).__name__):
                with self.assertRaises(ValueError):
                    OwnerVerifier.create('owner-test', password)
                self.assertFalse(self.record.verify(password))
        self.assertTrue(OwnerVerifier.create('owner-test', 'x' * 1024).verify('x' * 1024))

    def test_unicode_exact_no_normalization(self):
        password = 'é' * 12
        record = OwnerVerifier.create('owner-test', password)
        self.assertTrue(record.verify(password))
        self.assertFalse(record.verify('e\u0301' * 12))

    def test_distinct_salts_and_immutable(self):
        other = OwnerVerifier.create('owner-test', SYNTHETIC_PASSWORD_VALUE)
        self.assertNotEqual(self.record.salt, other.salt)
        self.assertNotEqual(self.record.password_hash, other.password_hash)
        with self.assertRaises(AttributeError):
            self.record.subject = 'other'
        for subject in ('', '   ', None):
            with self.assertRaises(ValueError):
                OwnerVerifier.create(subject, SYNTHETIC_PASSWORD_VALUE)

    def test_strict_schema(self):
        original = json.loads(self.path.read_bytes())
        variants = [dict(original, version=2), dict(original, version=True),
                    dict(original, salt='00'), dict(original, hash='Z' * 64),
                    dict(original, extra=1), dict(original, subject='  ')]
        for obj in variants:
            self.write(json.dumps(obj).encode())
            with self.assertRaises(ValueError):
                self.store.read()
        for data in (b'{', b'[]', b'\xff', b'{"version":1,"version":1}', b'x' * 4097):
            self.write(data)
            with self.assertRaises(ValueError):
                self.store.read()
            self.assertIsNone(self.login.login(SYNTHETIC_PASSWORD_VALUE))

    def test_symlink_and_bootstrap_symlink(self):
        target = self.path.with_name('target')
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            self.store.read()
        with self.assertRaises(OSError):
            self.store.bootstrap('owner-test', SYNTHETIC_PASSWORD_VALUE)
        self.assertTrue(VerifierStore(target).read().verify(SYNTHETIC_PASSWORD_VALUE))

    def test_permissions_and_nonregular(self):
        for mode in (0o644, 0o660, 0o700, 0o4600):
            self.path.chmod(mode)
            with self.assertRaises(ValueError):
                self.store.read()
        self.path.chmod(0o600)
        os.chmod(self.directory.name, 0o755)
        try:
            with self.assertRaises(ValueError):
                self.store.read()
            with self.assertRaises(ValueError):
                self.store.bootstrap('owner-test', SYNTHETIC_PASSWORD_VALUE)
        finally:
            os.chmod(self.directory.name, 0o700)
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        with self.assertRaises(ValueError):
            self.store.read()

    def test_parent_symlink_and_hardlink(self):
        alias = self.path.with_name('alias')
        os.link(self.path, alias)
        with self.assertRaises(ValueError):
            self.store.read()
        alias.unlink()
        alias.symlink_to(self.directory.name, target_is_directory=True)
        with self.assertRaises(OSError):
            VerifierStore(alias / 'owner.json').read()

    def test_failed_login_no_session_or_idle_refresh(self):
        grant = self.login.login(SYNTHETIC_PASSWORD_VALUE)
        self.now = 104
        self.assertIsNone(self.login.login(SYNTHETIC_NEW_PASSWORD_VALUE))
        self.assertEqual(len(self.sessions._sessions), 1)
        self.now = 105
        self.assertIsNone(self.authorize(grant))

    def test_lockout_and_recovery(self):
        for _ in range(3):
            self.assertIsNone(self.login.login(SYNTHETIC_NEW_PASSWORD_VALUE))
        with patch.object(self.store, 'read', side_effect=AssertionError('must not hash')):
            self.assertIsNone(self.login.login(SYNTHETIC_PASSWORD_VALUE))
        self.now = 110
        self.assertIsNotNone(self.login.login(SYNTHETIC_PASSWORD_VALUE))
        self.now = 109
        self.assertIsNone(self.login.login(SYNTHETIC_PASSWORD_VALUE))
        self.now = float('nan')
        self.assertIsNone(self.login.login(SYNTHETIC_PASSWORD_VALUE))

    def test_rotation_revokes_all_owner_scopes(self):
        grant = self.login.login(SYNTHETIC_PASSWORD_VALUE)
        browser = self.sessions.issue('owner-test', mode='cookie', scope='web')
        other = self.sessions.issue('other', mode='bearer', scope='api')
        self.assertTrue(self.login.rotate(SYNTHETIC_PASSWORD_VALUE, SYNTHETIC_NEW_PASSWORD_VALUE))
        self.assertIsNone(self.authorize(grant))
        self.assertIsNone(self.sessions.authorize(browser.token, mode='cookie', scope='web'))
        self.assertIsNotNone(self.authorize(other))
        self.assertFalse(self.store.read().verify(SYNTHETIC_PASSWORD_VALUE))
        self.assertIsNotNone(self.login.login(SYNTHETIC_NEW_PASSWORD_VALUE))

    def test_wrong_rotation_and_invalid_new_leave_record(self):
        before = self.path.read_bytes()
        self.assertFalse(self.login.rotate(SYNTHETIC_NEW_PASSWORD_VALUE, SYNTHETIC_PASSWORD_VALUE))
        self.assertFalse(self.login.rotate(SYNTHETIC_PASSWORD_VALUE, 'short'))
        self.assertEqual(self.path.read_bytes(), before)

    def test_atomic_replace_failure_cleanup(self):
        before = self.path.read_bytes()
        with patch('assistant_hub.security.credentials.os.replace', side_effect=OSError('synthetic failure')):
            self.assertFalse(self.login.rotate(SYNTHETIC_PASSWORD_VALUE, SYNTHETIC_NEW_PASSWORD_VALUE))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.store.read().verify(SYNTHETIC_PASSWORD_VALUE))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_write_fsync_failure_cleanup(self):
        with patch('assistant_hub.security.credentials.os.fsync', side_effect=OSError('synthetic failure')):
            self.assertFalse(self.login.rotate(SYNTHETIC_PASSWORD_VALUE, SYNTHETIC_NEW_PASSWORD_VALUE))
        self.assertTrue(self.store.read().verify(SYNTHETIC_PASSWORD_VALUE))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_post_replace_durability_failure_revokes(self):
        grant = self.login.login(SYNTHETIC_PASSWORD_VALUE)
        real = os.fsync
        def sync(fd):
            if os.fstat(fd).st_mode & 0o170000 == 0o040000:
                raise OSError('synthetic directory sync failure')
            real(fd)
        with patch('assistant_hub.security.credentials.os.fsync', side_effect=sync):
            self.assertFalse(self.login.rotate(SYNTHETIC_PASSWORD_VALUE, SYNTHETIC_NEW_PASSWORD_VALUE))
        self.assertIsNone(self.authorize(grant))
        self.assertTrue(self.store.read().verify(SYNTHETIC_NEW_PASSWORD_VALUE))

    def test_no_secrets_in_repr_or_errors_or_logs(self):
        import logging
        with patch.object(logging.Logger, '_log') as log:
            self.login.login(SYNTHETIC_NEW_PASSWORD_VALUE)
            with self.assertRaises(ValueError) as caught:
                OwnerVerifier.create('owner-test', 'short')
            log.assert_not_called()
        representation = repr((self.record, self.store, self.login, caught.exception))
        for secret in (SYNTHETIC_PASSWORD_VALUE, SYNTHETIC_NEW_PASSWORD_VALUE, self.record.salt.hex(), self.record.password_hash.hex()):
            self.assertNotIn(secret, representation)

    def test_subject_mode_scope_binding(self):
        grant = self.login.login(SYNTHETIC_PASSWORD_VALUE)
        identity = self.authorize(grant)
        self.assertEqual((identity.subject, identity.scope), ('owner-test', 'api'))
        self.assertIsNone(self.sessions.authorize(grant.token, mode='cookie', scope='api'))
        self.assertIsNone(self.sessions.authorize(grant.token, mode='bearer', scope='web'))
        wrong = LoginService(self.store, self.sessions, subject='other', mode='bearer', scope='api')
        self.assertIsNone(wrong.login(SYNTHETIC_PASSWORD_VALUE))
        cookie = LoginService(self.store, self.sessions, subject='owner-test', mode='cookie', scope='web')
        browser = cookie.login(SYNTHETIC_PASSWORD_VALUE)
        self.assertIsNotNone(browser.csrf)
        self.assertIsNotNone(self.sessions.authorize(browser.token, mode='cookie', scope='web',
                                                     csrf=browser.csrf, require_csrf=True))

    def test_limits_and_capacity_fail_closed(self):
        for options in ({'max_attempts': True}, {'window': float('inf')}, {'window': 0}):
            with self.assertRaises(ValueError):
                LoginService(self.store, self.sessions, subject='owner-test', mode='bearer', scope='api', **options)
        with patch.object(self.sessions, 'issue', side_effect=ValueError('capacity')):
            self.assertIsNone(self.login.login(SYNTHETIC_PASSWORD_VALUE))
