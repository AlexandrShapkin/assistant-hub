"""Local SQLite persistence. Records decisions and reviews, never dispatches."""
import json
import os
from pathlib import Path
import sqlite3
import stat
from dataclasses import asdict
from .contracts import ActionIntent, Decision, PollResult
from .conformance import validate_poll_result


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Reject symlinks and non-regular files before SQLite sees the path.
        flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("database must be a regular file")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                service TEXT, account TEXT, external_id TEXT, data TEXT NOT NULL,
                PRIMARY KEY(service, account, external_id));
            CREATE TABLE IF NOT EXISTS cursors (
                service TEXT, account TEXT, cursor TEXT,
                PRIMARY KEY(service, account));
            CREATE TABLE IF NOT EXISTS intents (
                key TEXT PRIMARY KEY, data TEXT NOT NULL, decision TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT NOT NULL, subject TEXT NOT NULL, data TEXT NOT NULL);
        ''')

    def close(self) -> None:
        self.db.close()

    def cursor(self, service: str, account: str) -> str | None:
        row = self.db.execute("SELECT cursor FROM cursors WHERE service=? AND account=?",
                              (service, account)).fetchone()
        return row[0] if row else None

    def ingest(self, service: str, account: str, result: PollResult) -> int:
        validate_poll_result(service, account, result, self.cursor(service, account))
        count = 0
        with self.db:
            for event in result.events:
                data = asdict(event)
                data["timestamp"] = event.timestamp.isoformat()
                count += self.db.execute(
                    "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?)",
                    (service, account, event.external_id, encode(data)),
                ).rowcount
            self.db.execute("INSERT OR REPLACE INTO cursors VALUES (?, ?, ?)",
                            (service, account, result.cursor))
            self._audit("collect", encode([service, account]), encode({"inserted": count}))
        return count

    def _audit(self, kind: str, subject: str, data: str) -> None:
        self.db.execute("INSERT INTO audit(kind, subject, data) VALUES (?, ?, ?)",
                        (kind, subject, data))

    def record_intent(self, intent: ActionIntent, decision: Decision) -> Decision:
        data = encode(asdict(intent))
        with self.db:
            row = self.db.execute("SELECT data, decision FROM intents WHERE key=?",
                                  (intent.idempotency_key,)).fetchone()
            if row:
                if row["data"] != data:
                    raise ValueError("idempotency key conflicts with existing intent")
                return Decision(**json.loads(row["decision"]))
            serialized = encode(asdict(decision))
            self.db.execute("INSERT INTO intents VALUES (?, ?, ?)",
                            (intent.idempotency_key, data, serialized))
            self._audit("plan", intent.idempotency_key, serialized)
        return decision

    def review(self, key: str, outcome: str, reviewer: str) -> None:
        if outcome not in ("approve", "reject") or not reviewer.strip():
            raise ValueError("review requires outcome and reviewer")
        with self.db:
            row = self.db.execute("SELECT decision FROM intents WHERE key=?", (key,)).fetchone()
            if row is None:
                raise ValueError("unknown intent")
            if json.loads(row[0])["status"] != "review":
                raise ValueError("intent is not awaiting review")
            self._audit("review", key, encode({"outcome": outcome, "reviewer": reviewer}))

    def inbox(self) -> list[dict]:
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT data FROM events ORDER BY service, account, external_id")]

    def intents(self) -> list[dict]:
        return [{"intent": json.loads(row[0]), "decision": json.loads(row[1])}
                for row in self.db.execute("SELECT data, decision FROM intents ORDER BY key")]

    def audit(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM audit ORDER BY id")]
