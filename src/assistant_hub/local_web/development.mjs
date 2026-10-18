// Inert owner reports only. Never infer agent liveness or successful execution.
export function renderDevelopment(target, snapshot, requestControl, documentRef = document) {
  const node = (tag, text) => {
    const result = documentRef.createElement(tag);
    result.textContent = text;
    return result;
  };
  target.replaceChildren();
  target.append(node('p', 'Source: owner-submitted reports. Executor not connected. PR/CI verification unknown.'));
  target.append(node('p', Object.entries(snapshot.projects).map(([name, state]) => `${name}: ${state}`).join(' · ')));
  if (!snapshot.tasks.length) target.append(node('p', 'No task reports received. No agent activity is known.'));
  for (const task of snapshot.tasks) {
    const card = node('article', '');
    card.append(node('h3', `${task.project} #${task.issue} · ${task.task_id}`));
    card.append(node('p', `Agent ${task.executor_id} reported ${task.status} · ${task.freshness}`));
    card.append(node('p', `Last received: ${new Date(task.received_at * 1000).toISOString()}`));
    card.append(node('p', `Branch: ${task.branch} · Commit: ${task.head_sha} · Worktree: ${task.worktree}`));
    card.append(node('p', `Reported PR: ${task.pr} · PR verification: ${task.pr_verification} · CI: ${task.ci}`));
    for (const action of ['pause', 'resume']) {
      const button = node('button', `Request ${action}`);
      button.type = 'button';
      button.disabled = snapshot.projects[task.project] !== 'active' || ['completed', 'failed'].includes(task.status);
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { await requestControl(task.task_id, action); }
        finally { button.disabled = snapshot.projects[task.project] !== 'active' || ['completed', 'failed'].includes(task.status); }
      });
      card.append(button);
    }
    target.append(card);
  }
  target.append(node('h3', 'Structured event log (latest 200)'));
  for (const event of snapshot.events) {
    const data = event.data;
    const detail = event.kind === 'report' ? `reported ${data.status} · sequence ${data.sequence}` : `requested ${data.action} · pending, not delivered`;
    target.append(node('p', `${new Date(event.received_at * 1000).toISOString()} · ${data.task_id} · ${detail}`));
  }
}

// Retain an idempotency key across uncertain network delivery. Never dispatch commands.
export function createControlRequestSender(send, nextId = () => globalThis.crypto.randomUUID()) {
  if (typeof send !== 'function' || typeof nextId !== 'function') throw new TypeError('callbacks required');
  const pending = new Map();
  return {
    async request(taskId, action) {
      const key = JSON.stringify([taskId, action]);
      let messageId = pending.get(key);
      if (!messageId) {
        messageId = nextId();
        pending.set(key, messageId);
      }
      // A failed request may have committed server-side. Preserve its ID for retry.
      const result = await send({message_id: messageId, task_id: taskId, action});
      if (pending.get(key) === messageId) pending.delete(key);
      return result;
    },
    clear() { pending.clear(); }, // Called on logout; never carry IDs to a new session.
  };
}
