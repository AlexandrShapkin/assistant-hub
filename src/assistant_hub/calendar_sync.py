"""Opt-in HTTP iCalendar subscription: exact owner-private URL, no page scraping."""
from contextlib import closing
import os
from pathlib import Path
import stat
import threading
import time

from .adapters.public_feed import get_public, public_url
from .calendar_import import MAX_ICAL_BYTES, parse_ical
from .core.contracts import PermanentPollError
from .core.store import Store

MIN_INTERVAL = 900
MAX_INTERVAL = 86400


def read_subscription_url(path):
    """A trusted 0700 owner directory and 0600 regular file, never an argv URL."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("absolute private subscription file required")
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(directory)
        if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o700:
            raise ValueError("untrusted calendar URL parent")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            meta = os.fstat(fd)
            if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                    or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_size > 2049):
                raise ValueError("untrusted calendar URL file")
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(2050)
        finally:
            os.close(fd)
    finally:
        os.close(directory)
    try:
        url = raw.decode("utf-8").strip()
    except UnicodeError:
        raise ValueError("invalid calendar URL file") from None
    if not url or '\n' in url or '\r' in url:
        raise ValueError("invalid calendar URL file")
    return public_url(url)


class CalendarSubscription:
    """One approved full-week iCalendar source. Nothing fetched at initialization."""

    def __init__(self, db, url, interval, lock, transport=None, clock=time.monotonic):
        if type(interval) is not int or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
            raise ValueError("invalid calendar subscription interval")
        self.url = public_url(url)
        self.db = db
        self.interval = interval
        self.lock = lock
        self.transport = transport or get_public
        self.clock = clock
        self.next_due = clock() + interval
        self.failures = 0
        self.headers = {}
        self.has_snapshot = False

    def run_due(self):
        if self.clock() < self.next_due:
            return
        self.next_due = self.clock() + self.interval
        try:
            response = self.transport(self.url, dict(self.headers), accept='text/calendar')
            if not isinstance(response, tuple) or len(response) != 5:
                raise ValueError("invalid calendar HTTP result")
            status, kind, raw, etag, last_modified = response
            if type(status) is not int or not isinstance(raw, bytes) or len(raw) > MAX_ICAL_BYTES:
                raise ValueError("invalid calendar HTTP payload")
            if status == 304:
                if raw or not self.has_snapshot:
                    raise ValueError("invalid 304 calendar response")
            elif status == 200:
                if not isinstance(kind, str) or kind.split(';', 1)[0].lower().strip() != 'text/calendar':
                    raise ValueError("not a public calendar")
                week, events = parse_ical(raw.decode('utf-8', errors='strict'),
                                          provenance='subscription-ics')
                from .adapters.public_feed import validator
                next_headers = {}
                if etag is not None:
                    next_headers['If-None-Match'] = validator(etag)
                if last_modified is not None:
                    next_headers['If-Modified-Since'] = validator(last_modified, True)
                # Validate the entire HTTP response before any write.
                with self.lock, closing(Store(self.db)) as store:
                    store.import_calendar_week(week, events)
                self.headers = next_headers
                self.has_snapshot = True
            else:
                raise ValueError("invalid calendar HTTP response")
        except PermanentPollError:
            self.next_due = float("inf")
        except Exception:
            # No URL, HTTP response, error details or imported event text in logs.
            self.failures = min(self.failures + 1, 7)
            self.next_due = self.clock() + min(MAX_INTERVAL, self.interval * 2**self.failures)
        else:
            self.failures = 0
            self.next_due = self.clock() + self.interval

    def run(self, stop: threading.Event):
        while not stop.is_set():
            self.run_due()
            stop.wait(min(60, max(.05, self.next_due - self.clock())))
