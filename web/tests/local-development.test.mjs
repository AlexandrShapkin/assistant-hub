import test from 'node:test';
import assert from 'node:assert/strict';
import { renderDevelopment } from '../../src/assistant_hub/local_web/development.mjs';

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.handlers = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  get text() { return [this.textContent, ...this.children.map(c => c.text)].join(' '); }
}
const documentRef = {createElement: tag => new Node(tag)};
const task = {task_id: 'test', project: 'assistant-hub', issue: '52', executor_id: 'agent',
  status: 'running', freshness: 'stale / unknown', received_at: 1000,
  branch: '<img src=x onerror=alert(1)>', head_sha: 'unknown', pr: 'unknown',
  worktree: 'unknown', pr_verification: 'unknown', ci: 'unknown'};
const snapshot = {projects: {'assistant-hub': 'active', rustcraft: 'candidate'}, tasks: [task],
  events: [{kind: 'control_request', received_at: 1000, data: {task_id: 'test', action: 'pause'}}]};

test('empty ledger explains lack of activity; reports stay inert and requests pending', () => {
  const target = new Node('div');
  renderDevelopment(target, {...snapshot, tasks: [], events: []}, () => {}, documentRef);
  assert.match(target.text, /No agent activity is known/);
  renderDevelopment(target, snapshot, () => {}, documentRef);
  assert.match(target.text, /stale \/ unknown/);
  assert.match(target.text, /CI: unknown/);
  assert.match(target.text, /pending, not delivered/);
  const card = target.children.find(n => n.tag === 'article');
  assert.ok(card.children.some(n => n.textContent.includes(task.branch)));
  assert.equal(card.children.some(n => n.tag === 'img'), false);
});

test('controls send bounded requests and candidate/terminal buttons are disabled', async () => {
  const target = new Node('div');
  const requests = [];
  renderDevelopment(target, snapshot, async (...args) => requests.push(args), documentRef);
  let buttons = target.children.find(n => n.tag === 'article').children.filter(n => n.tag === 'button');
  await buttons[0].handlers.click();
  assert.deepEqual(requests, [['test', 'pause']]);
  for (const changes of [{project: 'rustcraft'}, {status: 'completed'}]) {
    renderDevelopment(target, {...snapshot, tasks: [{...task, ...changes}]}, () => {}, documentRef);
    buttons = target.children.find(n => n.tag === 'article').children.filter(n => n.tag === 'button');
    assert.ok(buttons.every(b => b.disabled));
  }
});
