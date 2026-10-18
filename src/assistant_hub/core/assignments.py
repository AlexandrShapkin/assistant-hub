"""Offline, durable assignment ledger. No executor transport or dispatch."""
import json
import sqlite3
from uuid import UUID


class AssignmentLedger:
    """Persist commands and executor events with idempotent, ordered updates."""

    def __init__(self, store):
        self.db = store.db
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS executor_assignments (
                    task_id TEXT PRIMARY KEY,
                    executor_id TEXT NOT NULL,
                    generation INTEGER NOT NULL CHECK(generation > 0),
                    idempotency_key TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN (
                        'pending', 'accepted', 'running', 'completed', 'failed',
                        'cancel_requested', 'cancelled', 'needs_reconciliation')),
                    last_sequence INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(executor_id, idempotency_key));
                CREATE TABLE IF NOT EXISTS executor_events (
                    message_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES executor_assignments(task_id),
                    sequence INTEGER NOT NULL CHECK(sequence > 0),
                    kind TEXT NOT NULL,
                    UNIQUE(task_id, sequence));
            """)

    def assign(self, task_id, executor_id, generation, idempotency_key):
        if (not all(isinstance(v, str) and 0 < len(v) <= 128
                    for v in (task_id, executor_id, idempotency_key))
                or type(generation) is not int or generation < 1):
            raise ValueError("invalid assignment")
        with self.db:
            existing = self.db.execute(
                "SELECT task_id, executor_id, generation, idempotency_key "
                "FROM executor_assignments WHERE task_id=? OR "
                "(executor_id=? AND idempotency_key=?)",
                (task_id, executor_id, idempotency_key)).fetchone()
            expected = (task_id, executor_id, generation, idempotency_key)
            if existing:
                if tuple(existing) != expected:
                    raise ValueError("conflicting assignment")
                return False
            self.db.execute(
                "INSERT INTO executor_assignments "
                "(task_id, executor_id, generation, idempotency_key, state) "
                "VALUES (?, ?, ?, ?, 'pending')", expected)
            return True

    def record_event(self, task_id, message_id, sequence, generation, kind):
        transitions = {
            'accepted': ('pending', 'accepted'),
            'started': ('accepted', 'running'),
            'heartbeat': ('running', 'running'),
            'progress': ('running', 'running'),
            'completed': ('running', 'completed'),
            'failed': ('running', 'failed'),
            'cancel_requested': ('pending', 'cancel_requested'),
            'cancelled': ('cancel_requested', 'cancelled'),
        }
        if (kind not in transitions or type(sequence) is not int or sequence < 1
                or type(generation) is not int or generation < 1):
            raise ValueError("invalid event")
        try:
            UUID(message_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("invalid message id") from None
        with self.db:
            old = self.db.execute(
                "SELECT task_id, sequence, kind FROM executor_events WHERE message_id=?",
                (message_id,)).fetchone()
            if old:
                if tuple(old) != (task_id, sequence, kind):
                    raise ValueError("conflicting message id")
                return False
            row = self.db.execute(
                "SELECT generation, state, last_sequence FROM executor_assignments "
                "WHERE task_id=?", (task_id,)).fetchone()
            if not row or row["generation"] != generation:
                raise ValueError("unknown task or stale generation")
            if sequence <= row["last_sequence"]:
                raise ValueError("out-of-order event")
            required, new_state = transitions[kind]
            if row["state"] != required:
                raise ValueError("invalid state transition")
            self.db.execute(
                "INSERT INTO executor_events VALUES (?, ?, ?, ?)",
                (message_id, task_id, sequence, kind))
            self.db.execute(
                "UPDATE executor_assignments SET state=?, last_sequence=? WHERE task_id=?",
                (new_state, sequence, task_id))
            return True

    def status(self, task_id):
        row = self.db.execute(
            "SELECT task_id, executor_id, generation, state, last_sequence "
            "FROM executor_assignments WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None
