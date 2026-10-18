"""Offline, durable assignment ledger. No executor transport or dispatch."""
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
                    lease_deadline INTEGER,
                    UNIQUE(executor_id, idempotency_key));
                CREATE TABLE IF NOT EXISTS executor_events (
                    message_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES executor_assignments(task_id),
                    sequence INTEGER NOT NULL CHECK(sequence > 0),
                    kind TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    UNIQUE(task_id, sequence));
                CREATE TABLE IF NOT EXISTS executor_outbox (
                    task_id TEXT PRIMARY KEY REFERENCES executor_assignments(task_id),
                    command TEXT NOT NULL CHECK(command = 'assign'),
                    delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)));
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
            self.db.execute(
                "INSERT INTO executor_outbox(task_id, command) VALUES (?, 'assign')",
                (task_id,))
            return True

    def record_event(self, task_id, message_id, sequence, generation, kind):
        transitions = {
            'accepted': ('pending', 'accepted'),
            'started': ('accepted', 'running'),
            'heartbeat': ('running', 'running'),
            'progress': ('running', 'running'),
            'completed': ('running', 'completed'),
            'failed': ('running', 'failed'),
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
                "SELECT task_id, sequence, kind, generation FROM executor_events WHERE message_id=?",
                (message_id,)).fetchone()
            if old:
                if tuple(old) != (task_id, sequence, kind, generation):
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
            # Completion can race with a locally requested cancellation.
            # The executor's terminal result is authoritative.
            if kind in ('completed', 'failed') and row['state'] == 'cancel_requested':
                pass
            elif row["state"] != required:
                raise ValueError("invalid state transition")
            self.db.execute(
                "INSERT INTO executor_events VALUES (?, ?, ?, ?, ?)",
                (message_id, task_id, sequence, kind, generation))
            self.db.execute(
                "UPDATE executor_assignments SET state=?, last_sequence=? WHERE task_id=?",
                (new_state, sequence, task_id))
            return True

    def status(self, task_id):
        row = self.db.execute(
            "SELECT task_id, executor_id, generation, state, last_sequence "
            "FROM executor_assignments WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def pending_commands(self):
        """Read pending durable commands; caller must deliver at least once."""
        return [dict(row) for row in self.db.execute(
            "SELECT o.task_id, o.command, a.executor_id, a.generation, "
            "a.idempotency_key FROM executor_outbox o "
            "JOIN executor_assignments a ON a.task_id=o.task_id "
            "WHERE o.delivered=0 AND a.state='pending' ORDER BY o.rowid")]

    def mark_delivered(self, task_id):
        """Local transport receipt, not executor acceptance."""
        with self.db:
            return bool(self.db.execute(
                "UPDATE executor_outbox SET delivered=1 "
                "WHERE task_id=? AND delivered=0", (task_id,)).rowcount)

    def lease(self, task_id, generation, deadline, now):
        """Set a bounded deadline; never automatically reassign expired work."""
        if (type(generation) is not int or generation < 1 or
                type(deadline) is not int or type(now) is not int or
                deadline <= now):
            raise ValueError("invalid lease")
        with self.db:
            row = self.db.execute(
                "SELECT generation, state FROM executor_assignments WHERE task_id=?",
                (task_id,)).fetchone()
            if not row or row["generation"] != generation or row["state"] not in (
                    "pending", "accepted", "running"):
                raise ValueError("lease not eligible")
            self.db.execute(
                "UPDATE executor_assignments SET lease_deadline=? WHERE task_id=?",
                (deadline, task_id))

    def reconcile_expired(self, now):
        """Mark expired nonterminal tasks for explicit status reconciliation."""
        if type(now) is not int:
            raise ValueError("invalid timestamp")
        with self.db:
            rows = self.db.execute(
                "SELECT task_id FROM executor_assignments "
                "WHERE lease_deadline IS NOT NULL AND lease_deadline<=? "
                "AND state IN ('pending','accepted','running')", (now,)).fetchall()
            self.db.execute(
                "UPDATE executor_assignments SET state='needs_reconciliation' "
                "WHERE lease_deadline IS NOT NULL AND lease_deadline<=? "
                "AND state IN ('pending','accepted','running')", (now,))
            return [row["task_id"] for row in rows]

    def request_cancel(self, task_id, generation):
        """Record a cancellation request, never assume termination."""
        if type(generation) is not int or generation < 1:
            raise ValueError("invalid generation")
        with self.db:
            row = self.db.execute(
                "SELECT generation, state FROM executor_assignments WHERE task_id=?",
                (task_id,)).fetchone()
            if not row or row["generation"] != generation:
                raise ValueError("unknown task or generation")
            if row["state"] == "cancel_requested":
                return False
            if row["state"] not in ("pending", "accepted", "running"):
                raise ValueError("cannot cancel terminal or uncertain task")
            self.db.execute(
                "UPDATE executor_assignments SET state='cancel_requested' "
                "WHERE task_id=?", (task_id,))
            # A not-yet-sent assignment must not be dispatched after cancellation.
            self.db.execute(
                "UPDATE executor_outbox SET delivered=1 WHERE task_id=? "
                "AND delivered=0", (task_id,))
            return True

    def reconcile_status(self, task_id, generation, executor_state):
        """A verified status observation only; no implicit redispatch."""
        if executor_state not in ("accepted", "running", "completed", "failed",
                                  "cancelled", "not_found"):
            raise ValueError("invalid executor state")
        with self.db:
            row = self.db.execute(
                "SELECT generation, state FROM executor_assignments WHERE task_id=?",
                (task_id,)).fetchone()
            if not row or row["generation"] != generation or (
                    row["state"] != "needs_reconciliation"):
                raise ValueError("reconciliation not eligible")
            if executor_state == "not_found":
                return False
            self.db.execute(
                "UPDATE executor_assignments SET state=?, lease_deadline=NULL "
                "WHERE task_id=?", (executor_state, task_id))
            return True
