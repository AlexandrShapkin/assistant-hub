"""Private timetable change tracking using synthetic iCalendar snapshots only."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from assistant_hub.calendar_import import parse_ical, SERVICE, ACCOUNT
from assistant_hub.core.store import Store
from tests.test_calendar_import import calendar, event


class CalendarChangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "hub.sqlite3"

    def ingest(self, store, *entries, provenance='manual-ics'):
        week, snapshot = parse_ical(calendar(*entries), provenance=provenance)
        return store.import_calendar_week(week, snapshot)

    def test_initial_snapshot_creates_no_change_spam_and_repeat_is_idempotent(self):
        with closing(Store(self.path)) as store:
            first = self.ingest(store, event("synthetic-a"))
            self.assertEqual((first['added'], first['changed'], first['removed']), (1, 0, 0))
            self.assertEqual(store.calendar_changes(), [])
            self.assertEqual(self.ingest(store, event("synthetic-a"))['changed'], 0)
            self.assertEqual(store.calendar_changes(), [])
            self.assertEqual(store.calendar_weeks()[0]['count'], 1)
        with closing(Store(self.path)) as store:
            self.assertEqual(store.calendar_changes(), [])

    def test_add_room_move_and_removal_have_private_before_after_details(self):
        a = event("synthetic-a", title="Fictional seminar")
        b = event("synthetic-b", title="Example lab", start="20261013T182000",
                  end="20261013T195000")
        with closing(Store(self.path)) as store:
            self.ingest(store, a)
            store.set_status(SERVICE, ACCOUNT,
                             parse_ical(calendar(a))[1][0].external_id, 'done', 'owner')
            added = self.ingest(store, a, b)
            self.assertEqual(added['added'], 1)
            changes = store.calendar_changes()
            self.assertEqual([x['kind'] for x in changes], ['added'])
            self.assertIsNone(changes[0]['before'])
            self.assertEqual(changes[0]['after']['title'], 'Example lab')
            self.assertEqual(changes[0]['after']['time'], '18:20–19:50')
            self.assertNotIn('synthetic-b', str(changes))  # raw upstream UID isn't returned
            self.assertEqual(store.import_calendar_week(
                *parse_ical(calendar(a, b)))['added'], 0)
            self.assertEqual(len(store.calendar_changes()), 1)

            moved = event("synthetic-a", title="Fictional seminar",
                          location="Room B", start="20261012T132000", end="20261012T145000")
            changed = self.ingest(store, moved, b)
            self.assertEqual(changed['changed'], 1)
            changes = store.calendar_changes()
            self.assertEqual(changes[0]['kind'], 'updated')
            self.assertEqual(changes[0]['before']['time'], '11:20–12:50')
            self.assertEqual(changes[0]['after']['time'], '13:20–14:50')
            self.assertEqual(changes[0]['before']['location'], 'Room A')
            self.assertEqual(changes[0]['after']['location'], 'Room B')
            item = next(e for e in store.inbox_with_status() if e['title'] == 'Fictional seminar')
            self.assertEqual(item['status'], 'done')

            deleted = self.ingest(store, moved)
            self.assertEqual(deleted['removed'], 1)
            changes = store.calendar_changes()
            self.assertEqual(changes[0]['kind'], 'removed')
            self.assertEqual(changes[0]['before']['title'], 'Example lab')
            self.assertIsNone(changes[0]['after'])
            self.assertEqual([c['kind'] for c in changes], ['removed', 'updated', 'added'])
            self.assertTrue(all(c['week'] == '2026-10-12' for c in changes))

    def test_provenance_change_does_not_trigger_false_alert(self):
        raw = event("synthetic-a")
        with closing(Store(self.path)) as store:
            self.ingest(store, raw, provenance='manual-ics')
            response = self.ingest(store, raw, provenance='subscription-ics')
            self.assertEqual(response['changed'], 0)
            self.assertEqual(store.calendar_changes(), [])
            self.assertEqual(store.inbox()[0]['attributes']['provenance'], 'subscription-ics')

    def test_other_weeks_preserved_and_reopen_reads_history(self):
        a = event("synthetic-a")
        b = event("synthetic-b", start="20261019T112000", end="20261019T125000")
        with closing(Store(self.path)) as store:
            self.ingest(store, a)
            self.ingest(store, b)
            self.ingest(store, event("synthetic-a", title="Changed"))
            self.assertEqual(len(store.calendar_changes()), 1)
            self.assertEqual({e['attributes']['week_start'] for e in store.inbox()},
                             {'2026-10-12', '2026-10-19'})
        with closing(Store(self.path)) as store:
            self.assertEqual(len(store.calendar_changes()), 1)
            self.assertEqual(store.calendar_changes()[0]['kind'], 'updated')
            with self.assertRaises(ValueError):
                store.calendar_changes(0)
            with self.assertRaises(ValueError):
                store.calendar_changes(201)

    def test_failed_transaction_does_not_log_change_or_replace_lesson(self):
        a = event('synthetic-a', title='Original')
        changed = event('synthetic-a', title='Edited')
        with closing(Store(self.path)) as store:
            self.ingest(store, a)
            before = (store.inbox(), store.calendar_changes(), store.calendar_weeks())
            store.db.execute("""CREATE TRIGGER block_calendar_change_insert
                 BEFORE INSERT ON calendar_changes BEGIN SELECT RAISE(ABORT, 'forced'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                self.ingest(store, changed)
            self.assertEqual((store.inbox(), store.calendar_changes(), store.calendar_weeks()), before)

    def test_history_is_bounded_to_500_rows(self):
        with closing(Store(self.path)) as store:
            self.ingest(store, event("initial"))
            for i in range(515):
                self.ingest(store, event("initial", title=f"Changed synthetic class {i}"))
            self.assertEqual(store.db.execute(
                'SELECT COUNT(*) FROM calendar_changes').fetchone()[0], 500)
            self.assertEqual(len(store.calendar_changes()), 200)
            self.assertEqual(store.calendar_changes()[0]['after']['title'],
                             'Changed synthetic class 514')
            self.assertEqual(store.calendar_changes()[-1]['kind'], 'updated')


if __name__ == "__main__":
    unittest.main()
