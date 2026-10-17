import { demoEvents } from './demo-data.mjs';
import { STATUSES, initialFilters, eventKey, selectEvents, counters, navigation, updateEvent } from './view-model.mjs';
import { DEFAULT_LOCALE, LOCALES, t, formatTime, accountLabel, presentEvent } from './i18n.mjs';

let events = demoEvents.map(event => ({ ...event }));
let filters = { ...initialFilters };
let selected = eventKey(events[0]);
let locale = DEFAULT_LOCALE;
const $ = id => document.getElementById(id);
const text = (key, params) => t(locale, key, params);

function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function button(label, handler, className = '') {
  const node = element('button', label, className);
  node.type = 'button';
  node.addEventListener('click', handler);
  return node;
}
function labelFor(value, field) {
  if (field === 'status') return text('status.' + value) === 'status.' + value ? value : text('status.' + value);
  if (field === 'source') return text('source.' + value) === 'source.' + value ? value : text('source.' + value);
  if (field === 'account') return accountLabel(value, locale);
  return value;
}
function nav(id, entries, field) {
  $(id).replaceChildren(...entries.map(({ value, count, label }) => {
    const active = filters[field] === value;
    const node = button('', () => {
      filters[field] = value;
      render();
      $(id).querySelector('[aria-pressed="true"]')?.focus();
    }, `nav-button ${active ? 'active' : ''}`);
    node.setAttribute('aria-pressed', String(active));
    node.append(element('span', label ?? labelFor(value, field)), element('span', String(count), 'nav-count'));
    return node;
  }));
}
function simulate(operation) {
  const focusedOperation = document.activeElement?.dataset.operation;
  try {
    events = updateEvent(events, selected, operation);
    render();
    $('announcement').textContent = text('simulationNotice', { operation: text('operation.' + operation) });
    const replacement = [...$('inspector').querySelectorAll('button')]
      .find(node => node.dataset.operation === focusedOperation && !node.disabled);
    (replacement || $('detail-title'))?.focus();
  } catch {
    $('announcement').textContent = text('simulationDenied');
  }
}
function renderDetail(event) {
  const panel = $('inspector');
  panel.replaceChildren();
  if (!event) {
    panel.append(element('h2', text('nothingSelected')), element('p', text('selectItem')));
    return;
  }
  panel.append(element('p', text('itemDetails'), 'eyebrow'));
  const badges = element('div', undefined, 'badges');
  badges.append(element('span', labelFor(event.source, 'source'), 'badge'),
    element('span', accountLabel(event.account, locale), 'badge'));
  panel.append(badges);
  const title = element('h2', event.title);
  title.id = 'detail-title';
  title.tabIndex = -1;
  panel.append(title);
  const time = element('time', formatTime(event.timestamp, locale));
  time.dateTime = event.timestamp;
  panel.append(time, element('p', event.summary, 'detail-summary'), element('p', event.body, 'body-copy'));
  const metadata = element('dl', undefined, 'metadata');
  for (const [label, value] of [
    [text('metadataStatus'), labelFor(event.status, 'status')],
    [text('metadataPriority'), text(event.priority)],
    [text('metadataKind'), text('kind.' + event.kind) === 'kind.' + event.kind ? event.kind : text('kind.' + event.kind)],
    [text('metadataId'), event.id],
  ]) metadata.append(element('dt', label), element('dd', value));
  panel.append(metadata, element('h3', text('organize')));
  const actions = element('div', undefined, 'actions');
  for (const [status, label] of [
    ['done', 'markDone'], ['deferred', 'defer'], ['review', 'markReview'], ['new', 'reopen'],
  ]) {
    const node = button(text(label), () => simulate(status), 'secondary');
    node.disabled = event.status === status;
    node.dataset.operation = status;
    actions.append(node);
  }
  panel.append(actions);
  if (event.proposedAction) {
    const card = element('section', undefined, 'simulation');
    card.append(element('p', text('simulationHeading'), 'eyebrow'), element('h3', event.proposedAction),
      element('p', text('simulationExplainer')));
    if (event.simulation) {
      card.append(
        element('p', text('simulationState', { state: text('simulation.' + event.simulation) }), 'simulation-state'),
        element('p', text('simulationDraft', { action: event.proposedAction }), 'draft'),
      );
    }
    const controls = element('div', undefined, 'actions');
    const operations = !event.simulation || ['approved', 'rejected'].includes(event.simulation)
      ? [['draft', 'simulationButtonDraft']]
      : event.simulation === 'draft'
        ? [['request-review', 'simulationButtonReview']]
        : [['approve', 'simulationButtonApprove'], ['reject', 'simulationButtonReject']];
    for (const [operation, label] of operations) {
      const node = button(text(label), () => simulate(operation), 'primary');
      node.dataset.operation = operation;
      controls.append(node);
    }
    card.append(controls);
    panel.append(card);
  }
  panel.append(element('p', text('detailFoot'), 'muted detail-foot'));
}
function render() {
  const counts = counters(events);
  nav('statuses', [{ value: '', label: text('allActivity'), count: events.length },
    ...STATUSES.map(value => ({ value, count: counts[value] }))], 'status');
  for (const [id, field, key] of [
    ['sources', 'source', 'allServices'], ['accounts', 'account', 'allAccounts'],
  ]) nav(id, [{ value: '', label: text(key), count: events.length }, ...navigation(events, field)], field);
  // Only the display fields of the synthetic fixtures change with locale.
  const visible = selectEvents(events.map(event => presentEvent(event, locale)), filters);
  if (!visible.some(event => eventKey(event) === selected)) selected = visible[0] ? eventKey(visible[0]) : null;
  $('count').textContent = String(visible.length);
  $('results').textContent = text('results', { visible: visible.length, total: events.length });
  $('items').replaceChildren(...visible.map(event => {
    const active = eventKey(event) === selected;
    const node = button('', () => {
      selected = eventKey(event);
      render();
      const replacement = [...$('items').children]
        .find(item => item.getAttribute('aria-current') === 'true');
      replacement?.focus();
    }, `item ${active ? 'selected' : ''}`);
    node.setAttribute('aria-current', String(active));
    node.setAttribute('aria-controls', 'inspector');
    const meta = element('span', undefined, 'item-meta');
    meta.append(element('span', labelFor(event.source, 'source')),
      element('span', accountLabel(event.account, locale)));
    node.append(meta, element('span', event.title, 'item-title'),
      element('span', event.summary, 'item-summary'));
    const bottom = element('span', undefined, 'item-bottom');
    bottom.append(element('span', labelFor(event.status, 'status')),
      element('span', formatTime(event.timestamp, locale)));
    if (event.priority === 'important') bottom.prepend(element('span', text('important'), 'important'));
    node.append(bottom);
    return node;
  }));
  if (!visible.length) $('items').append(element('h3', text('emptyTitle')), element('p', text('emptyText'), 'muted'));
  renderDetail(visible.find(event => eventKey(event) === selected));
}
function setLocale(next) {
  if (!LOCALES.includes(next)) return;
  locale = next;
  document.documentElement.lang = locale;
  document.title = text('pageTitle');
  for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = text(node.dataset.i18n);
  for (const node of document.querySelectorAll('[data-i18n-aria]')) node.setAttribute('aria-label', text(node.dataset.i18nAria));
  for (const node of document.querySelectorAll('[data-i18n-placeholder]')) node.placeholder = text(node.dataset.i18nPlaceholder);
  for (const code of LOCALES) $('locale-' + code).setAttribute('aria-pressed', String(code === locale));
  render();
}
for (const code of LOCALES) $('locale-' + code).addEventListener('click', () => setLocale(code));
$('filters-toggle').addEventListener('click', () => {
  const expanded = document.querySelector('.sidebar').classList.toggle('expanded');
  $('filters-toggle').setAttribute('aria-expanded', String(expanded));
});
$('search').addEventListener('input', event => { filters.query = event.target.value; render(); });
for (const field of ['priority', 'sort']) $(field).addEventListener('change', event => {
  filters[field] = event.target.value; render();
});
$('reset').addEventListener('click', () => {
  filters = { ...initialFilters };
  $('search').value = '';
  $('priority').value = '';
  $('sort').value = 'latest';
  render();
});
setLocale(DEFAULT_LOCALE);
