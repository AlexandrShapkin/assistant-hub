import { DEFAULT_LOCALE, LOCALES, t, formatDate } from './i18n.mjs';
import {
  preferredCalendarWeek, weekSnapshotState, upcomingCalendarLessons,
} from './calendar_overview.mjs';
// Session proof stays in this module's memory. Refresh deliberately logs out.
let token = null;
let events = [];
let services = [];
let selected = null;
let locale = DEFAULT_LOCALE;
let noticeState = null;
let calendarWeeks = [];
let calendarChanges = [];
let selectedWeek = null;
const $ = id => document.getElementById(id);
const tr = (key, params) => t(locale, key, params);
const notice = (key, params = {}) => {
  noticeState = { key, params };
  $('notice').textContent = tr(key, params);
};
const rawSourceBanner = $('source-banner').textContent;
const sourceMode = rawSourceBanner.startsWith('Synthetic demo') ? 'syntheticBanner' : 'publicBanner';
const statuses = ['new', 'review', 'deferred', 'done'];

function loggedOut() {
  token = null;
  events = [];
  services = [];
  selected = null;
  calendarWeeks = [];
  calendarChanges = [];
  selectedWeek = null;
  $('calendar-file').value = '';
  $('calendar-days').replaceChildren();
  $('calendar-changes').replaceChildren();
  $('calendar-upcoming').replaceChildren();
  $('calendar-snapshot-status').textContent = '';
  $('items').replaceChildren();
  $('details').replaceChildren();
  $('workspace').hidden = true;
  $('login-panel').hidden = false;
  $('password').value = '';
}

