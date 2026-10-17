import { demoEvents } from './demo-data.mjs';
import { STATUSES, initialFilters, eventKey, selectEvents, counters, navigation, updateEvent } from './view-model.mjs';
let events = demoEvents.map(event => ({ ...event }));
let filters = { ...initialFilters };
let selected = eventKey(events[0]);
const $ = id => document.getElementById(id);
const names = { communication: 'Communication', git: 'Git activity', website: 'Website updates', device: 'Device health', new: 'New', review: 'Review', deferred: 'Deferred', done: 'Done' };
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, handler, className = '') {
  const node = element('button', text, className);
  node.type = 'button'; node.addEventListener('click', handler); return node;
}
function nav(id, entries, field) {
  $(id).replaceChildren(...entries.map(({ value, count, label }) => {
    const active = filters[field] === value;
    const node = button('', () => {
      filters[field] = value; render();
      $(id).querySelector('[aria-pressed="true"]')?.focus();
    }, `nav-button ${active ? 'active' : ''}`);
    node.setAttribute('aria-pressed', String(active));
    node.append(element('span', label || names[value] || value), element('span', String(count), 'nav-count'));
    return node;
  }));
}
function simulate(operation) {
  const focusedOperation = document.activeElement?.dataset.operation;
  try {
    events = updateEvent(events, selected, operation);
    render();
    $('announcement').textContent = `Simulation only: ${operation}. Nothing was sent or executed.`;
    const replacement = [...$('inspector').querySelectorAll('button')].find(node => node.dataset.operation === focusedOperation && !node.disabled);
    (replacement || $('detail-title'))?.focus();
  } catch (error) { $('announcement').textContent = error.message; }
}
function renderDetail(event) {
  const panel = $('inspector'); panel.replaceChildren();
  if (!event) { panel.append(element('h2', 'Nothing selected'), element('p', 'Choose an item from the current results.')); return; }
  panel.append(element('p', 'ITEM DETAILS', 'eyebrow'));
  const badges = element('div', undefined, 'badges');
  badges.append(element('span', names[event.source] || event.source, 'badge'), element('span', event.account, 'badge'));
  panel.append(badges);
  const title = element('h2', event.title); title.id = 'detail-title'; title.tabIndex = -1; panel.append(title);
  const time = element('time', formatTime(event.timestamp)); time.dateTime = event.timestamp;
  panel.append(time, element('p', event.summary, 'detail-summary'), element('p', event.body, 'body-copy'));
  const metadata = element('dl', undefined, 'metadata');
  for (const [label, value] of [['Status', names[event.status]], ['Priority', event.priority], ['Kind', event.kind], ['Sample ID', event.id]]) metadata.append(element('dt', label), element('dd', value));
  panel.append(metadata, element('h3', 'Organize this item'));
  const actions = element('div', undefined, 'actions');
  for (const status of ['done', 'deferred', 'review', 'new']) {
    const node = button(({ done: 'Mark done', deferred: 'Defer', review: 'Mark for review', new: 'Reopen' })[status], () => simulate(status), 'secondary');
    node.disabled = event.status === status; node.dataset.operation = status; actions.append(node);
  }
  panel.append(actions);
  if (event.proposedAction) {
    const card = element('section', undefined, 'simulation');
    card.append(element('p', 'ACTION SIMULATION', 'eyebrow'), element('h3', event.proposedAction), element('p', 'Practice the review flow. This does not grant permission, send a message, or run an action.'));
    if (event.simulation) card.append(element('p', `Simulation state: ${event.simulation}`, 'simulation-state'), element('p', `Synthetic draft: ${event.proposedAction}. Gather context and prepare a short note for discussion.`, 'draft'));
    const controls = element('div', undefined, 'actions');
    const operations = !event.simulation || ['approved', 'rejected'].includes(event.simulation) ? [['draft', 'Simulate draft']] : event.simulation === 'draft' ? [['request-review', 'Request review · simulation']] : [['approve', 'Approve · simulation'], ['reject', 'Reject · simulation']];
    for (const [operation, label] of operations) { const node = button(label, () => simulate(operation), 'primary'); node.dataset.operation = operation; controls.append(node); }
    card.append(controls); panel.append(card);
  }
  panel.append(element('p', 'Synthetic content · In-memory changes only', 'muted detail-foot'));
}
function formatTime(timestamp) { return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }).format(new Date(timestamp)) + ' UTC'; }
function render() {
  const counts = counters(events);
  nav('statuses', [{ value: '', label: 'All activity', count: events.length }, ...STATUSES.map(value => ({ value, count: counts[value] }))], 'status');
  for (const [id, field, label] of [['sources', 'source', 'All services'], ['accounts', 'account', 'All accounts']]) nav(id, [{ value: '', label, count: events.length }, ...navigation(events, field)], field);
  const visible = selectEvents(events, filters);
  if (!visible.some(event => eventKey(event) === selected)) selected = visible[0] ? eventKey(visible[0]) : null;
  $('count').textContent = String(visible.length);
  $('results').textContent = `${visible.length} of ${events.length} synthetic items`;
  $('items').replaceChildren(...visible.map(event => {
    const active = eventKey(event) === selected;
    const node = button('', () => { selected = eventKey(event); render(); const replacement = [...$('items').children].find(item => item.getAttribute('aria-current') === 'true'); replacement?.focus(); }, `item ${active ? 'selected' : ''}`);
    node.setAttribute('aria-current', String(active)); node.setAttribute('aria-controls', 'inspector');
    const meta = element('span', undefined, 'item-meta');
    meta.append(element('span', names[event.source] || event.source), element('span', event.account));
    node.append(meta, element('span', event.title, 'item-title'), element('span', event.summary, 'item-summary'));
    const bottom = element('span', undefined, 'item-bottom');
    bottom.append(element('span', names[event.status]), element('span', formatTime(event.timestamp)));
    if (event.priority === 'important') bottom.prepend(element('span', 'Important', 'important'));
    node.append(bottom); return node;
  }));
  if (!visible.length) $('items').append(element('h3', 'A little quieter here.'), element('p', 'No matching items. Try another search or reset the filters.', 'muted'));
  renderDetail(visible.find(event => eventKey(event) === selected));
}
$('filters-toggle').addEventListener('click', () => {
  const expanded = document.querySelector('.sidebar').classList.toggle('expanded');
  $('filters-toggle').setAttribute('aria-expanded', String(expanded));
});
$('search').addEventListener('input', event => { filters.query = event.target.value; render(); });
for (const field of ['priority', 'sort']) $(field).addEventListener('change', event => { filters[field] = event.target.value; render(); });
$('reset').addEventListener('click', () => { filters = { ...initialFilters }; $('search').value = ''; $('priority').value = ''; $('sort').value = 'latest'; render(); });
render();
