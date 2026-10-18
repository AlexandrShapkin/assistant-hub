// Pure timetable presentation helpers. No fetch, cookies, storage or background timers.
// All calendar dates use the university's civil timezone, not the browser timezone.
export const CALENDAR_ZONE = 'Asia/Barnaul';
export const LOOKAHEAD_DAYS = 14;
export const STALE_AFTER_HOURS = 48;

export function currentCalendarWeek(now = new Date()) {
  if (!(now instanceof Date) || !Number.isFinite(now.getTime())) throw new TypeError('invalid date');
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: CALENDAR_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(now).filter(part => part.type !== 'literal')
      .map(part => [part.type, Number(part.value)]));
  const date = Date.UTC(parts.year, parts.month - 1, parts.day);
  const weekday = (new Date(date).getUTCDay() + 6) % 7; // Monday = 0.
  return new Date(date - weekday * 86400000).toISOString().slice(0, 10);
}

export function preferredCalendarWeek(weeks, now = new Date()) {
  const current = currentCalendarWeek(now);
  const values = weeks.map(week => week.week)
    .filter(value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value));
  if (values.includes(current)) return current;
  // Show the nearest upcoming week rather than silently defaulting to an old one.
  return values.filter(value => value > current).sort()[0] ??
    values.filter(value => value < current).sort().at(-1) ?? null;
}

function parsedImportTimestamp(value) {
  if (typeof value !== 'string') return NaN;
  // sqlite CURRENT_TIMESTAMP is UTC without an explicit offset.
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) {
    return Date.parse(value.replace(' ', 'T') + 'Z');
  }
  return NaN; // Do not trust unknown local-time formats.
}

export function weekSnapshotState(weeks, now = new Date()) {
  const current = currentCalendarWeek(now);
  const item = weeks.find(week => week.week === current);
  if (!item) return {week: current, state: 'missing'};
  const updated = parsedImportTimestamp(item.imported_at);
  if (!Number.isFinite(updated) || updated > now.getTime()) {
    return {week: current, state: 'unknown'};
  }
  const hours = (now.getTime() - updated) / 3600000;
  return {week: current, state: hours >= STALE_AFTER_HOURS ? 'stale' : 'recent'};
}

export function upcomingCalendarLessons(events, now = new Date(), limit = 3) {
  const start = now.getTime();
  const end = start + LOOKAHEAD_DAYS * 86400000;
  if (!Number.isFinite(start) || !Number.isInteger(limit) || limit < 1 || limit > 20) {
    throw new RangeError('invalid upcoming lesson arguments');
  }
  return events.filter(item => item.service_id === 'local-calendar' &&
      item.account_id === 'weekly-ics' &&
      typeof item.timestamp === 'string' &&
      Number.isFinite(Date.parse(item.timestamp)) &&
      Date.parse(item.timestamp) >= start &&
      Date.parse(item.timestamp) <= end)
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp) ||
      a.external_id.localeCompare(b.external_id))
    .slice(0, limit);
}
