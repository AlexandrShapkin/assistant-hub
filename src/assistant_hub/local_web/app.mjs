// Session proof stays in this module's memory. Refresh deliberately logs out.
let token = null;
let events = [];
let services = [];
let selected = null;
const $ = id => document.getElementById(id);
const notice = message => { $('notice').textContent = message; };
const statuses = ['new', 'review', 'deferred', 'done'];

function loggedOut() {
  token = null;
  events = [];
  services = [];
  selected = null;
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
    throw new Error('Request denied. Check login, selection and localhost URL.');
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
  options('account', services.filter(s => !$('service').value || s.service === $('service').value).map(s => s.account), 'All accounts');
}
const identity = event => JSON.stringify([event.service_id, event.account_id, event.external_id]);
function details() {
  const target = $('details');
  target.replaceChildren(element('h2', 'Item details'));
  const event = events.find(e => identity(e) === selected);
  if (!event) {
    target.append(element('p', 'Select an item to review its workflow status.'));
    return;
  }
  target.append(element('h3', event.title), element('p', `${event.service_id} / ${event.account_id} / ${event.external_id}`), element('p', event.timestamp), element('pre', event.body));
  const label = element('label', 'Workflow status (UI only)');
  label.htmlFor = 'item-status';
  const select = element('select', '');
  select.id = 'item-status';
  for (const status of statuses) {
    const option = element('option', status);
    option.value = status;
    select.append(option);
  }
  select.value = event.status;
  const save = element('button', 'Save status');
  save.type = 'button';
  save.addEventListener('click', () => run(save, async () => {
    await api('/api/status', {service: event.service_id, account: event.account_id, external_id: event.external_id, status: select.value});
    await refresh();
    notice('Workflow status saved locally. No action dispatched.');
  }));
  target.append(label, select, save);
}
function render() {
  const query = $('search').value.trim().toLowerCase();
  const visible = events.filter(e =>
    (!$('service').value || e.service_id === $('service').value) &&
    (!$('account').value || e.account_id === $('account').value) &&
    (!$('status-filter').value || e.status === $('status-filter').value) &&
    [e.title, e.body, e.service_id, e.account_id, e.external_id].join(' ').toLowerCase().includes(query));
  $('count').textContent = `${visible.length} items`;
  $('items').replaceChildren();
  for (const event of visible) {
    const button = element('button', event.title);
    button.type = 'button';
    button.className = 'item';
    button.append(element('small', `${event.service_id} / ${event.account_id} / ${event.external_id} · ${event.status}`));
    button.addEventListener('click', () => { selected = identity(event); details(); });
    $('items').append(button);
  }
  if (!visible.length) $('items').append(element('p', 'No matching items. Collect events to populate the inbox.'));
  details();
}
async function refresh() {
  events = await api('/api/inbox');
  render();
}
async function run(button, action) {
  button.disabled = true;
  try { await action(); }
  catch { notice('Request failed. Use the exact localhost URL and sign in again if needed.'); }
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
    options('service', [...new Set(services.map(s => s.service))], 'All services');
    accounts();
    await refresh();
    $('login-panel').hidden = true;
    $('workspace').hidden = false;
    notice('Signed in. Collection is read-only and manual.');
  });
});
$('service').addEventListener('change', () => { accounts(); render(); });
for (const id of ['account', 'status-filter', 'search']) $(id).addEventListener('input', render);
$('collect').addEventListener('click', () => run($('collect'), async () => {
  for (const binding of services.filter(s => (!$('service').value || s.service === $('service').value) && (!$('account').value || s.account === $('account').value))) {
    await api('/api/collect', {service: binding.service, account: binding.account});
  }
  await refresh();
  notice('Page collected. Repeated collection deduplicates; public snapshots can miss updates.');
}));
$('logout').addEventListener('click', () => run($('logout'), async () => {
  await api('/api/logout', {});
  loggedOut();
  notice('Logged out. Session revoked.');
}));
