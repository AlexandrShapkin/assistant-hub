import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { demoEvents } from '../demo-data.mjs';
import { DEFAULT_LOCALE, LOCALES, t, formatTime, accountLabel, presentEvent } from '../i18n.mjs';
import { eventKey, updateEvent, selectEvents, initialFilters } from '../view-model.mjs';

test('Russian is the default and English is available without storage', () => {
  assert.equal(DEFAULT_LOCALE, 'ru');
  assert.deepEqual(LOCALES, ['ru', 'en']);
  assert.equal(t('ru', 'inbox'), 'Входящие');
  assert.equal(t('en', 'inbox'), 'Inbox');
  assert.equal(t('other', 'inbox'), 'Inbox');
  assert.equal(t('ru', 'missing-key'), 'missing-key');
  assert.equal(t('ru', 'results', {visible: 2, total: 12}), '2 из 12 учебных событий');
  assert.match(formatTime(demoEvents[0].timestamp, 'ru'), /UTC$/);
  assert.notEqual(formatTime(demoEvents[0].timestamp, 'ru'), formatTime(demoEvents[0].timestamp, 'en'));
});

test('all static text, accessibility labels and placeholders have RU and EN values', async () => {
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /<html lang="ru">/);
  assert.match(html, /id="locale-ru"[^>]*aria-pressed="true"/);
  assert.match(html, /id="locale-en"[^>]*aria-pressed="false"/);
  for (const [, key] of html.matchAll(/data-i18n(?:-aria|-placeholder)?="([^"]+)"/g)) {
    for (const locale of LOCALES) {
      assert.notEqual(t(locale, key), key, `Missing ${locale} translation for ${key}`);
      assert.ok(t(locale, key).trim());
    }
  }
  for (const key of ['language', 'status.done', 'status.review', 'source.device',
    'simulationNotice', 'simulationExplainer', 'simulationDenied', 'emptyText',
    'detailFoot', 'markDone', 'defer', 'simulationButtonApprove', 'simulationButtonReject']) {
    assert.ok(t('ru', key) !== key && t('en', key) !== key, key);
  }
});

test('Russian synthetic fixtures preserve event identity, status and immutable schema', () => {
  const localized = demoEvents.map(event => presentEvent(event, 'ru'));
  assert.equal(localized.length, demoEvents.length);
  for (let index = 0; index < demoEvents.length; index++) {
    const original = demoEvents[index];
    const displayed = localized[index];
    assert.equal(eventKey(displayed), eventKey(original));
    for (const key of ['id', 'source', 'account', 'priority', 'status', 'kind', 'timestamp']) {
      assert.equal(displayed[key], original[key]);
    }
    assert.notEqual(displayed.title, original.title);
    assert.notEqual(displayed.summary, original.summary);
    assert.notEqual(displayed.body, original.body);
    if (original.proposedAction) assert.notEqual(displayed.proposedAction, original.proposedAction);
    assert.equal(presentEvent(original, 'en'), original);
    assert.ok(accountLabel(original.account, 'ru').includes('пример'));
  }
  assert.equal(demoEvents[0].title, 'A little clarity for the next milestone');
  assert.equal(selectEvents(localized, {...initialFilters, query: 'уточнения'}).length, 1);
  const changed = updateEvent(demoEvents, eventKey(localized[0]), 'done');
  assert.equal(changed[0].status, 'done');
  assert.equal(demoEvents[0].status, 'review');
});

test('unknown provider events, kind and accounts fall back to original strings', () => {
  const external = { ...demoEvents[0], id: 'external-event', source: 'future-provider', account: 'Other account', title: 'Do not translate' };
  assert.equal(presentEvent(external, 'ru'), external);
  assert.equal(accountLabel(external.account, 'ru'), external.account);
  assert.equal(t('ru', 'source.future-provider'), 'source.future-provider');
});

test('UI locale switching is client-only and does not change other state', async () => {
  const source = await readFile(new URL('../app.mjs', import.meta.url), 'utf8');
  assert.match(source, /function setLocale\(/);
  assert.match(source, /document\.documentElement\.lang = locale/);
  assert.match(source, /render\(\);\s*}\s*for \(const code of LOCALES\)/);
  assert.match(source, /setLocale\(DEFAULT_LOCALE\)/);
  assert.match(source, /presentEvent\(event, locale\)/);
  assert.doesNotMatch(source, /location\.reload\(|document\.cookie|localStorage|sessionStorage/);
});
