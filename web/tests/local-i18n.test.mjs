import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { DEFAULT_LOCALE, LOCALES, t, formatDate } from '../../src/assistant_hub/local_web/i18n.mjs';

test('private local UI has Russian default, English switch and safe fallback', () => {
  assert.equal(DEFAULT_LOCALE, 'ru');
  assert.deepEqual(LOCALES, ['ru', 'en']);
  assert.equal(t('ru', 'signIn'), 'Войти');
  assert.equal(t('en', 'signIn'), 'Sign in');
  assert.equal(t('unexpected', 'signIn'), 'Sign in');
  assert.equal(t('ru', 'not-defined'), 'not-defined');
  assert.equal(t('ru', 'itemCount', {count: 4}), 'Событий: 4');
  assert.match(formatDate('2026-10-17T12:00:00Z', 'ru'), /UTC$/);
  assert.equal(formatDate('invalid-date', 'ru'), 'invalid-date');
});

test('translated local UI covers the form, labels, status selectors and accessible names', async () => {
  const html = await readFile(new URL('../../src/assistant_hub/local_web/index.html', import.meta.url), 'utf8');
  assert.match(html, /<html lang="ru">/);
  assert.match(html, /id="locale-ru"[^>]*aria-pressed="true"/);
  assert.match(html, /id="locale-en"[^>]*aria-pressed="false"/);
  for (const [, key] of html.matchAll(/data-i18n(?:-aria|-placeholder)?="([^"]+)"/g)) {
    for (const locale of LOCALES) {
      assert.ok(t(locale, key) !== key, `Missing ${locale} translation: ${key}`);
      assert.ok(t(locale, key).trim());
    }
  }
  for (const key of ['requestFailed', 'signedIn', 'collected', 'loggedOut',
    'saved', 'itemDetails', 'publicBanner', 'syntheticBanner']) {
    for (const locale of LOCALES) assert.notEqual(t(locale, key), key);
  }
});

test('locale switch only touches presentation and does not modify authentication flow', async () => {
  const source = await readFile(new URL('../../src/assistant_hub/local_web/app.mjs', import.meta.url), 'utf8');
  assert.match(source, /let token = null/);
  assert.match(source, /credentials: 'omit'/);
  assert.match(source, /redirect: 'error'/);
  assert.match(source, /function setLocale/);
  assert.match(source, /setLocale\(DEFAULT_LOCALE\)/);
  assert.match(source, /document\.documentElement\.lang = locale/);
  assert.match(source, /if \(noticeState\)/);
  assert.doesNotMatch(source, /localStorage|sessionStorage|document\.cookie|location\.reload|innerHTML|outerHTML/);
});
