"""Explicit public feed snapshots. No discovery, redirects or implicit transport retries."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
import ssl
from typing import NamedTuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, unquote
import xml.etree.ElementTree as ET

from ..core.contracts import Capability, Event, Manifest, PermanentPollError, PollResult, TransientPollError

MAX_BYTES = 512 * 1024
ERROR = 'Public feed collection failed'
TYPES = {'application/rss+xml', 'application/atom+xml', 'application/xml', 'text/xml',
         'application/feed+json', 'application/json'}


def public_url(value):
    """Canonical public HTTPS URL; DNS is separately enforced at connection time."""
    if (not isinstance(value, str) or len(value) > 2048 or
            any(ord(c) <= 32 or 127 <= ord(c) <= 159 for c in unquote(value)) or '\\' in value or '#' in value):
        raise ValueError('invalid public feed URL')
    p = urlsplit(value)
    if not (p.path + p.query).isascii():
        raise ValueError('invalid public feed URL')
    if p.scheme != 'https' or p.username is not None or p.password is not None or p.fragment or p.port not in (None, 443):
        raise ValueError('invalid public feed URL')
    host = (p.hostname or '').encode('idna').decode('ascii').lower()
    labels = host.split('.')
    if (len(host) > 253 or len(labels) < 2 or
            any(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', x) is None for x in labels) or
            not re.fullmatch(r'[a-z]{2,63}|xn--[a-z0-9-]+', labels[-1]) or
            labels[-1] in {'localhost', 'local', 'internal', 'intranet', 'lan', 'home', 'test', 'invalid', 'example', 'onion', 'localdomain', 'corp', 'arpa'}):
        raise ValueError('invalid public feed URL')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('invalid public feed URL')
    if len(p.query) > 512:
        raise ValueError('invalid public feed URL')
    for key, val in parse_qsl(p.query, keep_blank_values=True, max_num_fields=16):
        if re.search(r'token|key|secret|auth|password|passwd|credential|signature|session|jwt', key, re.I):
            raise ValueError('invalid public feed URL')
    return urlunsplit(('https', host, p.path or '/', p.query, ''))


class FeedResponse(NamedTuple):
    status: int
    content_type: str
    body: bytes
    etag: str | None = None
    last_modified: str | None = None


def validator(value, date=False):
    if value is None:
        return None
    if not isinstance(value, str) or not 0 < len(value) <= 128 or any(not 32 <= ord(c) <= 126 for c in value):
        raise ValueError()
    if date:
        if re.fullmatch(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT', value) is None:
            raise ValueError()
        parsed = parsedate_to_datetime(value)
        if parsed.utcoffset() is None:
            raise ValueError()
    return value


def get_public(url, headers, *, accept=None):
    """Resolve once, reject every unsafe answer, connect to a vetted numeric IP."""
    url = public_url(url)
    p = urlsplit(url)
    conn = http.client.HTTPSConnection(p.hostname, timeout=8, context=ssl.create_default_context())
    try:
        answers = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
        if not answers:
            raise ValueError()
        for family, kind, proto, _, address in answers:
            ip = ipaddress.ip_address(address[0])
            if (not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback or
                    ip.is_link_local or ip.is_private or ip.is_unspecified or getattr(ip, 'ipv4_mapped', None)):
                raise ValueError()
        family, kind, proto, _, address = answers[0]
        with socket.socket(family, kind, proto) as raw:
            raw.settimeout(8)
            raw.connect(address)
            conn.sock = conn._context.wrap_socket(raw, server_hostname=p.hostname)
            if accept not in (None, 'text/calendar'):
                raise ValueError()
            safe = {'Accept': accept if accept else ', '.join(sorted(TYPES)),
                    'Accept-Encoding': 'identity',
                    'User-Agent': 'assistant-hub-public-feed/1'}
            for name, value in headers.items():
                if name not in ('If-None-Match', 'If-Modified-Since'):
                    raise ValueError()
                safe[name] = validator(value, name == 'If-Modified-Since')
            conn.request('GET', urlunsplit(('', '', p.path, p.query, '')), headers=safe)
            response = conn.getresponse()
            if response.status not in (200, 304) or response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise ValueError()
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError()
            return FeedResponse(response.status, response.getheader('Content-Type', ''), body,
                                response.getheader('ETag'), response.getheader('Last-Modified'))
    except (OSError, http.client.HTTPException):
        raise TransientPollError(ERROR) from None
    except ValueError:
        raise PermanentPollError(ERROR) from None
    finally:
        conn.close()


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text(value, markup=False):
    if not isinstance(value, str):
        raise ValueError()
    value.encode('utf-8')
    if markup:
        parser = PlainText()
        parser.feed(value)
        value = ''.join(parser.parts)
    return ''.join(c for c in value if ord(c) >= 32 and not 127 <= ord(c) <= 159
                   and c not in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')[:2000]


def date(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError()
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError) as exc:
            raise ValueError('invalid feed item date') from exc
    if result is None or result.utcoffset() is None:
        raise ValueError()
    return result.astimezone(timezone.utc)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


class PublicFeedAdapter:
    manifest = Manifest('public-feed', '1.0', (Capability('read', False, 'low'),))

    def __init__(self, feed_url, transport=None):
        self.feed_url = public_url(feed_url)
        self.accounts = (urlsplit(self.feed_url).hostname + ':' + sha256(self.feed_url.encode()).hexdigest(),)
        self._transport = transport if transport is not None else get_public

    def _items(self, raw, content_type):
        decoded = raw.decode('utf-8', errors='strict')
        if content_type in {'application/json', 'application/feed+json'}:
            obj = json.loads(decoded, object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(obj, dict) or obj.get('version') not in ('https://jsonfeed.org/version/1', 'https://jsonfeed.org/version/1.1'):
                raise ValueError()
            items = obj['items']
            if not isinstance(items, list) or len(items) >= 100:
                raise ValueError()
            for i in items:
                if not isinstance(i, dict):
                    raise ValueError()
                yield (i.get('id'), i.get('title', ''), i.get('content_text', i.get('summary', i.get('content_html', ''))),
                       i.get('date_modified') or i.get('date_published'), i.get('url'), 'content_text' not in i and 'summary' not in i)
        else:
            if re.search(r'<!\s*(DOCTYPE|ENTITY)', decoded, re.I):
                raise ValueError()
            root = ET.fromstring(decoded)
            stack = [(root, 0)]
            count = 0
            item_count = 0
            while stack:
                node, depth = stack.pop()
                count += 1
                if node.tag in ('item', '{http://www.w3.org/2005/Atom}entry'):
                    item_count += 1
                if item_count >= 100:
                    raise ValueError()
                if depth > 24 or count > 5000:
                    raise ValueError()
                stack.extend((child, depth + 1) for child in node)
            atom = '{http://www.w3.org/2005/Atom}'
            if root.tag == 'rss':
                if len(root.findall('channel')) != 1:
                    raise ValueError()
                items = root.findall('./channel/item')
                prefix = ''
            elif root.tag == atom + 'feed':
                items = root.findall(atom + 'entry')
                prefix = atom
            else:
                raise ValueError()
            if len(items) >= 100:
                raise ValueError()
            for i in items:
                def field(name):
                    n = i.find(prefix + name)
                    return ''.join(n.itertext()) if n is not None else None
                link = field('link')
                if prefix:
                    link = next((n.get('href') for n in i.findall(atom + 'link') if n.get('rel', 'alternate') == 'alternate'), None)
                yield (field('id' if prefix else 'guid'), field('title') or '',
                       (field('summary') or field('content') if prefix else field('description')) or '',
                       (field('updated') or field('published') if prefix else field('pubDate')), link, True)

    def poll(self, account_id, cursor):
        try:
            if account_id != self.accounts[0]:
                raise ValueError()
            state = {'v': 1}
            if cursor is not None:
                if not isinstance(cursor, str) or len(cursor.encode('utf-8')) > 4096:
                    raise ValueError()
                state = json.loads(cursor, object_pairs_hook=unique)
                if not isinstance(state, dict) or type(state.get('v')) is not int or state.get('v') != 1 or set(state) - {'v', 'etag', 'last_modified'}:
                    raise ValueError()
            headers = {}
            for key, header in (('etag', 'If-None-Match'), ('last_modified', 'If-Modified-Since')):
                if key in state:
                    headers[header] = validator(state[key], key == 'last_modified')
                    if headers[header] is None:
                        raise ValueError()
            response = self._transport(self.feed_url, headers)
            if not isinstance(response, tuple) or len(response) != 5:
                raise ValueError()
            status, content_type, raw, etag, modified = response
            if type(status) is not int or not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
                raise ValueError()
            if status == 304:
                if raw or cursor is None:
                    raise ValueError()
                return PollResult((), cursor)
            if status != 200 or not isinstance(content_type, str) or content_type.split(';')[0].strip().lower() not in TYPES:
                raise ValueError()
            new_state = {'v': 1}
            for key, value in (('etag', etag), ('last_modified', modified)):
                if value is not None:
                    new_state[key] = validator(value, key == 'last_modified')
            events = []
            receipt = datetime.now(timezone.utc)
            for ident, title, body, updated, link, markup in self._items(raw, content_type.split(';')[0].strip().lower()):
                title, body = text(title, True), text(body, markup)
                safe_link = ''
                if link:
                    try:
                        safe_link = public_url(link)
                        if urlsplit(safe_link).hostname != urlsplit(self.feed_url).hostname:
                            safe_link = ''
                    except ValueError:
                        pass
                stamp = date(updated)
                if ident is not None and (not isinstance(ident, str) or not ident or len(ident) > 4096):
                    raise ValueError()
                identity = ident or json.dumps([title, body, safe_link], ensure_ascii=True)
                version = stamp.isoformat() if stamp else ''
                external = 'v1:' + sha256(json.dumps([self.feed_url, identity, version]).encode()).hexdigest()
                events.append(Event('public-feed', account_id, external, 'feed.item', stamp or receipt,
                                    account_id, title, body, {'provenance': 'public-feed', 'html_url': safe_link}))
            return PollResult(tuple(events[:40]), json.dumps(new_state, sort_keys=True, separators=(',', ':')))
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError, ET.ParseError, OSError):
            raise PermanentPollError(ERROR) from None


class PublicFeedCatalog:
    """One read-only adapter and independent cursor per explicit public feed."""

    manifest = PublicFeedAdapter.manifest
    MAX_FEEDS = 8

    def __init__(self, urls, transport=None):
        if (not isinstance(urls, (tuple, list)) or
                not 1 <= len(urls) <= self.MAX_FEEDS):
            raise ValueError('1 to 8 explicit public feeds required')
        sources = [PublicFeedAdapter(url, transport) for url in urls]
        accounts = tuple(source.accounts[0] for source in sources)
        if len(set(accounts)) != len(accounts):
            raise ValueError('duplicate public feed URL')
        self.accounts = accounts
        self._sources = dict(zip(accounts, sources))

    def poll(self, account_id, cursor):
        source = self._sources.get(account_id)
        if source is None:
            raise PermanentPollError(ERROR)
        return source.poll(account_id, cursor)
