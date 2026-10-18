"""Owner-submitted development evidence. No executor or command delivery."""
import json
import re
import time
from uuid import UUID

PROJECTS = {"assistant-hub": "active", "codex-smart": "active", "rustcraft": "candidate"}
REPORT_FIELDS = ("protocol_version", "message_id", "task_id", "project", "executor_id",
                 "sequence", "status", "issue", "branch", "head_sha", "pr")
CONTROL_FIELDS = ("message_id", "task_id", "action")
STATUSES = {"running", "blocked", "completed", "failed"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def identifier(value):
    return bool(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}", value))


def uuid(value):
    if str(UUID(value)) != value:
        raise ValueError("canonical UUID required")


class DevelopmentLedger:
    def __init__(self, store, clock=time.time):
        self.db, self.clock = store.db, clock
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS development_tasks (
                task_id TEXT PRIMARY KEY, data TEXT NOT NULL, sequence INTEGER NOT NULL,
                received_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS development_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT UNIQUE NOT NULL,
                task_id TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL,
                received_at REAL NOT NULL);
        ''')

    def _validate(self, obj, fields):
        if (type(obj) is not dict or set(obj) != set(fields) or
                any(type(v) is not str or not v or len(v) > 128 for v in obj.values())):
            raise ValueError("invalid envelope")
        uuid(obj["message_id"])
        if not identifier(obj["task_id"]):
            raise ValueError("invalid task identity")

    def _replay(self, obj, kind):
        row = self.db.execute("SELECT kind, data FROM development_events WHERE message_id=?",
                              (obj["message_id"],)).fetchone()
        if row and (row["kind"] != kind or row["data"] != canonical(obj)):
            raise ValueError("conflicting replay")
        return row is not None

    def _event(self, obj, kind, actor, now):
        self.db.execute("INSERT INTO development_events(message_id, task_id, kind, data, received_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (obj["message_id"], obj["task_id"], kind, canonical(obj), now))
        self.db.execute("INSERT INTO audit(kind, subject, data) VALUES (?, ?, ?)",
                        ("development." + kind, actor, canonical(obj)))

    def report(self, obj, *, actor):
        self._validate(obj, REPORT_FIELDS)
        if (obj["protocol_version"] != "1" or obj["project"] not in PROJECTS or
                not identifier(obj["executor_id"]) or obj["status"] not in STATUSES or
                not re.fullmatch(r"[1-9][0-9]{0,8}", obj["sequence"]) or
                not re.fullmatch(r"[1-9][0-9]{0,8}", obj["issue"]) or
                not re.fullmatch(r"unknown|[1-9][0-9]{0,8}", obj["pr"]) or
                not re.fullmatch(r"unknown|[0-9a-f]{40}", obj["head_sha"]) or
                not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/-]{0,127}", obj["branch"])):
            raise ValueError("invalid report")
        with self.db:
            if self._replay(obj, "report"):
                return {"accepted": True, "replayed": True}
            row = self.db.execute("SELECT data, sequence FROM development_tasks WHERE task_id=?",
                                  (obj["task_id"],)).fetchone()
            previous = json.loads(row["data"]) if row else None
            if int(obj["sequence"]) != (row["sequence"] + 1 if row else 1):
                raise ValueError("next sequence required")
            if previous and (any(obj[k] != previous[k] for k in ("project", "executor_id", "issue")) or
                             previous["status"] in {"completed", "failed"}):
                raise ValueError("immutable task or terminal report")
            if not row and self.db.execute("SELECT count(*) FROM development_tasks").fetchone()[0] >= 100:
                raise ValueError("task capacity reached")
            now = self.clock()
            self.db.execute("INSERT INTO development_tasks VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(task_id) DO UPDATE SET data=excluded.data, "
                            "sequence=excluded.sequence, received_at=excluded.received_at",
                            (obj["task_id"], canonical(obj), int(obj["sequence"]), now))
            self._event(obj, "report", actor, now)
        return {"accepted": True, "replayed": False}

    def control(self, obj, *, actor):
        self._validate(obj, CONTROL_FIELDS)
        if obj["action"] not in {"pause", "resume"}:
            raise ValueError("unsupported request")
        with self.db:
            if self._replay(obj, "control_request"):
                return {"delivery": "pending", "replayed": True}
            row = self.db.execute("SELECT data FROM development_tasks WHERE task_id=?",
                                  (obj["task_id"],)).fetchone()
            task = json.loads(row["data"]) if row else None
            if (not task or PROJECTS[task["project"]] != "active" or
                    task["status"] in {"completed", "failed"}):
                raise ValueError("eligible task required")
            self._event(obj, "control_request", actor, self.clock())
        return {"delivery": "pending", "replayed": False}

    def snapshot(self):
        now = self.clock()
        tasks = []
        for row in self.db.execute("SELECT * FROM development_tasks ORDER BY received_at DESC, task_id"):
            task = json.loads(row["data"])
            age = now - row["received_at"]
            task.update(received_at=row["received_at"],
                        freshness="recent report" if 0 <= age <= 90 else "stale / unknown",
                        pr_verification="unknown", ci="unknown", worktree="unknown")
            tasks.append(task)
        events = [dict(id=r["id"], kind=r["kind"], received_at=r["received_at"],
                       data=json.loads(r["data"])) for r in self.db.execute(
                           "SELECT * FROM development_events ORDER BY id DESC LIMIT 200")]
        return {"projects": PROJECTS, "tasks": tasks, "events": events,
                "source": "owner-submitted reports", "executor_connected": False}
