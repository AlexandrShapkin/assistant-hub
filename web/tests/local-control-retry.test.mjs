import test from 'node:test';
import assert from 'node:assert/strict';
import {createControlRequestSender} from '../../src/assistant_hub/local_web/development.mjs';

test('lost response after a committed request reuses the exact message ID', async () => {
  const calls = [];
  let id = 0;
  let loseFirstResponse = true;
  const sender = createControlRequestSender(async payload => {
    calls.push({...payload});
    if (loseFirstResponse) {
      loseFirstResponse = false;
      throw new Error('response lost after commit');
    }
    return {delivery: 'pending'};
  }, () => `uuid-${++id}`);
  await assert.rejects(sender.request('task-1', 'pause'), /response lost/);
  assert.deepEqual(await sender.request('task-1', 'pause'), {delivery: 'pending'});
  assert.deepEqual(calls[0], calls[1]);
  await sender.request('task-1', 'pause');
  assert.notEqual(calls[2].message_id, calls[1].message_id);
});

test('task and action identities are independent while retries remain pending', async () => {
  const calls = [];
  let id = 0;
  const sender = createControlRequestSender(async payload => {
    calls.push({...payload});
    throw new Error('network timeout');
  }, () => `uuid-${++id}`);
  for (const [taskId, action] of [['a', 'pause'], ['a', 'resume'], ['b', 'pause'], ['a', 'pause']]) {
    await assert.rejects(sender.request(taskId, action), /network timeout/);
  }
  assert.equal(calls[0].message_id, calls[3].message_id);
  assert.notEqual(calls[0].message_id, calls[1].message_id);
  assert.notEqual(calls[0].message_id, calls[2].message_id);
});

test('logout clears uncertain request IDs', async () => {
  const calls = [];
  let id = 0;
  const sender = createControlRequestSender(async payload => {
    calls.push({...payload});
    throw new Error('network timeout');
  }, () => `uuid-${++id}`);
  await assert.rejects(sender.request('a', 'pause'));
  sender.clear();
  await assert.rejects(sender.request('a', 'pause'));
  assert.notEqual(calls[0].message_id, calls[1].message_id);
});

test('late completion from old session cannot clear new session request', async () => {
  let resolveOld;
  let n = 0;
  const calls = [];
  const sender = createControlRequestSender(payload => {
    calls.push({...payload});
    if (calls.length === 1) return new Promise(resolve => { resolveOld = resolve; });
    return Promise.reject(new Error('network timeout'));
  }, () => `uuid-${++n}`);
  const oldRequest = sender.request('task-1', 'pause');
  sender.clear();
  await assert.rejects(sender.request('task-1', 'pause'), /network timeout/);
  resolveOld({delivery: 'pending'});
  await oldRequest;
  await assert.rejects(sender.request('task-1', 'pause'), /network timeout/);
  assert.equal(calls[1].message_id, calls[2].message_id);
  assert.notEqual(calls[0].message_id, calls[1].message_id);
});
