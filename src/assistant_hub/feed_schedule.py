"""Opt-in, bounded, one-worker scheduling of explicitly registered public feeds."""
from contextlib import closing
import time

from .core.contracts import PermanentPollError
from .core.hub import Hub
from .core.store import Store


MIN_INTERVAL = 900
MAX_INTERVAL = 86400


class FeedSchedule:
    """No side effects during construction; run_due is deterministic with a fake clock.

    The web handler and worker share the same lock, and each poll owns a separate
    SQLite connection. Permanent failures suspend one feed until process restart.
    All other failures apply capped per-feed backoff; no error content is logged.
    """

    def __init__(self, registry, db_path, accounts, interval, lock, clock=time.monotonic):
        if (type(interval) is not int or not MIN_INTERVAL <= interval <= MAX_INTERVAL
                or not isinstance(accounts, tuple) or not accounts
                or len(accounts) > 8 or len(set(accounts)) != len(accounts)):
            raise ValueError("invalid feed scheduling configuration")
        for account in accounts:
            registry.require("public-feed", account, "read")
        self.registry, self.db_path, self.accounts = registry, db_path, accounts
        self.interval, self.lock, self.clock = interval, lock, clock
        self.failures = dict.fromkeys(accounts, 0)
        self.due = {account: clock() + interval for account in accounts}

    def run_due(self):
        """Attempt each due feed at most once; one failure does not block others."""
        for account in self.accounts:
            if self.clock() < self.due[account]:
                continue
            # A second simultaneous invocation cannot start an immediate replay.
            self.due[account] = self.clock() + self.interval
            try:
                with self.lock, closing(Store(self.db_path)) as store:
                    Hub(self.registry, store).collect("public-feed", account)
            except PermanentPollError:
                self.due[account] = float("inf")
            except Exception:
                # Keep another source alive even after an unexpected provider/DB error.
                # Never expose untrusted exception contents in worker logs.
                self.failures[account] = min(self.failures[account] + 1, 7)
                delay = min(MAX_INTERVAL, self.interval * 2 ** self.failures[account])
                self.due[account] = self.clock() + delay
            else:
                self.failures[account] = 0
                self.due[account] = self.clock() + self.interval

    def run(self, stop):
        """Block on a cancellation event; never start a collection on shutdown."""
        while not stop.is_set():
            self.run_due()
            remaining = min(self.due.values()) - self.clock()
            stop.wait(min(60, max(0.05, remaining)))
