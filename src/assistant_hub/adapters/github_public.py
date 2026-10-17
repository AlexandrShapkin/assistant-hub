"""Bounded, anonymous GitHub public snapshots; no retries or pagination."""
from datetime import datetime, timezone
import json
from http.client import HTTPException
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from ..core.contracts import (AuthenticationPollError, Capability, Event, Manifest,
                              PermanentPollError, PollResult, RateLimitPollError,
                              TransientPollError)

MAX_RESPONSE = 2 * 1024 * 1024
ERROR = "GitHub public collection failed"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_error(code):
    if code in (403, 429):
        return RateLimitPollError(ERROR)
    if code == 401:
        return AuthenticationPollError(ERROR)
    if code >= 500:
        return TransientPollError(ERROR)
    return PermanentPollError(ERROR)


def get_public(url):
    """Fresh opener: no proxies, cookies, netrc, ambient tokens or redirects."""
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, method="GET", headers={
        "Accept": "application/vnd.github+json", "User-Agent": "assistant-hub-public-reader",
        "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with opener.open(request, timeout=8) as response:
            if response.status != 200:
                raise http_error(response.status)
            data = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        error.close()
        raise http_error(error.code) from None
    except (OSError, URLError, ValueError, HTTPException):
        raise TransientPollError(ERROR) from None
    if len(data) > MAX_RESPONSE:
        raise PermanentPollError(ERROR)
    return data


def text(value, limit=2400):
    if not isinstance(value, str):
        raise ValueError()
    value[:limit].encode('utf-8')
    # Keep provider text as inert text; strip controls and bidi formatting.
    return ''.join(c for c in value[:limit] if c in '\n\t' or
                   (ord(c) >= 32 and not 127 <= ord(c) <= 159 and
                    c not in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069'))


def number(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError()
    return str(value)


def timestamp(value):
    if not isinstance(value, str) or re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value) is None:
        raise ValueError()
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


class GitHubPublicAdapter:
    manifest = Manifest('github-public', '1.0', (Capability('read', False, 'low'),))

    def __init__(self, repo, transport=None):
        if not isinstance(repo, str) or len(repo) > 140:
            raise ValueError('invalid public repository')
        parts = repo.split('/')
        if (len(parts) != 2 or
                re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', parts[0]) is None or
                re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', parts[1]) is None or
                '..' in parts[1] or parts[1] == '.'):
            raise ValueError('invalid public repository')
        self.repo = repo.lower()
        self.accounts = (self.repo,)
        self._transport = transport if transport is not None else get_public

    def _get(self, suffix):
        try:
            raw = self._transport('https://api.github.com/repos/' + self.repo + suffix)
            if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
                raise ValueError()
            return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except HTTPError as error:
            error.close()
            raise http_error(error.code) from None
        except (ValueError, TypeError, RecursionError, OSError):
            raise PermanentPollError(ERROR) from None

    def _event(self, item, kind):
        ident = number(item['id'] if kind == 'workflow' else item['number'])
        updated = timestamp(item['updated_at'])
        version = updated.isoformat()
        path = {'issue': 'issues', 'pull': 'pull', 'workflow': 'actions/runs'}[kind]
        expected = f'https://github.com/{self.repo}/{path}/{ident}'
        url = item['html_url']
        if not isinstance(url, str) or not url.isascii() or url.lower() != expected:
            raise ValueError()
        attrs = {'repo': self.repo, 'html_url': expected, 'provenance': 'github-public'}
        if kind == 'workflow':
            attempt = number(item['run_attempt'])
            status = text(item['status'], 80)
            conclusion = item['conclusion']
            if conclusion is not None:
                conclusion = text(conclusion, 80)
            if not status:
                raise ValueError()
            attrs.update(status=status, conclusion=conclusion or '', run_attempt=attempt)
            version += ':' + attempt + ':' + status
            title, body = text(item['name']), ''
        else:
            state = text(item['state'], 80)
            if state not in ('open', 'closed'):
                raise ValueError()
            attrs['state'] = state
            title = text(item['title'])
            body = text(item['body']) if item['body'] is not None else ''
        return Event('github-public', self.repo, f'v1:{kind}:{ident}:{version}',
                     'github.' + kind, updated, self.repo, title, body, attrs)

    def poll(self, account_id, cursor):
        if account_id != self.repo or cursor not in (None, 'latest-v1'):
            raise PermanentPollError(ERROR)
        try:
            metadata = self._get('')
            if (not isinstance(metadata, dict) or metadata['private'] is not False or
                    not isinstance(metadata['full_name'], str) or not metadata['full_name'].isascii() or
                    metadata['full_name'].lower() != self.repo):
                raise ValueError()
            query = '?state=all&sort=updated&direction=desc&per_page=30'
            events = []
            for kind, suffix in (('issue', '/issues' + query), ('pull', '/pulls' + query),
                                 ('workflow', '/actions/runs?per_page=30')):
                items = self._get(suffix)
                if kind == 'workflow':
                    items = items['workflow_runs']
                if not isinstance(items, list) or len(items) > 30:
                    raise ValueError()
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError()
                    if kind == 'issue' and 'pull_request' in item:
                        continue
                    events.append(self._event(item, kind))
            return PollResult(tuple(events), 'latest-v1')
        except (KeyError, TypeError, ValueError, OverflowError):
            raise PermanentPollError(ERROR) from None
