export const STATUSES = Object.freeze(['new', 'review', 'deferred', 'done']);
export const OPERATIONS = Object.freeze(['draft', 'request-review', 'approve', 'reject']);
export const initialFilters = Object.freeze({ query: '', source: '', account: '', priority: '', status: '', sort: 'latest' });
export const eventKey = event => JSON.stringify([event.source, event.account, event.id]);
export function selectEvents(events, filters = initialFilters) {
  const query = (filters.query || '').trim().toLocaleLowerCase();
  return events.filter(event =>
    (!filters.source || event.source === filters.source) &&
    (!filters.account || event.account === filters.account) &&
    (!filters.priority || event.priority === filters.priority) &&
    (!filters.status || event.status === filters.status) &&
    (!query || [event.id, event.source, event.account, event.kind, event.title, event.summary, event.body, event.proposedAction || ''].join(' ').toLocaleLowerCase().includes(query))
  ).sort((a, b) => (filters.sort === 'important' ? Number(b.priority === 'important') - Number(a.priority === 'important') : 0) || b.timestamp.localeCompare(a.timestamp) || eventKey(a).localeCompare(eventKey(b)));
}
export function counters(events) {
  return Object.fromEntries(STATUSES.map(status => [status, events.filter(event => event.status === status).length]));
}
export function navigation(events, field) {
  if (!['source', 'account'].includes(field)) throw new Error('Invalid navigation field');
  return [...new Set(events.map(event => event[field]))].sort().map(value => ({ value, count: events.filter(event => event[field] === value).length }));
}
export function updateEvent(events, key, operation) {
  const target = events.find(event => eventKey(event) === key);
  if (!target) throw new Error('Unknown event');
  if (!STATUSES.includes(operation) && !OPERATIONS.includes(operation)) throw new Error('Invalid operation');
  if (OPERATIONS.includes(operation) && !target.proposedAction) throw new Error('No proposed action');
  if (operation === 'request-review' && target.simulation !== 'draft') throw new Error('Draft required');
  if (['approve', 'reject'].includes(operation) && target.simulation !== 'requested') throw new Error('Review request required');
  return events.map(event => {
    if (eventKey(event) !== key) return event;
    if (STATUSES.includes(operation)) return { ...event, status: operation };
    const simulation = { draft: 'draft', 'request-review': 'requested', approve: 'approved', reject: 'rejected' }[operation];
    return { ...event, simulation };
  });
}
