"""Offline iCalendar fixture tests; no real person, group, school or network."""
from contextlib import closing
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from assistant_hub.calendar_import import parse_ical, SERVICE, ACCOUNT, MAX_ICAL_BYTES
from assistant_hub.core.store import Store


def event(uid, title="Synthetic lecture", start="20261012T112000", end="20261012T125000",
          location="Room A", description="Teacher Example"):
    return (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART;TZID=Asia/Barnaul:{start}\r\n"
        f"DTEND;TZID=Asia/Barnaul:{end}\r\n"
        f"SUMMARY:{title}\r\n"
        f"LOCATION:{location}\r\n"
        f"DESCRIPTION:{description}\r\n"
        "END:VEVENT\r\n"
    )


def calendar(*entries):
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Synthetic Tests//EN\r\n" + "".join(entries) + "END:VCALENDAR\r\n"


class CalendarImportTests(unittest.TestCase):
    def test_week_timezone_metadata_and_escape(self):
        raw = calendar(event("uid-a", "C\\, D\\; E", description=r"Part one\nPart two"),
                       event("uid-b", start="20261013T182000", end="20261013T195000"))
        week, lessons = parse_ical(raw)
        self.assertEqual(week, "2026-10-12")
        self.assertEqual(len(lessons), 2)
        first = lessons[0]
        self.assertEqual((first.service_id, first.account_id, first.kind),
                         (SERVICE, ACCOUNT, "calendar.lesson"))
        self.assertEqual(first.timestamp.isoformat(), "2026-10-12T04:20:00+00:00")
        self.assertEqual(first.title, "C, D; E")
        self.assertIn("Part one\nPart two", first.body)
        self.assertEqual(first.attributes["time_local"], "11:20–12:50")
        self.assertEqual(first.attributes["location"], "Room A")
        self.assertNotIn("uid-a", first.external_id)
        self.assertEqual(parse_ical(raw)[1][0].external_id, first.external_id)

    def test_utc_datetime_and_floating_are_localized(self):
        a = event("utc", start="20261012T042000Z", end="20261012T055000Z")
        a = a.replace("DTSTART;TZID=Asia/Barnaul:", "DTSTART:").replace(
            "DTEND;TZID=Asia/Barnaul:", "DTEND:")
        b = event("floating")
        b = b.replace("DTSTART;TZID=Asia/Barnaul:", "DTSTART:").replace(
            "DTEND;TZID=Asia/Barnaul:", "DTEND:")
        week, lessons = parse_ical(calendar(a, b))
        self.assertEqual(week, "2026-10-12")
        self.assertEqual({e.attributes["time_local"] for e in lessons}, {"11:20–12:50"})

    def test_folded_utf8_and_nonexecuted_markup(self):
        raw = calendar(event("uid-a", title="<img src=x onerror=alert(1)>",
                             description="First line\\nSecond line"))
        raw = raw.replace("SUMMARY:<img src=x onerror=alert(1)>",
                          "SUMMARY:<img src=x onerror=" + "\r\n" + " alert(1)>")
        lesson = parse_ical(raw)[1][0]
        self.assertEqual(lesson.title, "<img src=x onerror=alert(1)>")
        self.assertEqual(lesson.attributes["provenance"], "manual-ics")
        self.assertNotIn("\\n", lesson.body)

    def test_reject_bad_calendar(self):
        good = calendar(event("one"))
        invalid = [
            "", "<html></html>", good.replace("VERSION:2.0", "VERSION:1.0"),
            good.replace("BEGIN:VEVENT", "BEGIN:VTODO"),
            good.replace("END:VEVENT", "END:VCALENDAR"),
            good.replace("UID:one", "UID:"),
            good.replace("UID:one", "UID:one\r\nUID:two"),
            good.replace("DTSTART;TZID=Asia/Barnaul:", "DTSTART;TZID=Etc/../../oops:"),
            good.replace("DTSTART;TZID=Asia/Barnaul:20261012T112000",
                         "DTSTART;VALUE=DATE:20261012"),
            good.replace("DTEND;TZID=Asia/Barnaul:20261012T125000",
                         "DTEND;TZID=Asia/Barnaul:20261012T102000"),
            good.replace("END:VEVENT", "RRULE:FREQ=WEEKLY\r\nEND:VEVENT"),
            good.replace("END:VEVENT", "RDATE:20261013T102000Z\r\nEND:VEVENT"),
            good.replace("END:VEVENT", "EXDATE:20261013T102000Z\r\nEND:VEVENT"),
            good.replace("END:VEVENT", "RECURRENCE-ID:20261012T112000Z\r\nEND:VEVENT"),
            good.replace("SUMMARY:Synthetic lecture", "SUMMARY:"),
            good.replace("SUMMARY:Synthetic lecture", "SUMMARY:bad\\xescape"),
            good.replace("SUMMARY:Synthetic lecture", "SUMMARY:ok\x00"),
            good.replace("BEGIN:VEVENT", "BEGIN:VEVENT\r\nBEGIN:VEVENT"),
            good.replace("END:VCALENDAR", "END:VCALENDAR\r\nGET http://evil.invalid"),
            calendar(event("one"), event("one")),
            calendar(event("one"), event("two", start="20261019T112000", end="20261019T125000")),
            calendar(event("one", start="20261018T233000", end="20261019T003000")),
            good * 200,
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
        ]
        for n, case in enumerate(invalid):
            with self.subTest(case=n), self.assertRaises(ValueError):
                parse_ical(case)
        with self.assertRaises(ValueError):
            parse_ical(good + "a" * MAX_ICAL_BYTES)
        with self.assertRaises(ValueError):
            parse_ical(123)

    def test_cancelled_lessons_do_not_get_imported(self):
        a = event("ok")
        b = event("canceled", start="20261013T112000", end="20261013T125000")
        b = b.replace("END:VEVENT", "STATUS:CANCELLED\r\nEND:VEVENT")
        week, lessons = parse_ical(calendar(a, b))
        self.assertEqual(week, "2026-10-12")
        self.assertEqual(len(lessons), 1)
        with self.assertRaises(ValueError):
            parse_ical(calendar(b))

    def test_multiple_weeks_update_and_remove_only_target_week(self):
        week_a, a = parse_ical(calendar(event("a"), event("b", start="20261013T182000",
                                                     end="20261013T195000")))
        week_b, b = parse_ical(calendar(event("week-b", start="20261019T112000",
                                                     end="20261019T125000")))
        with tempfile.TemporaryDirectory() as tmp, closing(Store(Path(tmp) / "db")) as store:
            self.assertEqual(store.import_calendar_week(week_a, a),
                             {"week": week_a, "count": 2, "added": 2, "changed": 0, "removed": 0})
            self.assertEqual(store.import_calendar_week(week_b, b)["added"], 1)
            store.set_status(SERVICE, ACCOUNT, a[0].external_id, "done", "owner")
            modified = event("a", "Updated lecture", location="Other room")
            new_week, changed = parse_ical(calendar(modified))
            stats = store.import_calendar_week(new_week, changed)
            self.assertEqual((stats["added"], stats["changed"], stats["removed"]), (0, 1, 1))
            self.assertEqual(len(store.inbox()), 2)
            self.assertEqual({i["title"] for i in store.inbox()}, {"Updated lecture", "Synthetic lecture"})
            self.assertEqual(
                next(i for i in store.inbox_with_status()
                     if i["external_id"] == a[0].external_id)["status"], "done")
            self.assertEqual({r["week"] for r in store.calendar_weeks()}, {week_a, week_b})
            self.assertEqual(store.import_calendar_week(new_week, changed)["changed"], 0)
            audit = [row for row in store.audit() if row["kind"] == "calendar-import"]
            self.assertEqual(len(audit), 4)

    def test_transaction_rolls_back_on_failure(self):
        week, a = parse_ical(calendar(event("a")))
        _, b = parse_ical(calendar(event("a", "Changed")))
        with tempfile.TemporaryDirectory() as tmp, closing(Store(Path(tmp) / "db")) as store:
            store.import_calendar_week(week, a)
            before = (store.inbox(), store.audit(), store.calendar_weeks())
            store.db.execute("""CREATE TRIGGER calendar_no_update BEFORE UPDATE ON events
                                WHEN OLD.service='local-calendar'
                                BEGIN SELECT RAISE(ABORT, 'forced rollback'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                store.import_calendar_week(week, b)
            self.assertEqual(before, (store.inbox(), store.audit(), store.calendar_weeks()))


    def test_calendar_audit_failure_rolls_back_every_write(self):
        week, original = parse_ical(calendar(event("audit-uid")))
        _, changed = parse_ical(calendar(event("audit-uid", title="Changed")))
        with tempfile.TemporaryDirectory() as tmp, closing(Store(Path(tmp) / "db")) as store:
            store.import_calendar_week(week, original)
            before = (store.inbox(), store.audit(), store.calendar_weeks(),
                      store.calendar_changes())
            with patch.object(store, "_audit", side_effect=RuntimeError("audit unavailable")):
                with self.assertRaises(RuntimeError):
                    store.import_calendar_week(week, changed)
            self.assertEqual(
                (store.inbox(), store.audit(), store.calendar_weeks(),
                 store.calendar_changes()), before
            )

    def test_importing_core_store_does_not_load_calendar_provider(self):
        import subprocess
        import sys
        source = Path(__file__).resolve().parents[1] / "src"
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "import assistant_hub.core.store; "
                "assert 'assistant_hub.calendar_import' not in sys.modules")
        result = subprocess.run([sys.executable, "-c", code, str(source)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
