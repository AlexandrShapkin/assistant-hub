"""Provider-specific weekly calendar persistence on the existing SQLite transaction.

Uses the database and audit callback owned by core Store. No connection, schema,
commit, or permission lifecycle is created here.
"""
import json
import sqlite3
from dataclasses import asdict
from typing import Callable

from .calendar_import import SERVICE as CALENDAR_SERVICE, ACCOUNT as CALENDAR_ACCOUNT
from .core.store import encode


class CalendarPersistence:
    def __init__(self, db: sqlite3.Connection, audit: Callable[[str, str, str], None]) -> None:
        self.db = db
        self._audit = audit

    @staticmethod
    def _calendar_display(data: dict) -> dict:
        """Snapshot only useful calendar fields, excluding UID/provenance."""
        attrs = data["attributes"]
        return {"title": data["title"], "time": attrs.get("time_local", ""),
                "date": attrs.get("date_local", ""), "location": attrs.get("location", ""),
                "body": data["body"], "timestamp": data["timestamp"]}

    def import_calendar_week(self, week: str, events: tuple) -> dict:
        """Replace just one owner-imported week atomically; retain other weeks."""
        if (not isinstance(week, str) or len(week) != 10 or
                not isinstance(events, tuple) or not 1 <= len(events) <= 80 or
                len({event.external_id for event in events}) != len(events) or
                any(event.service_id != CALENDAR_SERVICE or
                    event.account_id != CALENDAR_ACCOUNT or
                    event.kind != "calendar.lesson" or
                    event.attributes.get("week_start") != week for event in events)):
            raise ValueError("invalid weekly calendar snapshot")
        with self.db:
            baseline_exists = self.db.execute(
                "SELECT 1 FROM calendar_weeks WHERE week_start=?", (week,)).fetchone() is not None
            rows = self.db.execute(
                "SELECT external_id, data FROM events WHERE service=? AND account=?",
                (CALENDAR_SERVICE, CALENDAR_ACCOUNT)).fetchall()
            previous = {}
            for row in rows:
                data = json.loads(row["data"])
                if data.get("attributes", {}).get("week_start") == week:
                    previous[row["external_id"]] = data
            current = set()
            changes = []
            added = changed = 0
            for event in events:
                data = asdict(event)
                data["timestamp"] = event.timestamp.isoformat()
                serialized = encode(data)
                key = event.external_id
                current.add(key)
                before = previous.get(key)
                after_visible = self._calendar_display(data)
                if before is None:
                    self.db.execute("INSERT INTO events VALUES (?, ?, ?, ?)",
                                    (CALENDAR_SERVICE, CALENDAR_ACCOUNT, key, serialized))
                    added += 1
                    if baseline_exists:
                        changes.append((week, key, "added", None, encode(after_visible)))
                else:
                    before_visible = self._calendar_display(before)
                    if before_visible != after_visible:
                        changed += 1
                        changes.append((week, key, "updated", encode(before_visible),
                                        encode(after_visible)))
                    # Provenance-only changes silently refresh source metadata.
                    if encode(before) != serialized:
                        self.db.execute(
                            "UPDATE events SET data=? WHERE service=? AND account=? AND external_id=?",
                            (serialized, CALENDAR_SERVICE, CALENDAR_ACCOUNT, key))
            removed = previous.keys() - current
            for key in removed:
                if baseline_exists:
                    changes.append((week, key, "removed",
                                    encode(self._calendar_display(previous[key])), None))
                self.db.execute("DELETE FROM event_states WHERE service=? AND account=? AND external_id=?",
                                (CALENDAR_SERVICE, CALENDAR_ACCOUNT, key))
                self.db.execute("DELETE FROM events WHERE service=? AND account=? AND external_id=?",
                                (CALENDAR_SERVICE, CALENDAR_ACCOUNT, key))
            # Log changes only after a baseline exists. New subscriptions and
            # imports do not generate dozens of misleading 'new class' alerts.
            for record in changes:
                self.db.execute(
                    "INSERT INTO calendar_changes(week_start, external_id, kind, before_json, after_json) "
                    "VALUES (?, ?, ?, ?, ?)", record)
            # Keep at most 500 private recent changes, avoiding unbounded growth.
            self.db.execute("DELETE FROM calendar_changes WHERE id NOT IN "
                            "(SELECT id FROM calendar_changes ORDER BY id DESC LIMIT 500)")
            self.db.execute(
                "INSERT INTO calendar_weeks(week_start, event_count) VALUES (?, ?) "
                "ON CONFLICT(week_start) DO UPDATE SET "
                "imported_at=CURRENT_TIMESTAMP, event_count=excluded.event_count",
                (week, len(events)))
            result = {"week": week, "count": len(events), "added": added,
                      "changed": changed, "removed": len(removed)}
            self._audit("calendar-import", week, encode(result))
        return result

    def calendar_weeks(self) -> list[dict]:
        return [dict(row) for row in self.db.execute(
            "SELECT week_start AS week, imported_at, event_count AS count "
            "FROM calendar_weeks ORDER BY week_start DESC LIMIT 104")]

    def calendar_changes(self, limit=200) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("invalid calendar change limit")
        return [{"id": row["id"], "week": row["week_start"], "kind": row["kind"],
                 "before": json.loads(row["before_json"]) if row["before_json"] else None,
                 "after": json.loads(row["after_json"]) if row["after_json"] else None,
                 "recorded_at": row["recorded_at"]}
                for row in self.db.execute(
                    "SELECT id, week_start, kind, before_json, after_json, recorded_at "
                    "FROM calendar_changes ORDER BY id DESC LIMIT ?", (limit,))]