async function api(path, body) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST', headers,
    credentials: 'omit', cache: 'no-store', redirect: 'error',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    if (response.status === 401) loggedOut();
    throw new Error(tr('requestFailed'));
  }
  return response.json();
}

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}
function options(id, values, all) {
  const select = $(id);
  select.replaceChildren();
  const first = element('option', all);
  first.value = '';
  select.append(first);
  for (const value of values) {
    const option = element('option', value);
    option.value = value;
    select.append(option);
  }
}
function accounts() {
  options('account', services.filter(s => !$('service').value || s.service === $('service').value).map(s => s.account), tr('allAccounts'));
}
const identity = event => JSON.stringify([event.service_id, event.account_id, event.external_id]);
function details() {
  const target = $('details');
  target.replaceChildren(element('h2', tr('itemDetails')));
  const event = events.find(e => identity(e) === selected);
  if (!event) {
    target.append(element('p', tr('selectPrompt')));
    return;
  }
  target.append(element('h3', event.title), element('p', `${event.service_id} / ${event.account_id} / ${event.external_id}`), element('p', formatDate(event.timestamp, locale)), element('pre', event.body));
  const label = element('label', tr('detailStatus'));
  label.htmlFor = 'item-status';
  const select = element('select', '');
  select.id = 'item-status';
  for (const status of statuses) {
    const option = element('option', tr('status.' + status));
    option.value = status;
    select.append(option);
  }
  select.value = event.status;
  const save = element('button', tr('save'));
  save.type = 'button';
  save.addEventListener('click', () => run(save, async () => {
    await api('/api/status', {service: event.service_id, account: event.account_id, external_id: event.external_id, status: select.value});
    await refresh();
    notice('saved');
  }));
  target.append(label, select, save);
}
const calendarRecords = () => events.filter(e => e.service_id === 'local-calendar' && e.account_id === 'weekly-ics');
function calendarOverviewRender() {
  const snapshot = weekSnapshotState(calendarWeeks);
  const stateText = {
    missing: 'calendarSnapshotMissing', stale: 'calendarSnapshotStale',
    recent: 'calendarSnapshotRecent', unknown: 'calendarSnapshotUnknown',
  }[snapshot.state];
  $('calendar-snapshot-status').textContent = tr(stateText, {week: snapshot.week});
  const upcoming = $('calendar-upcoming');
  upcoming.replaceChildren();
  const next = upcomingCalendarLessons(calendarRecords());
  if (!next.length) {
    upcoming.append(element('p', tr('calendarUpcomingNone')));
    return;
  }
  for (const lesson of next) {
    const row = element('div', '');
    row.className = 'calendar-upcoming-item';
    row.append(element('small', [lesson.attributes.date_local,
      lesson.attributes.time_local].filter(Boolean).join(' · ')));
    row.append(element('strong', lesson.title));
    if (lesson.attributes.location) row.append(element('small', lesson.attributes.location));
    upcoming.append(row);
  }
}
function calendarChangeSummary(lesson) {
  if (!lesson) return '';
  return [lesson.date, lesson.time, lesson.title, lesson.location].filter(Boolean).join(' · ');
}
function calendarChangeRender() {
  const container = $('calendar-changes');
  container.replaceChildren();
  const changes = calendarChanges.filter(c => c.week === selectedWeek).slice(0, 20);
  if (!changes.length) {
    container.append(element('p', tr('calendarChangesNone')));
    return;
  }
  for (const change of changes) {
    const panel = element('div', '');
    panel.className = 'calendar-change';
    panel.append(element('strong', tr('calendar.change.' + change.kind)));
    const previous = calendarChangeSummary(change.before);
    const next = calendarChangeSummary(change.after);
    if (previous) panel.append(element('p', previous));
    if (previous && next) panel.append(element('small', '↓'));
    if (next) panel.append(element('p', next));
    if (previous && next && previous === next && change.before.body !== change.after.body) {
      panel.append(element('small', tr('calendarDescriptionChanged')));
    }
    panel.append(element('small', change.recorded_at + ' UTC'));
    container.append(panel);
  }
}
function calendarRender() {
  const weeks = $('calendar-week');
  weeks.replaceChildren();
  const current = calendarWeeks.find(w => w.week === selectedWeek);
  if (!current) selectedWeek = preferredCalendarWeek(calendarWeeks);
  for (const week of calendarWeeks) {
    const option = element('option', week.week);
    option.value = week.week;
    weeks.append(option);
  }
  weeks.value = selectedWeek || '';
  weeks.disabled = !calendarWeeks.length;
  calendarOverviewRender();
  const place = $('calendar-days');
  place.replaceChildren();
  const entry = calendarWeeks.find(w => w.week === selectedWeek);
  if (!entry) {
    $('calendar-updated').textContent = tr('calendarNone');
    calendarChangeRender();
    return;
  }
  const imported = entry.imported_at ? entry.imported_at + ' UTC' : '';
  $('calendar-updated').textContent = tr('calendarUpdated', {date: imported.replace(/ UTC$/, '')});
  const lessons = calendarRecords().filter(e => e.attributes.week_start === selectedWeek);
  const date = new Date(selectedWeek + 'T12:00:00Z');
  for (let index = 0; index < 7; index++) {
    const day = new Date(date);
    day.setUTCDate(date.getUTCDate() + index);
    const iso = day.toISOString().slice(0, 10);
    const label = new Intl.DateTimeFormat(locale === 'ru' ? 'ru-RU' : 'en-US',
      {weekday: 'long', day: 'numeric', month: 'short', timeZone: 'UTC'}).format(day);
    const box = element('section', '');
    box.className = 'calendar-day';
    box.append(element('h3', label));
    const today = lessons.filter(e => e.attributes.date_local === iso)
      .sort((a,b) => a.attributes.time_local.localeCompare(b.attributes.time_local));
    if (!today.length) box.append(element('small', tr('calendarNoClasses')));
    for (const lesson of today) {
      const item = element('div', '');
      item.className = 'calendar-lesson';
      item.append(element('small', lesson.attributes.time_local), element('strong', lesson.title));
      if (lesson.attributes.location) item.append(element('small', lesson.attributes.location));
      box.append(item);
    }
    place.append(box);
  }
  calendarChangeRender();
}
async function calendarRefresh() {
  const [weeks, changes] = await Promise.all([
    api('/api/calendar/weeks'), api('/api/calendar/changes')]);
  calendarWeeks = weeks;
  calendarChanges = changes;
  calendarRender();
}

