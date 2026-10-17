"""Offline public-feed evidence: fake HTTP, DNS, sockets and owner requests only."""
from contextlib import closing
from email.message import Message
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

from assistant_hub.adapters.public_feed import (PublicFeedAdapter, FeedResponse, MAX_BYTES,
                                               get_public, public_url)
from assistant_hub.core.contracts import PollError
from assistant_hub.core.hub import Hub
from assistant_hub.core.registry import Binding, Registry
from assistant_hub.core.store import Store

URL = 'https://feeds.python.org/news'
RSS = b'<rss><channel><item><guid>one</guid><title>Title</title><description>&lt;b&gt;Body&lt;/b&gt;</description><link>https://feeds.python.org/one</link><pubDate>Fri, 16 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.transport = Mock(return_value=FeedResponse(200, 'application/rss+xml', RSS))
        self.adapter = PublicFeedAdapter(URL, self.transport)

    def poll(self, cursor=None):
        return self.adapter.poll(self.adapter.accounts[0], cursor)

    def response(self, body, content_type='application/rss+xml', **kwargs):
        self.transport.return_value = FeedResponse(200, content_type, body, **kwargs)

    def test_rss(self):
        e = self.poll().events[0]
        self.assertEqual((e.title, e.body), ('Title', 'Body'))
        self.assertEqual(e.timestamp.utcoffset().total_seconds(), 0)
        self.assertEqual(e.attributes['html_url'], 'https://feeds.python.org/one')

    def test_atom(self):
        self.response(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>one</id><title>A</title><content>text</content><updated>2026-10-16T12:00:00+02:00</updated><link href="https://feeds.python.org/one"/></entry></feed>', 'application/atom+xml')
        e = self.poll().events[0]
        self.assertEqual(e.body, 'text')
        self.assertEqual(e.timestamp.hour, 10)

    def test_json_versions(self):
        for version in ('1', '1.1'):
            self.response(json.dumps({'version': 'https://jsonfeed.org/version/' + version,
                                      'items': [{'id': 'one', 'content_html': '<p>Safe</p>'}]}).encode(), 'application/feed+json')
            self.assertEqual(self.poll().events[0].body, 'Safe')

    def test_json_text_precedence(self):
        self.response(b'{"version":"https://jsonfeed.org/version/1","items":[{"id":"one","content_text":"<b>plain</b>","summary":"other"}]}', 'application/json')
        self.assertEqual(self.poll().events[0].body, '<b>plain</b>')

    def test_manifest(self):
        self.assertEqual(self.adapter.manifest.service_id, 'public-feed')
        self.assertEqual([(c.name, c.mutating, c.risk) for c in self.adapter.manifest.capabilities], [('read', False, 'low')])

    def test_normalization_identity(self):
        self.assertEqual(PublicFeedAdapter('https://FEEDS.PYTHON.ORG:443/news').accounts, self.adapter.accounts)
        self.assertNotEqual(PublicFeedAdapter(URL + '2').accounts, self.adapter.accounts)
        self.assertIn('xn--', public_url('https://bücher.de/feed'))

    def test_urls_rejected(self):
        for url in ('http://python.org/', 'https://localhost/', 'https://a.local/', 'https://intranet/',
                    'https://127.0.0.1/', 'https://[::1]/', 'https://169.254.169.254/',
                    'https://a.python.org:444/', 'https://user:pass@python.org/', 'https://python.org/#x',
                    'https://python.org/?api_key=x', 'https://python.org/?%74oken=x',
                    'https://python.org/\n', 'https://python.org/%0d%0aHost:x', 'https://2130706433/',
                    'https://a..org/', 'https://a.internal/', 'https://python.org/?q=' + 'x' * 513):
            with self.subTest(url=url), self.assertRaises(ValueError): PublicFeedAdapter(url)
        self.assertEqual(public_url(URL + '?page=1'), URL + '?page=1')

    def test_wrong_account(self):
        with self.assertRaises(PollError): self.adapter.poll('other', None)
        self.transport.assert_not_called()

    def test_invalid_cursor(self):
        for cursor in ('', '{}', 'null', '{"v":2}', '{"v":1,"etag":"x\\r\\nHost:x"}', 'x' * 4097,
                       '{"v":1,"last_modified":"yesterday"}', '{"v":1,"etag":null}'):
            with self.subTest(cursor=cursor), self.assertRaises(PollError): self.poll(cursor)
        self.transport.assert_not_called()

    def test_validators(self):
        self.response(RSS, etag='"one"', last_modified='Fri, 16 Oct 2026 10:00:00 GMT')
        first = self.poll()
        self.poll(first.cursor)
        self.assertEqual(self.transport.call_args.args[1], {'If-None-Match': '"one"', 'If-Modified-Since': 'Fri, 16 Oct 2026 10:00:00 GMT'})

    def test_validator_replacement(self):
        self.response(RSS, etag='"one"')
        first = self.poll()
        self.response(RSS)
        second = self.poll(first.cursor)
        self.assertEqual(json.loads(second.cursor), {'v': 1})

    def test_header_injection(self):
        for value in ('x\r\nAuthorization: secret', 'é', 'x' * 129):
            self.response(RSS, etag=value)
            with self.assertRaises(PollError): self.poll()

    def test_304(self):
        cursor = self.poll().cursor
        self.transport.return_value = FeedResponse(304, '', b'')
        self.assertEqual(self.poll(cursor).cursor, cursor)
        self.assertEqual(self.poll(cursor).events, ())
        with self.assertRaises(PollError): self.poll()
        self.transport.return_value = FeedResponse(304, '', b'bad')
        with self.assertRaises(PollError): self.poll(cursor)

    def test_status_content_type(self):
        for status in (301, 302, 307, 401, 404, 429, 500):
            self.transport.return_value = FeedResponse(status, 'application/xml', RSS)
            with self.assertRaises(PollError): self.poll()
        self.response(RSS, 'text/html')
        with self.assertRaises(PollError): self.poll()

    def test_bad_xml_utf_and_dtd(self):
        for body in (b'\xff', b'<rss>', b'<!DOCTYPE rss><rss/>', b'<!entity a "x"><rss/>', b'<html/>',
                     b'<!DoCtYpE rss [<!ENTITY x "abc">]><rss/>'):
            self.response(body)
            with self.subTest(body=body), self.assertRaises(PollError): self.poll()

    def test_bad_json(self):
        for body in (b'{', b'null', b'[]', b'{"version":"no"}', b'{"version":"https://jsonfeed.org/version/1","items":[null]}',
                     b'{"version":"https://jsonfeed.org/version/1","items":[],"items":[]}', b'NaN'):
            self.response(body, 'application/json')
            with self.assertRaises(PollError): self.poll()

    def test_limits(self):
        for body in (b'x' * (MAX_BYTES + 1), b'<rss><channel>' + b'<item/>' * 100 + b'</channel></rss>',
                     b'<rss>' + b'<x>' * 25 + b'</x>' * 25 + b'</rss>'):
            self.response(body)
            with self.assertRaises(PollError): self.poll()
        self.response(b'<rss><channel>' + b'<item/>' * 41 + b'</channel></rss>')
        self.assertEqual(len(self.poll().events), 40)

    def test_safe_text_identity(self):
        self.response(RSS.replace(b'Title', ('\u202e' + 'x' * 2100).encode()).replace(b'one</guid>', b'unsafe-secret-id</guid>'))
        e = self.poll().events[0]
        self.assertEqual(len(e.title), 2000)
        self.assertNotIn('unsafe-secret-id', e.external_id)
        self.assertNotIn('\u202e', e.title)

    def test_source_link_sanitizer(self):
        for link in ('http://feeds.python.org/one', 'https://evil.org/one', 'javascript:alert(1)',
                     'https://127.0.0.1/', 'https://feeds.python.org/?token=x'):
            self.response(RSS.replace(b'https://feeds.python.org/one', link.encode()))
            self.assertEqual(self.poll().events[0].attributes['html_url'], '')
        self.assertEqual(self.transport.call_count, 5)

    def test_missing_date_identity(self):
        self.response(b'<rss><channel><item><title>A</title></item></channel></rss>')
        self.assertEqual(self.poll().events[0].external_id, self.poll().events[0].external_id)

    def test_malformed_date(self):
        self.response(RSS.replace(b'Fri, 16 Oct 2026 10:00:00 GMT', b'nonsense'))
        with self.assertRaises(PollError): self.poll()

    def test_dedup_version_atomicity_isolation(self):
        registry = Registry()
        registry.enable(self.adapter, (Binding(self.adapter.accounts[0]),))
        with tempfile.TemporaryDirectory() as directory, closing(Store(Path(directory) / 'db')) as store:
            hub = Hub(registry, store)
            account = self.adapter.accounts[0]
            self.assertEqual(hub.collect('public-feed', account), 1)
            self.assertEqual(hub.collect('public-feed', account), 0)
            self.response(RSS.replace(b'10:00:00', b'11:00:00'))
            self.assertEqual(hub.collect('public-feed', account), 1)
            before = (store.inbox(), store.audit(), store.cursor('public-feed', account))
            self.response(RSS.replace(b'</channel>', b'<item><pubDate>bad</pubDate></item></channel>'))
            with self.assertRaises(PollError): hub.collect('public-feed', account)
            self.assertEqual(before, (store.inbox(), store.audit(), store.cursor('public-feed', account)))
            other = PublicFeedAdapter(URL + '2', lambda *a: FeedResponse(200, 'application/xml', RSS))
            store.ingest('public-feed', other.accounts[0], other.poll(other.accounts[0], None))
            self.assertEqual(len(store.inbox()), 3)


class TransportTests(unittest.TestCase):
    def test_unsafe_dns_any_answer(self):
        for ip in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '224.0.0.1', '192.0.2.1'):
            answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (addr, 443)) for addr in ('8.8.8.8', ip)]
            with patch('socket.getaddrinfo', return_value=answers), patch('socket.socket') as sock:
                with self.assertRaises(PollError): get_public(URL, {})
                sock.assert_not_called()

    def test_pinned_tls_and_bounded_http(self):
        with patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]) as dns, patch('socket.socket') as sock, patch('ssl.create_default_context') as ctx, patch('http.client.HTTPSConnection') as https:
            response = https.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = RSS
            response.getheader.side_effect = lambda key, default=None: {'Content-Type': 'application/xml'}.get(key, default)
            self.assertEqual(get_public(URL, {'If-None-Match': '"one"'}).body, RSS)
            sock.return_value.__enter__.return_value.connect.assert_called_once_with(('8.8.8.8', 443))
            https.return_value._context.wrap_socket.assert_called_once_with(sock.return_value.__enter__.return_value, server_hostname='feeds.python.org')
            ctx.assert_called_once_with()
            dns.assert_called_once()
            response.read.assert_called_once_with(MAX_BYTES + 1)
            args, kwargs = https.return_value.request.call_args
            self.assertEqual(args, ('GET', '/news'))
            self.assertEqual(kwargs['headers']['Accept-Encoding'], 'identity')
            self.assertNotIn('Authorization', kwargs['headers'])

    def test_transport_status_encoding_size(self):
        for status, encoding, body in ((302, 'identity', b''), (200, 'gzip', b''), (200, 'identity', b'x' * (MAX_BYTES + 1))):
            with patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]), patch('socket.socket'), patch('http.client.HTTPSConnection') as https:
                response = https.return_value.getresponse.return_value
                response.status = status
                response.getheader.return_value = encoding
                response.read.return_value = body
                with self.assertRaises(PollError): get_public(URL, {})


