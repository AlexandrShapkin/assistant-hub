"""Synthetic auth contracts: no network, real keys or real OpenSSL process."""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from assistant_hub.security.github_app import (
    AppInstallation, GitHubAppError, InstallationTokenManager, MAX_RESPONSE,
    OpenSSLSigner, build_app_jwt, post_token)


class GitHubAppTests(unittest.TestCase):
    def setUp(self):
        # This sandbox maps /tmp to nobody and mounts an empty .git guard.
        # Model conventional root-owned sticky /tmp, without changing host files.
        real_fstat = os.fstat
        tmp_info = Path('/tmp').stat()
        def conventional_tmp(fd):
            info = real_fstat(fd)
            if (info.st_dev, info.st_ino) == (tmp_info.st_dev, tmp_info.st_ino):
                values = list(info)
                values[4] = 0
                return os.stat_result(values)
            return info
        patcher = patch('assistant_hub.security.github_app.os.fstat', side_effect=conventional_tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / 'synthetic-signing-fixture'
        self.path.write_bytes(b'not a key; trusted fake signer only')
        self.path.chmod(0o600)
        self.now = 1800000000.0
        self.config = AppInstallation(123, 456, 'owner/repo', self.path)
        self.calls = []
        self.signatures = []
        self.reply = self.response()
        self.status = 201
        self.manager = self.manager_for(self.config)

    def response(self, seconds=3600):
        return {'token': 'synthetic_token_not_a_credential',
                'expires_at': datetime.fromtimestamp(self.now + seconds, timezone.utc).isoformat(),
                'permissions': dict.fromkeys(('issues', 'pull_requests', 'actions', 'metadata'), 'read'),
                'repositories': [{'full_name': 'owner/repo'}]}

    def signer(self, config, data):
        self.signatures.append((config, data))
        return b'synthetic signature\xff'

    def transport(self, *args):
        self.calls.append(args)
        raw = self.reply if isinstance(self.reply, bytes) else json.dumps(self.reply).encode()
        return self.status, raw

    def manager_for(self, config):
        return InstallationTokenManager(config, self.signer, self.transport, lambda: self.now)

    def denied(self):
        with self.assertRaisesRegex(GitHubAppError, '^GitHub App authentication failed$') as raised:
            self.manager.get_token()
        self.assertIsNone(self.manager._cached)
        self.assertNotIn('synthetic_token', str(raised.exception))

    def test_ids_strict(self):
        for value in (0, -1, True, 1.5, '1', None):
            for args in ((value, 1), (1, value)):
                with self.subTest(args=args), self.assertRaises(GitHubAppError):
                    AppInstallation(*args, 'owner/repo', self.path)

    def test_repository_strict(self):
        for repo in ('owner', 'a/b/c', '/repo', '-a/b', 'a/b..c', 'a/.', 'a/é',
                     'a/b?x', 'a/b\n', 'a/' + 'b' * 101, 'a/b%20c', 'a/b:c'):
            with self.subTest(repo=repo), self.assertRaises(GitHubAppError):
                AppInstallation(1, 2, repo, self.path)
        self.assertEqual(AppInstallation(1, 2, 'Owner/Repo', self.path).repository, 'owner/repo')

    def test_absolute_path_required(self):
        for path in ('/tmp/a', Path('relative'), self.directory / '..' / 'key'):
            with self.assertRaises(GitHubAppError):
                AppInstallation(1, 2, 'a/b', path)

    def test_git_directory_forbidden(self):
        (self.directory / '.git').mkdir()
        (self.directory / '.git' / 'HEAD').write_text('ref: refs/heads/synthetic')
        with self.assertRaises(GitHubAppError):
            AppInstallation(1, 2, 'a/b', self.path)

    def test_immutable_and_redacted(self):
        with self.assertRaises(FrozenInstanceError):
            self.config.app_id = 9
        self.assertNotIn(str(self.path), repr(self.config))
        jwt = build_app_jwt(self.config, self.signer, lambda: self.now)
        self.assertNotIn(jwt.value, repr(jwt))
        token = self.manager.get_token()
        self.assertNotIn(token.value, repr(token))
        self.assertNotIn(token.value, repr(self.manager))

    def test_file_modes(self):
        for mode in (0o644, 0o400, 0o700, 0o660, 0o1600):
            self.path.chmod(mode)
            with self.subTest(mode=mode):
                self.denied()
        self.assertFalse(self.calls)

    def test_directory_modes(self):
        for mode in (0o755, 0o770, 0o1700):
            self.directory.chmod(mode)
            self.denied()
        self.directory.chmod(0o700)

    def test_file_symlink(self):
        target = self.directory / 'target'
        self.path.rename(target)
        self.path.symlink_to(target)
        self.denied()

    def test_parent_symlink(self):
        alias = self.directory / 'alias'
        alias.symlink_to(self.directory, target_is_directory=True)
        self.manager = self.manager_for(AppInstallation(1, 2, 'a/b', alias / self.path.name))
        self.denied()

    def test_intermediate_symlink(self):
        nested = self.directory / 'nested'
        nested.mkdir(mode=0o700)
        alias = self.directory / 'alias'
        alias.symlink_to(self.directory, target_is_directory=True)
        self.manager = self.manager_for(AppInstallation(1, 2, 'a/b', alias / 'nested' / 'key'))
        self.denied()

    def test_untrusted_ancestor(self):
        nested = self.directory / 'nested'
        nested.mkdir(mode=0o700)
        key = nested / 'fixture'
        key.write_bytes(b'fake')
        key.chmod(0o600)
        self.directory.chmod(0o777)
        self.manager = self.manager_for(AppInstallation(1, 2, 'a/b', key))
        self.denied()
        self.directory.chmod(0o700)

    def test_wrong_owner(self):
        real = os.fstat.side_effect
        def wrong(fd):
            info = real(fd)
            if info.st_ino == self.path.stat().st_ino:
                values = list(info)
                values[4] = os.geteuid() + 1
                return os.stat_result(values)
            return info
        with patch('assistant_hub.security.github_app.os.fstat', side_effect=wrong):
            self.denied()

    def test_hardlink_and_nonregular(self):
        os.link(self.path, self.directory / 'link')
        self.denied()
        self.path.unlink()
        self.path.mkdir(mode=0o600)
        self.denied()

    def test_jwt_claims_signature(self):
        jwt = build_app_jwt(self.config, self.signer, lambda: self.now).value
        header, payload, signature = jwt.split('.')
        decode = lambda part: base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))
        self.assertEqual(json.loads(decode(header)), {'alg': 'RS256', 'typ': 'JWT'})
        self.assertEqual(json.loads(decode(payload)), {'iat': int(self.now)-60,
                         'exp': int(self.now)+480, 'iss': 123})
        self.assertEqual(decode(signature), b'synthetic signature\xff')
        self.assertEqual(self.signatures[0][1], (header + '.' + payload).encode())
        self.assertNotIn('=', jwt)

    def test_signer_failure_redacted(self):
        def fail(*args):
            raise RuntimeError('synthetic_token_not_a_credential')
        self.manager = InstallationTokenManager(self.config, fail, self.transport, lambda: self.now)
        self.denied()
        self.assertFalse(self.calls)

    def test_exact_request(self):
        self.manager.get_token()
        url, method, headers, body = self.calls[0]
        self.assertEqual(url, 'https://api.github.com/app/installations/456/access_tokens')
        self.assertEqual(method, 'POST')
        self.assertEqual(headers, {'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10', 'Content-Type': 'application/json',
            'User-Agent': 'assistant-hub-app-auth',
            'Authorization': 'Bearer ' + build_app_jwt(self.config, self.signer, lambda: self.now).value})
        self.assertEqual(json.loads(body), {'repositories': ['repo'], 'permissions':
                         dict.fromkeys(('issues', 'pull_requests', 'actions', 'metadata'), 'read')})

    def test_http_failures(self):
        for status in (200, 301, 302, 307, 401, 403, 500):
            self.status = status
            self.denied()

    def test_transport_exception(self):
        def fail(*args):
            raise OSError('synthetic_token_not_a_credential')
        self.manager = InstallationTokenManager(self.config, self.signer, fail, lambda: self.now)
        self.denied()

    def test_invalid_json(self):
        for raw in (b'bad', b'\xff', b'[]', b'null', b'{"token":1,"token":2}',
                    b'{"permissions":{"issues":"read","issues":"write"}}', b'{"x":NaN}'):
            self.reply = raw
            self.denied()

    def test_oversize(self):
        self.reply = b' ' * (MAX_RESPONSE + 1)
        self.denied()

    def test_modern_installation_token_and_repo_case(self):
        self.reply = self.response()
        self.reply['token'] = 'ghs_12345_eyJhbGciOiJSUzI1NiJ9.e30.signature-part'
        self.reply['repositories'] = [{'full_name': 'OWNER/REPO'}]
        self.assertEqual(self.manager.get_token().value, self.reply['token'])

    def test_token_validation(self):
        for token in ('', 'short', 1, None, 'x' * 4097, 'x' * 20 + '\n'):
            self.reply['token'] = token
            self.denied()

    def test_required_fields(self):
        for key in self.response():
            self.reply = self.response()
            del self.reply[key]
            self.denied()

    def test_permissions_fail_closed(self):
        for permissions in ({}, {'issues': 'write'}, [], None):
            self.reply = self.response()
            self.reply['permissions'] = permissions
            self.denied()
        for change in ('missing', 'write', 'extra'):
            self.reply = self.response()
            if change == 'missing':
                del self.reply['permissions']['actions']
            elif change == 'write':
                self.reply['permissions']['actions'] = 'write'
            else:
                self.reply['permissions']['contents'] = 'read'
            self.denied()

    def test_repositories_fail_closed(self):
        for repos in ([], None, {}, [{}], [{'full_name': 'other/repo'}],
                      [{'full_name': 'owner/repo'}, {'full_name': 'owner/extra'}]):
            self.reply = self.response()
            self.reply['repositories'] = repos
            self.denied()

    def test_expiry_bounds(self):
        for seconds in (-1, 0, 60, 3701):
            self.reply = self.response(seconds)
            self.denied()
        for value in ('bad', '2027-01-01T00:00:00', None, 5):
            self.reply['expires_at'] = value
            self.denied()

    def test_cache_refresh_boundary(self):
        first = self.manager.get_token()
        self.now += 3509
        self.assertIs(self.manager.get_token(), first)
        self.assertEqual(len(self.calls), 1)
        self.now += 1
        self.reply = self.response()
        self.assertIsNot(self.manager.get_token(), first)
        self.assertEqual(len(self.calls), 2)

    def test_clear_and_revoke(self):
        for clear in (self.manager.clear, self.manager.revoke):
            first = self.manager.get_token()
            clear()
            self.assertIsNone(self.manager._cached)
            self.assertIsNot(self.manager.get_token(), first)

    def test_per_account_cache(self):
        first = self.manager.get_token()
        other = self.manager_for(AppInstallation(123, 789, 'owner/other', self.path))
        self.reply['repositories'] = [{'full_name': 'owner/other'}]
        self.assertIsNot(other.get_token(), first)
        self.assertIs(self.manager.get_token(), first)
        self.assertIn('/789/', self.calls[-1][0])

    def test_failure_erases_old_token(self):
        self.manager.get_token()
        self.now += 3510
        self.status = 500
        self.denied()

    def test_clock_rollback_and_nonfinite(self):
        self.manager.get_token()
        self.now -= 1
        self.denied()
        for now in (float('nan'), float('inf'), True, -1):
            self.now = now
            self.denied()

    def test_clock_skew_during_exchange(self):
        def skew(*args):
            self.now -= 10
            return self.transport(*args)
        self.manager = InstallationTokenManager(self.config, self.signer, skew, lambda: self.now)
        self.denied()

    def test_concurrent_single_exchange(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            tokens = list(pool.map(lambda _: self.manager.get_token(), range(16)))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(token is tokens[0] for token in tokens))

    def test_openssl_explicit_and_generic_failure(self):
        with self.assertRaises(GitHubAppError):
            OpenSSLSigner(Path('openssl'))
        # Mock PEM envelope recognition; never create an actual key or process.
        with patch('assistant_hub.security.github_app._rsa_pem'), patch(
                'assistant_hub.security.github_app.subprocess.run') as run:
            run.return_value.stdout = b'fake-signature'
            signer = OpenSSLSigner(Path('/usr/bin/openssl'))
            self.assertEqual(signer(self.config, b'jwt-signing-input'), b'fake-signature')
            run.assert_called_once_with(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(self.path)],
                input=b'jwt-signing-input', shell=False, timeout=6, capture_output=True, check=True)
            run.side_effect = subprocess.CalledProcessError(1, 'secret', stderr=b'secret')
            with self.assertRaisesRegex(GitHubAppError, '^GitHub App authentication failed$'):
                signer(self.config, b'jwt-signing-input')

    def test_default_signer_rejects_nonkey(self):
        with patch('assistant_hub.security.github_app.subprocess.run') as run:
            with self.assertRaises(GitHubAppError):
                OpenSSLSigner(Path('/usr/bin/openssl'))(self.config, b'input')
            run.assert_not_called()

    def test_transport_timeout_bound_no_proxy(self):
        with patch('assistant_hub.security.github_app.build_opener') as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.status = 201
            response.read.return_value = b'{}'
            self.assertEqual(post_token('https://api.github.com/app/installations/1/access_tokens',
                                       'POST', {}, b'{}'), (201, b'{}'))
            handlers = build.call_args.args
            self.assertEqual(handlers[0].proxies, {})
            self.assertIsNone(handlers[1].redirect_request(None, None, 302, '', {}, 'https://evil.test'))
            self.assertEqual(build.return_value.open.call_args.kwargs, {'timeout': 8})
            response.read.assert_called_once_with(MAX_RESPONSE + 1)


if __name__ == '__main__':
    unittest.main()
