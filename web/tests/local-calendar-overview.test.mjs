import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CALENDAR_ZONE, LOOKAHEAD_DAYS, STALE_AFTER_HOURS,
  currentCalendarWeek, preferredCalendarWeek,
  weekSnapshotState, upcomingCalendarLessons,
} from '../../src/assistant_hub/local_web/calendar_overview.mjs';

const instant = value => new Date(value);
const w = (week, imported_at = '2026-10-18 02:00:00') => ({week, imported_at, count: 2});
const lesson = (timestamp, external_id, service_id = 'local-calendar') => ({
  service_id, account_id: 'weekly-ics', timestamp, external_id, title: 'Fake ' + external_id,
});

test('calendar week anchored to Altai civil time, not device/UTC day', () => {
  assert.equal(CALENDAR_ZONE, 'Asia/Barnaul');
  assert.equal(currentCalendarWeek(instant('2026-10-18T16:59:59Z')), '2026-10-12');
  assert.equal(currentCalendarWeek(instant('2026-10-18T17:00:00Z')), '2026-10-19');
  assert.equal(currentCalendarWeek(instant('2026-10-11T17:00:00Z')), '2026-10-12');
  assert.equal(currentCalendarWeek(instant('2026-12-31T19:00:00Z')), '2026-12-28');
  assert.equal(currentCalendarWeek(instant('2027-01-03T17:00:00Z')), '2027-01-04');
  assert.throws(() => currentCalendarWeek(new Date(NaN)), TypeError);
});

test('prefers current week, otherwise next upcoming, then most recent past', () => {
  const now = instant('2026-10-18T12:00:00Z');
  assert.equal(preferredCalendarWeek([], now), null);
  assert.equal(preferredCalendarWeek([w('2026-10-05'), w('2026-10-12'), w('2026-10-19')], now),
    '2026-10-12');
  assert.equal(preferredCalendarWeek([w('2026-10-05'), w('2026-10-19'), w('2026-11-02')], now),
    '2026-10-19');
  assert.equal(preferredCalendarWeek([w('2026-09-28'), w('2026-10-05')], now), '2026-10-05');
  assert.equal(preferredCalendarWeek([w('not-a-week')], now), null);
});

test('freshness warning cannot claim a missing or stale week is up to date', () => {
  const now = instant('2026-10-18T12:00:00Z');
  assert.equal(STALE_AFTER_HOURS, 48);
  assert.deepEqual(weekSnapshotState([], now), {week: '2026-10-12', state: 'missing'});
  assert.deepEqual(weekSnapshotState([w('2026-10-19')], now),
    {week: '2026-10-12', state: 'missing'});
  assert.equal(weekSnapshotState([w('2026-10-12', '2026-10-18 11:59:59')], now).state, 'recent');
  assert.equal(weekSnapshotState([w('2026-10-12', '2026-10-16 12:00:00')], now).state, 'stale');
  assert.equal(weekSnapshotState([w('2026-10-12', '2026-10-18 12:00:01')], now).state, 'unknown');
  assert.equal(weekSnapshotState([w('2026-10-12', 'invalid')], now).state, 'unknown');
  assert.equal(weekSnapshotState([w('2026-10-12', '2026-10-15 02:00:00')], now).state, 'stale');
  assert.equal(weekSnapshotState([w('2026-10-12', '2026-10-18T11:00:00Z')], now).state, 'unknown');
});

test('upcoming lessons are sorted and bounded to 14 days across weeks', () => {
  const now = instant('2026-10-18T12:00:00Z');
  assert.equal(LOOKAHEAD_DAYS, 14);
  const records = [
    lesson('2026-10-18T11:59:00Z', 'old'),
    lesson('2026-10-20T15:00:00Z', 'late'),
    lesson('2026-10-19T03:00:00Z', 'next'),
    lesson('2026-10-20T15:00:00Z', 'a-tie'),
    lesson('2026-11-02T12:00:01Z', 'too-late'),
    lesson('2026-10-19T01:00:00Z', 'unrelated', 'demo'),
    {...lesson('2026-10-19T02:00:00Z', 'wrong-account'), account_id: 'another'},
    lesson('bogus', 'broken'),
  ];
  assert.deepEqual(upcomingCalendarLessons(records, now, 3).map(e => e.external_id),
    ['next', 'a-tie', 'late']);
  assert.deepEqual(upcomingCalendarLessons(records, now, 1).map(e => e.external_id), ['next']);
  assert.equal(upcomingCalendarLessons(records, now, 3).length, 3);
  assert.deepEqual(upcomingCalendarLessons(records, instant('2027-01-01T00:00:00Z')), []);
  assert.throws(() => upcomingCalendarLessons(records, now, 0), RangeError);
  assert.throws(() => upcomingCalendarLessons(records, now, 21), RangeError);
  assert.throws(() => upcomingCalendarLessons(records, new Date(NaN)), RangeError);
});
