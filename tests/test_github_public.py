"""Offline GitHub public snapshots and authenticated localhost integration."""
from contextlib import closing
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from assistant_hub.adapters.github_public import GitHubPublicAdapter, MAX_RESPONSE, NoRedirect, get_public
from assistant_hub.core.contracts import (PollError, PermanentPollError, RateLimitPollError,
                                         AuthenticationPollError, TransientPollError, ActionIntent)
from assistant_hub.core.hub import Hub
from assistant_hub.core.registry import Registry, Binding
from assistant_hub.core.store import Store


def fixtures():
    common = dict(number=1, updated_at='2026-10-17T01:00:00Z', title='Title', body='Body', state='open')
    issue = dict(common, html_url='https://github.com/owner/repo/issues/1')
    pull = dict(common, html_url='https://github.com/owner/repo/pull/1')
    run = dict(id=9, updated_at=common['updated_at'], name='CI', status='completed',
               conclusion='success', run_attempt=1, html_url='https://github.com/owner/repo/actions/runs/9')
    return [{'private': False, 'full_name': 'Owner/Repo'}, [issue], [pull], {'workflow_runs': [run]}]


class PublicTests(unittest.TestCase):
    def setUp(self):
        self.data = fixtures()
        self.calls = []
        self.adapter = GitHubPublicAdapter('Owner/Repo', self.transport)

    def transport(self, url):
        self.calls.append(url)
        index = (len(self.calls) - 1) % 4
        value = self.data[index]
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    def poll(self):
        return self.adapter.poll('owner/repo', None)

    def test_invalid_slugs(self):
        for slug in ('https://github.com/a/b', '../repo', 'a/..', 'a/b?x', 'a/b#x',
                     'a@b/c', 'a/b/c', 'a/é', 'a/b\n', '/b', 'a/', 'a/%2e', 'a/..b'):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                GitHubPublicAdapter(slug)

    def test_conversion(self):
        events = self.poll().events
        self.assertEqual([e.kind for e in events], ['github.issue', 'github.pull', 'github.workflow'])
        self.assertEqual(len({e.external_id for e in events}), 3)
        self.assertEqual(events[2].attributes['conclusion'], 'success')
        self.assertEqual(events[0].timestamp.utcoffset().total_seconds(), 0)
        self.assertTrue(all(e.account_id == 'owner/repo' for e in events))

    def test_fixed_endpoints(self):
        self.poll()
        self.assertEqual(self.calls, ['https://api.github.com/repos/owner/repo' + p for p in (
            '', '/issues?state=all&sort=updated&direction=desc&per_page=30',
            '/pulls?state=all&sort=updated&direction=desc&per_page=30', '/actions/runs?per_page=30')])

    def test_private(self):
        self.data[0]['private'] = True
        with self.assertRaises(PollError): self.poll()
        self.assertEqual(len(self.calls), 1)

    def test_metadata_mismatch(self):
        self.data[0]['full_name'] = 'other/repo'
        with self.assertRaises(PollError): self.poll()

    def test_missing_fields(self):
        for index, key in ((0, 'private'), (1, 'body'), (2, 'updated_at'), (3, 'conclusion')):
            self.data = fixtures(); self.calls.clear()
            target = self.data[index] if index == 0 else self.data[index][0] if index < 3 else self.data[3]['workflow_runs'][0]
            del target[key]
            with self.subTest(key=key), self.assertRaises(PollError): self.poll()

    def test_bad_json(self):
        for raw in (b'{', b'NaN', b'\xff', b'{"private":false,"private":false}', b'null'):
            self.calls.clear(); self.data[0] = raw
            with self.assertRaises(PollError): self.poll()

    def test_oversize(self):
        self.data[0] = b' ' * (MAX_RESPONSE + 1)
        with self.assertRaises(PollError): self.poll()

    def test_record_limit(self):
        self.data[1] *= 31
        with self.assertRaises(PollError): self.poll()

    def test_http_errors(self):
        for code, category in ((401, AuthenticationPollError), (403, RateLimitPollError),
                               (429, RateLimitPollError), (404, PermanentPollError),
                               (500, TransientPollError), (302, PermanentPollError)):
            self.calls.clear(); self.data[0] = HTTPError('url', code, 'private text', {}, None)
            with self.assertRaises(category) as error: self.poll()
            self.assertNotIn('private text', str(error.exception))
            self.assertEqual(len(self.calls), 1)

    def test_urls(self):
        for url in ('https://evil.test/owner/repo/issues/1', 'http://github.com/owner/repo/issues/1',
                    'https://github.com/other/repo/issues/1', 'https://github.com/owner/repo/issues/1?x',
                    'https://github.com@evil.test/owner/repo/issues/1'):
            self.calls.clear(); self.data[1][0]['html_url'] = url
            with self.assertRaises(PollError): self.poll()

    def test_safe_text(self):
        self.data[1][0]['title'] = '\x00\u202e<script>' + 'x' * 3000
        event = self.poll().events[0]
        self.assertLessEqual(len(event.title), 2400)
        self.assertNotIn('\x00', event.title)
        self.assertNotIn('\u202e', event.title)
        self.assertEqual(event.attributes['provenance'], 'github-public')

    def test_skip_issue_pr(self):
        self.data[1][0]['pull_request'] = {}
        self.assertEqual(len(self.poll().events), 2)

    def test_bad_timestamp(self):
        self.data[1][0]['updated_at'] = '2026-01-01'
        with self.assertRaises(PollError): self.poll()

    def test_scope_cursor(self):
        for account, cursor in (('other/repo', None), ('owner/repo', 'bad')):
            with self.assertRaises(PollError): self.adapter.poll(account, cursor)
        self.assertEqual(self.calls, [])

    def test_registration_dedup_updates_atomicity(self):
        registry = Registry(); registry.enable(self.adapter, (Binding('owner/repo', ('read',)),))
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'db')
            self.addCleanup(store.close)
            hub = Hub(registry, store)
            self.assertEqual(hub.collect('github-public', 'owner/repo'), 3)
            self.assertEqual(hub.collect('github-public', 'owner/repo'), 0)
            self.data[1][0]['updated_at'] = '2026-10-17T02:00:00Z'
            self.assertEqual(hub.collect('github-public', 'owner/repo'), 1)
            before = (store.inbox(), store.audit(), store.cursor('github-public', 'owner/repo'))
            self.data[3] = b'broken'
            with self.assertRaises(PollError): hub.collect('github-public', 'owner/repo')
            self.assertEqual(before, (store.inbox(), store.audit(), store.cursor('github-public', 'owner/repo')))
            intent = ActionIntent('github-public', 'owner/repo', 'reply', '1', 'x', 'test')
            self.assertEqual(hub.plan(intent).status, 'deny')

    def test_transport_contract(self):
        with patch('assistant_hub.adapters.github_public.build_opener') as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.status = 200; response.read.return_value = b'{}'
            self.assertEqual(get_public('https://api.github.com/repos/owner/repo'), b'{}')
            args, kwargs = build.return_value.open.call_args
            self.assertEqual(kwargs, {'timeout': 8})
            self.assertEqual(args[0].get_method(), 'GET')
            self.assertNotIn('Authorization', dict(args[0].header_items()))
            response.read.assert_called_once_with(MAX_RESPONSE + 1)

    def test_redirect_handler(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test'))

    def test_transport_oversize(self):
        with patch('assistant_hub.adapters.github_public.build_opener') as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b'x' * (MAX_RESPONSE + 1)
            with self.assertRaises(PollError): get_public('https://api.github.com/repos/owner/repo')

    def test_workflow_attempt_versions(self):
        before = self.poll().events[-1].external_id
        self.data[3]['workflow_runs'][0]['run_attempt'] = 2
        self.assertNotEqual(before, self.poll().events[-1].external_id)



class PublicServerTests(unittest.TestCase):
    def setUp(self):
        from assistant_hub.local_server import LocalServer
        from assistant_hub.security.credentials import VerifierStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.verifier, self.db = self.root / 'owner.json', self.root / 'db'
        VerifierStore(self.verifier).bootstrap('owner', 'synthetic-test-password')
        def fake_init(server, *args):
            server.server_port = 18770
        self.init_patch = patch('assistant_hub.local_server.ThreadingHTTPServer.__init__', fake_init)
        self.init_patch.start()
        self.addCleanup(self.init_patch.stop)
        self.server = LocalServer(self.verifier, self.db, 18770, 'owner/repo')

    def request(self, path, token=None, origin=True, method='POST'):
        from email.message import Message
        from assistant_hub.local_server import Handler
        handler = Handler.__new__(Handler)
        handler.server = self.server
        handler.command, handler.path = method, path
        handler.requestline = method + ' ' + path + ' HTTP/1.1'
        handler.headers = Message()
        handler.headers['Host'] = self.server.host
        if origin: handler.headers['Origin'] = self.server.origin
        if token: handler.headers['Authorization'] = 'Bearer ' + token
        handler.body = lambda *args: {'service': 'github-public', 'account': 'owner/repo'}
        with patch.object(handler, 'reply') as reply:
            handler.handle_request()
            return reply.call_args.args

    def test_public_authorization_and_errors(self):
        adapter = self.server.registry.get('github-public')
        with patch.object(adapter, 'poll', side_effect=PermanentPollError('sensitive text')) as poll:
            self.assertEqual(self.request('/api/collect')[0], 401)
            poll.assert_not_called()
            token = self.server.login.login('synthetic-test-password').token
            self.assertEqual(self.request('/api/collect', token, origin=False)[0], 403)
            poll.assert_not_called()
            services = self.request('/api/services', token, method='GET')[1]
            self.assertFalse(services[-1]['synthetic'])
            self.assertEqual(self.request('/api/collect', token),
                             (502, {'error': 'provider collection failed'}))
            poll.side_effect = RateLimitPollError('secret')
            self.assertEqual(self.request('/api/collect', token)[0], 429)
            with closing(Store(self.db)) as store:
                self.assertEqual(store.inbox(), [])
                self.assertEqual(store.audit(), [])

    def test_opt_in_registration_no_fetch_and_defaults(self):
        from assistant_hub.local_server import LocalServer
        with patch('assistant_hub.adapters.github_public.get_public') as transport:
            server = LocalServer(self.verifier, self.db, 18770, 'Owner/Repo')
            self.assertIn(('github-public', 'owner/repo'), server.bindings)
            self.assertTrue(server.github_public)
            transport.assert_not_called()
            default = LocalServer(self.verifier, self.db, 18770)
            self.assertFalse(default.github_public)
            self.assertTrue(all(s != 'github-public' for s, a in default.bindings))

    def test_banner_and_health_modes(self):
        enabled = self.request('/', method='GET')[1].decode()
        self.assertIn('Public read-only GitHub', enabled)
        self.assertIn('no private accounts or outgoing actions', enabled)
        self.assertIn('GitHub', self.request('/healthz', method='GET')[1]['label'])
        self.server.github_public = False
        self.assertIn('Synthetic demo', self.request('/', method='GET')[1].decode())
        self.assertEqual(self.request('/healthz', method='GET')[1], {'label': 'synthetic-only'})

    def test_cli_opt_in(self):
        from assistant_hub.local_server import main
        with patch('assistant_hub.local_server.LocalServer') as server, patch('builtins.print'):
            main(['serve', '--verifier', str(self.verifier), '--db', str(self.db),
                  '--github-public-repo', 'owner/repo'])
            server.assert_called_once_with(self.verifier, str(self.db), 18770, 'owner/repo')
