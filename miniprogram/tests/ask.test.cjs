const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function page(api = {}) {
  let definition;
  const redirects = [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../pages/ask/ask.js'), 'utf8'), {
    Page: (value) => { definition = value; },
    require: (name) => name.endsWith('/api') ? api : { mdToNodes: (s) => [s] },
    wx: { redirectTo: (value) => redirects.push(value) },
    setTimeout,
  });
  return {
    ...definition, data: { ...definition.data }, redirects,
    setData(patch) { Object.assign(this.data, patch); },
  };
}
const pick = (name) => ({ currentTarget: { dataset: { name } } });

test('synthesis ambiguous pick calls synthesis probe and renders a tree, never ask', async () => {
  let calls = 0;
  const tree = { name: 'item', recipes: [] };
  const p = page({ operator: async (name) => { calls++; assert.equal(name, 'item'); return { ok: true, tree }; },
    ask: () => assert.fail('must not call paid ask API') });
  p.data.mode = 'syn';
  p.data.route = 'ambiguous';
  await p.onAmbiguousPick(pick('item'));
  assert.equal(calls, 1);
  assert.equal(p.data.synthTree, tree);
  assert.equal(p.data.query, 'item');
  assert.equal(p.data.loading, false);
  assert.equal(p.data.route, '');
});

test('ask ambiguous pick stays in ask mode', async () => {
  const p = page({ ask: async (name) => ({ ok: true, answer: name }),
    operator: () => assert.fail('must not probe synthesis') });
  await p.onAmbiguousPick(pick('item'));
  assert.equal(p.data.route, 'rag');
  assert.equal(p.data.result.answer, 'item');
});

test('empty ambiguous pick sends no request', () => {
  const p = page({});
  p.onAmbiguousPick(pick(''));
  assert.equal(p.data.loading, false);
});

test('new synthesis result clears old tree/cards that otherwise mask KB or device', async () => {
  for (const result of [
    { ok: true, no_recipe: true, kb: { name: 'item', full_text: 'text' } },
    { ok: true, tree: { kind: 'device', name: 'item', recipes: [] } },
    { ok: true, ambiguous: true, item: 'item', candidates: ['one'] },
  ]) {
    const p = page({ operator: async () => result });
    p.data.synthTree = { name: 'old' };
    p.data.error = 'old error';
    p.data.recipeCard = { title: 'old card' };
    await p._probeOperator('item');
    assert.equal(p.data.synthTree, null);
    assert.equal(p.data.error, '');
    assert.ok(['kb', 'device', 'ambiguous'].includes(p.data.route));
  }
});

test('synthesis probe failure uses fallback with the same renderer', async () => {
  const tree = { name: 'item' };
  const p = page({ operator: async () => { throw Error('offline'); },
    synthesis: async () => ({ ok: true, tree }) });
  await p._probeOperator('item');
  assert.equal(p.data.synthTree, tree);
});

test('stale response cannot overwrite a newer query or redirect', async () => {
  let resolve;
  const p = page({ operator: (name) => name === 'old' ? new Promise((r) => { resolve = r; })
    : Promise.resolve({ ok: true, tree: { name: 'new' } }) });
  const old = p._probeOperator('old');
  await p._probeOperator('new');
  resolve({ ok: true, no_recipe: true, kb: { operator_detail: {} } });
  await old;
  assert.equal(p.data.synthTree.name, 'new');
  assert.equal(p.redirects.length, 0);
});

test('unloaded page ignores late ask response', async () => {
  let resolve;
  const p = page({ ask: () => new Promise((r) => { resolve = r; }) });
  const pending = p.runAsk('item');
  p.onUnload();
  resolve({ ok: true, answer: 'late' });
  await pending;
  assert.equal(p.data.result, null);
});

test('feedback sends trace, query and observed answer once', async () => {
  let payload;
  const p = page({ feedback: async (...args) => { payload = args; } });
  p.data.query = 'item';
  p.data.result = { trace_id: 'a'.repeat(32), answer: 'answer', feedback_snapshot: 'answer' };
  await p.onFeedback({ currentTarget: { dataset: { vote: 'not_useful' } } });
  assert.deepEqual(payload, ['a'.repeat(32), 'item', 'not_useful', '', 'answer']);
  assert.equal(p.data.feedbackState, 'sent');
  await p.onFeedback({ currentTarget: { dataset: { vote: 'useful' } } });
});

test('failed feedback can be retried', async () => {
  let calls = 0;
  const p = page({ feedback: async () => {
    calls += 1;
    if (calls === 1) throw new Error('temporary');
  } });
  p.data.query = 'item';
  p.data.result = { trace_id: 'b'.repeat(32), feedback_snapshot: 'answer' };
  await p.onFeedback({ currentTarget: { dataset: { vote: 'not_useful' } } });
  assert.equal(p.data.feedbackState, 'error');
  await p.onFeedback({ currentTarget: { dataset: { vote: 'not_useful' } } });
  assert.equal(calls, 2);
  assert.equal(p.data.feedbackState, 'sent');
});