class FeedServerTests(unittest.TestCase):
    def test_cli_one_feed_only(self):
        from assistant_hub.local_server import main
        args = ['serve', '--verifier', '/tmp/feed-test-owner.json', '--db', '/tmp/feed-test-db',
                '--public-feed', URL]
        with patch('assistant_hub.local_server.LocalServer') as server, patch('builtins.print'):
            main(args)
            server.assert_called_once_with(Path('/tmp/feed-test-owner.json'), '/tmp/feed-test-db',
                                           18770, None, public_feed=URL)
        with patch('assistant_hub.local_server.LocalServer') as server:
            with self.assertRaises(SystemExit): main(args + ['--public-feed', URL + '2'])
            server.assert_not_called()

    def test_opt_in_owner_boundary_and_banners(self):
        from assistant_hub.local_server import Handler, LocalServer
        from assistant_hub.security.credentials import VerifierStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verifier = root / 'owner.json'
            VerifierStore(verifier).bootstrap('owner', 'synthetic-test-password')
            def fake_init(server, *args): server.server_port = 18770
            with patch('assistant_hub.local_server.ThreadingHTTPServer.__init__', fake_init), patch('assistant_hub.adapters.public_feed.get_public', return_value=FeedResponse(200, 'application/xml', RSS)) as transport:
                default = LocalServer(verifier, root / 'db')
                self.assertFalse(default.public_feed)
                server = LocalServer(verifier, root / 'db', github_public_repo='owner/repo', public_feed=URL)
                account = server.registry.get('public-feed').accounts[0]
                def request(path, method='GET', token=None):
                    handler = Handler.__new__(Handler)
                    handler.server, handler.command, handler.path = server, method, path
                    handler.requestline = method + ' ' + path + ' HTTP/1.1'
                    handler.headers = Message()
                    handler.headers['Host'] = server.host
                    handler.headers['Origin'] = server.origin
                    if token: handler.headers['Authorization'] = 'Bearer ' + token
                    handler.body = lambda *args: {'service': 'public-feed', 'account': account}
                    with patch.object(handler, 'reply') as reply:
                        handler.handle_request()
                        return reply.call_args.args
                banner = request('/')[1].decode()
                self.assertIn('feeds + GitHub', banner)
                self.assertNotIn(URL, banner)
                self.assertIn('feeds', request('/healthz')[1]['label'])
                self.assertEqual(request('/api/services')[0], 401)
                self.assertEqual(request('/api/collect', 'POST')[0], 401)
                transport.assert_not_called()
                token = server.login.login('synthetic-test-password').token
                self.assertFalse(request('/api/services', token=token)[1][-1]['synthetic'])
                self.assertEqual(request('/api/collect', 'POST', token), (200, {'inserted': 1}))
                transport.assert_called_once()