function render() {
  const query = $('search').value.trim().toLowerCase();
  const visible = events.filter(e =>
    (!$('service').value || e.service_id === $('service').value) &&
    (!$('account').value || e.account_id === $('account').value) &&
    (!$('status-filter').value || e.status === $('status-filter').value) &&
    [e.title, e.body, e.service_id, e.account_id, e.external_id].join(' ').toLowerCase().includes(query));
  $('count').textContent = tr('itemCount', {count: visible.length});
  $('items').replaceChildren();
  for (const event of visible) {
    const button = element('button', event.title);
    button.type = 'button';
    button.className = 'item';
    button.append(element('small', `${event.service_id} / ${event.account_id} / ${event.external_id} · ${tr('status.' + event.status)}`));
    button.addEventListener('click', () => { selected = identity(event); details(); });
    $('items').append(button);
  }
  if (!visible.length) $('items').append(element('p', tr('empty')));
  details();
  calendarRender();
}
async function refresh() {
  events = await api('/api/inbox');
  render();
}
async function run(button, action) {
  button.disabled = true;
  try { await action(); }
  catch { notice('requestFailed'); }
  finally { button.disabled = false; }
}
$('login-form').addEventListener('submit', event => {
  event.preventDefault();
  token = null;
  const input = $('password');
  const secret = input.value;
  input.value = '';
  run(event.submitter, async () => {
    token = (await api('/api/login', {password: secret})).token;
    await api('/api/session');
    services = await api('/api/services');
    options('service', [...new Set(services.map(s => s.service))], tr('allServices'));
    accounts();
    await refresh();
    await calendarRefresh();
    $('login-panel').hidden = true;
    $('workspace').hidden = false;
    notice('signedIn');
  });
});
$('service').addEventListener('change', () => { accounts(); render(); });
for (const id of ['account', 'status-filter', 'search']) $(id).addEventListener('input', render);
$('collect').addEventListener('click', () => run($('collect'), async () => {
  for (const binding of services.filter(s => s.capabilities.includes('read') && (!$('service').value || s.service === $('service').value) && (!$('account').value || s.account === $('account').value))) {
    await api('/api/collect', {service: binding.service, account: binding.account});
  }
  await refresh();
  notice('collected');
}));
$('calendar-refresh').addEventListener('click', () => run($('calendar-refresh'), async () => {
  await refresh();
  await calendarRefresh();
  notice('calendarRefreshed');
}));
$('calendar-week').addEventListener('change', () => {
  selectedWeek = $('calendar-week').value;
  calendarRender();
});
$('calendar-import').addEventListener('click', () => {
  const file = $('calendar-file').files?.[0];
  if (!file || !file.name.toLowerCase().endsWith('.ics') || !file.size || file.size > 96 * 1024) {
    notice('calendarBadFile');
    return;
  }
  run($('calendar-import'), async () => {
    const ical = await file.text();
    const result = await api('/api/calendar/import', {ical});
    $('calendar-file').value = '';
    selectedWeek = result.week;
    await refresh();
    await calendarRefresh();
    $('service').value = 'local-calendar';
    accounts();
    render();
    notice('calendarSaved', result);
  });
});
$('logout').addEventListener('click', () => run($('logout'), async () => {
  await api('/api/logout', {});
  loggedOut();
  notice('loggedOut');
}));


function setLocale(next) {
  if (!LOCALES.includes(next)) return;
  locale = next;
  document.documentElement.lang = locale;
  document.title = tr('pageTitle');
  for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = tr(node.dataset.i18n);
  for (const node of document.querySelectorAll('[data-i18n-aria]')) node.setAttribute('aria-label', tr(node.dataset.i18nAria));
  for (const node of document.querySelectorAll('[data-i18n-placeholder]')) node.placeholder = tr(node.dataset.i18nPlaceholder);
  $('source-banner').textContent = tr(sourceMode);
  for (const code of LOCALES) $('locale-' + code).setAttribute('aria-pressed', String(code === locale));
  if (!$('workspace').hidden) {
    const allService = $('service').querySelector('option[value=""]');
    const allAccount = $('account').querySelector('option[value=""]');
    if (allService) allService.textContent = tr('allServices');
    if (allAccount) allAccount.textContent = tr('allAccounts');
    render();
  }
  if (!$('workspace').hidden) calendarRender();
  if (noticeState) $('notice').textContent = tr(noticeState.key, noticeState.params);
}
for (const code of LOCALES) $('locale-' + code).addEventListener('click', () => setLocale(code));
setLocale(DEFAULT_LOCALE);
