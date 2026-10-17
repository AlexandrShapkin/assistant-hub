import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { demoEvents } from '../demo-data.mjs';
import { STATUSES, initialFilters, eventKey, selectEvents, counters, navigation, updateEvent } from '../view-model.mjs';
const filter = patch => ({ ...initialFilters, ...patch });
test('fixtures have a complete generic schema and diverse synthetic sources', () => {
  assert.ok(demoEvents.length >= 10);
  assert.equal(new Set(demoEvents.map(event => event.source)).size, 4);
  assert.equal(new Set(demoEvents.map(eventKey)).size, demoEvents.length);
  for (const event of demoEvents) {
    for (const field of ['id', 'source', 'account', 'kind', 'title', 'summary', 'body', 'priority', 'timestamp', 'status']) assert.equal(typeof event[field], 'string');
    assert.ok(STATUSES.includes(event.status));
    assert.ok(Number.isFinite(Date.parse(event.timestamp)));
  }
});
test('same external id remains separate across accounts and sources', () => {
  const base = demoEvents[0];
  const events = [base, { ...base, account: 'Other fictional account' }, { ...base, source: 'custom-source' }];
  const updated = updateEvent(events, eventKey(events[1]), 'done');
  assert.equal(updated[1].status, 'done');
  assert.equal(updated[0], base); assert.equal(updated[2], events[2]);
  assert.equal(selectEvents(events, filter({ account: base.account, source: base.source })).length, 1);
  assert.equal(events[1].status, base.status);
});
test('search spans body, source, account and proposed action without parsing markup', () => {
  for (const query of ['  STORAGE  ', 'communication', 'Community', 'maintenance checklist']) assert.ok(selectEvents(demoEvents, filter({ query })).length > 0);
  const literal = { ...demoEvents[0], body: '<script>synthetic-marker</script>' };
  assert.equal(selectEvents([literal], filter({ query: '<script>' })).length, 1);
  assert.equal(selectEvents(demoEvents, filter({ query: 'nonexistent phrase' })).length, 0);
});
test('priority and status combine with account filters', () => {
  const result = selectEvents(demoEvents, filter({ priority: 'important', status: 'review', account: 'Studio · demo' }));
  assert.equal(result.length, 1); assert.equal(result[0].id, 'sample-1');
});
test('sorting is deterministic, latest versus important, without mutating inputs', () => {
  const events = [{ ...demoEvents[0], priority: 'normal' }, { ...demoEvents[1], priority: 'important' }];
  assert.equal(selectEvents(events, filter({ sort: 'latest' }))[0], events[0]);
  assert.equal(selectEvents(events, filter({ sort: 'important' }))[0], events[1]);
  assert.equal(events[0].priority, 'normal');
});
test('all status updates are immutable and counted', () => {
  for (const status of STATUSES) {
    const updated = updateEvent(demoEvents, eventKey(demoEvents[0]), status);
    assert.equal(updated[0].status, status);
    assert.equal(demoEvents[0].status, 'review');
    assert.equal(Object.values(counters(updated)).reduce((a, b) => a + b), demoEvents.length);
  }
  assert.equal(navigation(demoEvents, 'account').reduce((sum, entry) => sum + entry.count, 0), demoEvents.length);
  assert.throws(() => navigation(demoEvents, 'body'));
});
test('simulation requires a draft and review, and never changes event status', () => {
  const key = eventKey(demoEvents[0]);
  let events = updateEvent(demoEvents, key, 'draft');
  events = updateEvent(events, key, 'request-review');
  const approved = updateEvent(events, key, 'approve');
  const rejected = updateEvent(events, key, 'reject');
  assert.equal(approved[0].simulation, 'approved'); assert.equal(rejected[0].simulation, 'rejected');
  assert.equal(approved[0].status, 'review'); assert.equal(demoEvents[0].simulation, undefined);
  assert.throws(() => updateEvent(approved, key, 'approve'));
});
test('unknown keys, dispatch operations, missing proposals and skipped review deny', () => {
  const key = eventKey(demoEvents[0]);
  for (const operation of ['send', 'dispatch', 'delete', 'approve', 'reject', 'request-review']) assert.throws(() => updateEvent(demoEvents, key, operation));
  assert.throws(() => updateEvent(demoEvents, 'missing', 'done'));
  assert.throws(() => updateEvent(demoEvents, eventKey(demoEvents[3]), 'draft'));
});
test('view model works with unknown services, accounts, and event kinds', () => {
  const event = { ...demoEvents[0], source: 'future-adapter', account: 'Fictional delta', kind: 'custom-kind' };
  assert.equal(selectEvents([event], filter({ source: 'future-adapter', query: 'custom-kind' })).length, 1);
  assert.equal(updateEvent([event], eventKey(event), 'draft')[0].simulation, 'draft');
});
test('browser modules have no network, persistence or HTML injection primitives', async () => {
  const files = (await readdir(new URL('../', import.meta.url))).filter(name => name.endsWith('.mjs'));
  for (const name of files) {
    const source = await readFile(new URL(`../${name}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /\b(fetch|XMLHttpRequest|WebSocket|EventSource|localStorage|sessionStorage|indexedDB|serviceWorker|sendBeacon|innerHTML|outerHTML|insertAdjacentHTML|eval)\b/);
    assert.doesNotMatch(source, /https?:\/\//);
    for (const match of source.matchAll(/\bimport\s.*?from\s+['"]([^'"]+)['"]/g)) assert.ok(match[1].startsWith('./'));
  }
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /connect-src 'none'/); assert.match(html, /worker-src 'none'/);
  assert.doesNotMatch(html, /https?:\/\//);
  const css = await readFile(new URL('../styles.css', import.meta.url), 'utf8');
  assert.doesNotMatch(css, /@import|url\s*\(/i);
});
