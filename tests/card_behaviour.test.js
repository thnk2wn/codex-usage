// Exercises the shipped card script in a minimal stub host.
// Run directly: node tests/card_behaviour.test.js
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

// CARD_HTML_PATH lets the suite be pointed at another revision of the card,
// e.g. to confirm a new case fails before its fix.
const CARD = process.env.CARD_HTML_PATH || path.join(__dirname, '..', 'assets', 'status-card.html');
const SCRIPT = /<script>([\s\S]*)<\/script>/.exec(fs.readFileSync(CARD, 'utf8'))[1];
const META_KEY = 'codexUsage/report';

function report(overrides) {
  return Object.assign({
    kind: 'usage_card',
    generatedAt: '2026-09-15T20:00:00+00:00',
    thread: { id: 'task-1', name: 'Test task' },
    context: { usedPercent: 50, inputTokens: 1, windowTokens: 2 },
    sessionUsage: { totalTokens: 1, cachedPercent: 0 },
    latestTurn: { outputTokens: 1, totalTokens: 1 },
    combinedTokens: 1,
    subagentCount: 0,
    subagentTokens: 0,
    limit: null,
    pace: null,
    topTasks: [],
    alerts: [],
    detailsLoaded: true,
    windowUsage: null,
    preferences: { autoCardEnabled: true, autoCardIntervalSeconds: 300 },
    liveRefresh: { enabled: false, intervalMs: 3000, untilEpochMs: 0 }
  }, overrides);
}

function makeElement() {
  const element = {
    events: {},
    innerHTML: '',
    open: false,
    dataset: {},
    disabled: false,
    value: '',
    textContent: '',
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener(type, handler) { this.events[type] = handler; },
    querySelector: () => makeElement(),
    querySelectorAll: () => [],
    getBoundingClientRect: () => ({ height: 10 }),
    scrollHeight: 10,
    closest: () => null
  };
  return element;
}

function boot(options) {
  const listeners = {};
  const sent = [];
  const heights = [];
  const root = makeElement();
  const details = makeElement();
  const tasks = makeElement();
  root.querySelector = selector => {
    if (selector === ':scope > details' || selector === 'details') return root.innerHTML.includes('<details') ? details : null;
    if (selector === '.tasks') return tasks;
    return makeElement();
  };
  const openai = (options && options.noOpenai)
    ? undefined
    : { toolOutput: undefined, notifyIntrinsicHeight(height) { heights.push(height); }, setWidgetState() {} };
  const body = { scrollHeight: 10, getBoundingClientRect: () => ({ height: 10 }) };

  const windowStub = {
    openai,
    addEventListener: (type, handler) => { (listeners[type] = listeners[type] || []).push(handler); },
    removeEventListener() {},
    requestAnimationFrame: fn => fn(),
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: id => clearTimeout(id),
    parent: { postMessage: message => sent.push(message) }
  };

  const context = {
    window: windowStub,
    document: {
      getElementById: () => root,
      body,
      visibilityState: 'visible',
      querySelector: () => makeElement(),
      querySelectorAll: () => [],
      addEventListener() {}
    },
    Intl,
    Date,
    Math,
    JSON,
    Number,
    String,
    Object,
    Array,
    Set,
    Map,
    Promise,
    console,
    setTimeout,
    clearTimeout
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(SCRIPT, context);

  const fire = (type, detail) => (listeners[type] || []).forEach(fn => fn({ detail, source: windowStub.parent, data: detail }));
  const reply = (id, result) => fire('message', { jsonrpc: '2.0', id, result });
  return { listeners, sent, root, details, tasks, body, heights, openai, fire, reply, windowStub };
}

function initialize(host) {
  // The card sends ui/initialize on boot; answer it so `initialized` flips true.
  const init = host.sent.find(m => m.method === 'ui/initialize');
  assert.ok(init, 'card should send ui/initialize');
  host.reply(init.id, {});
  return new Promise(resolve => setTimeout(resolve, 0));
}

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('renders from component-only metadata', async () => {
  const host = boot();
  host.openai.toolResponseMetadata = { [META_KEY]: report() };
  await initialize(host);
  host.fire('openai:set_globals', { globals: { toolResponseMetadata: { [META_KEY]: report() } } });
  assert.ok(host.root.innerHTML.includes('Test task'), 'card should render the report');
});

test('an unrelated globals update does not change the original snapshot', async () => {
  const host = boot();
  // The persistent global still holds the ORIGINAL show_usage_card snapshot.
  host.openai.toolResponseMetadata = {
    [META_KEY]: report({ detailsLoaded: false, thread: { id: 'task-1', name: 'STALE' } })
  };
  await initialize(host);

  // A host can redeliver metadata, but this card remains the first snapshot.
  host.fire('openai:set_globals', {
    globals: { toolResponseMetadata: { [META_KEY]: report({ thread: { id: 'task-1', name: 'FRESH' } }) } }
  });
  assert.ok(host.root.innerHTML.includes('STALE'), 'the original card should remain unchanged');

  // Now an update about something else entirely arrives.
  host.fire('openai:set_globals', { globals: { theme: 'dark' } });
  assert.ok(host.root.innerHTML.includes('STALE'), 'the original snapshot should survive');
  assert.ok(!host.root.innerHTML.includes('FRESH'), 'later metadata should not overwrite it');
});

test('reads a payload wrapped in a nested tool-result envelope', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: {
      toolResponseMetadata: {
        mcp_tool_result: { _meta: { [META_KEY]: report({ thread: { id: 'task-1', name: 'WRAPPED' } }) } }
      }
    }
  });
  assert.ok(host.root.innerHTML.includes('WRAPPED'), 'nested envelope payload should render');
});

test('reads a payload under the call_tool_result envelope', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: {
      call_tool_result: { _meta: { [META_KEY]: report({ thread: { id: 'task-1', name: 'ALTKEY' } }) } }
    }
  });
  assert.ok(host.root.innerHTML.includes('ALTKEY'), 'alternate envelope payload should render');
});

test('a wrapped payload does not fall through to the refresh fallback', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: {
      toolResponseMetadata: { mcp_tool_result: { _meta: { [META_KEY]: report() } } },
      toolOutput: { kind: 'usage_card_ref', threadId: 'task-1' }
    }
  });
  const calls = host.sent.filter(m => m.params?.name === 'refresh_usage_card');
  assert.strictEqual(calls.length, 0, 'should not hydrate when the payload was delivered');
});

test('a reference with no metadata triggers hydration', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: { toolOutput: { kind: 'usage_card_ref', threadId: 'task-1', snapshotId: 'snapshot-1' } }
  });
  const call = host.sent.find(m => m.method === 'tools/call' && m.params?.name === 'refresh_usage_card');
  assert.ok(call, 'card should request its own data when metadata is absent');
  assert.strictEqual(call.params.arguments.thread_id, 'task-1');
  assert.strictEqual(call.params.arguments.include_details, false, 'fallback should only recover the compact header');
  assert.strictEqual(call.params.arguments.snapshot_id, 'snapshot-1', 'fallback should recover the original snapshot');
});

test('a wrapped payload on the tool-result channel is recognised', async () => {
  const host = boot();
  await initialize(host);
  host.fire('message', {
    jsonrpc: '2.0',
    method: 'ui/notifications/tool-result',
    params: { mcp_tool_result: { _meta: { [META_KEY]: report({ thread: { id: 'task-1', name: 'VIACHANNEL' } }) } } }
  });
  assert.ok(host.root.innerHTML.includes('VIACHANNEL'), 'wrapped tool-result payload should render');
});

test('details load once on expansion while the original header stays fixed', async () => {
  const host = boot();
  const initial = report({ detailsLoaded: false, generatedAt: '2026-09-15T20:00:00+00:00', combinedTokens: 10 });
  await initialize(host);
  host.fire('openai:set_globals', { globals: { toolResponseMetadata: { [META_KEY]: initial } } });
  assert.strictEqual(host.sent.filter(m => m.params?.name === 'refresh_usage_card').length, 0, 'collapsed card should not fetch details');

  host.details.open = true;
  host.details.events.toggle();
  const calls = host.sent.filter(m => m.params?.name === 'refresh_usage_card');
  assert.strictEqual(calls.length, 1, 'first expansion should load details once');
  assert.strictEqual(calls[0].params.arguments.include_details, true);

  const expanded = report({
    generatedAt: '2026-09-15T20:10:00+00:00',
    combinedTokens: 999,
    topTasks: [{ id: 'task-2', name: 'Another task', totalTokens: 20 }]
  });
  host.reply(calls[0].id, { structuredContent: expanded });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(host.root.innerHTML.includes('Another task'), 'expanded body should show fetched tasks');
  assert.ok(host.root.innerHTML.includes('Task 10 raw'), 'header should keep the creation snapshot');
  assert.ok(!host.root.innerHTML.includes('Task 999 raw'), 'detail fetch must not replace the header');
  assert.ok(host.root.innerHTML.includes('Cross-task details loaded'), 'body should distinguish its load time');

  host.details.open = false;
  host.details.events.toggle();
  host.details.open = true;
  host.details.events.toggle();
  assert.strictEqual(host.sent.filter(m => m.params?.name === 'refresh_usage_card').length, 1, 're-expansion should not fetch again');
});

test('a live flag in an older report never starts timed refreshes', async () => {
  const host = boot();
  await initialize(host);
  const oldLiveReport = report({
    detailsLoaded: false,
    liveRefresh: { enabled: true, intervalMs: 10, untilEpochMs: Date.now() + 1000 }
  });
  host.fire('openai:set_globals', { globals: { toolResponseMetadata: { [META_KEY]: oldLiveReport } } });
  await new Promise(resolve => setTimeout(resolve, 50));
  assert.strictEqual(host.sent.filter(m => m.params?.name === 'refresh_usage_card').length, 0);
});

test('details-load failure reports the error panel height to the host', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: { toolResponseMetadata: { [META_KEY]: report({ detailsLoaded: false }) } }
  });
  host.details.open = true;
  host.details.events.toggle();
  const call = host.sent.find(m => m.params?.name === 'refresh_usage_card');
  assert.ok(call);
  host.body.scrollHeight = 20;
  host.fire('message', { jsonrpc: '2.0', id: call.id, error: { message: 'failed' } });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(host.heights.includes(20), 'the host should receive the new error-panel height');
});

test('a reference delivered before init is replayed after init', async () => {
  // Host with no window.openai posts the tool result while ui/initialize is
  // still in flight. The ref must be kept and hydrated once the bridge is up.
  const host = boot({ noOpenai: true });
  host.fire('message', {
    jsonrpc: '2.0',
    method: 'ui/notifications/tool-result',
    params: { structuredContent: { kind: 'usage_card_ref', threadId: 'task-1' } }
  });
  assert.strictEqual(host.sent.filter(m => m.params?.name === 'refresh_usage_card').length, 0, 'cannot hydrate before init');
  await initialize(host);
  const calls = host.sent.filter(m => m.params?.name === 'refresh_usage_card');
  assert.strictEqual(calls.length, 1, 'pre-init reference should hydrate exactly once after init');
});

test('a re-delivered reference never replaces a rendered card', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: { toolResponseMetadata: { [META_KEY]: report({ thread: { id: 'task-1', name: 'GOOD' } }) } }
  });
  assert.ok(host.root.innerHTML.includes('GOOD'));
  // Host re-emits the persistent ref alongside an unrelated change.
  host.fire('openai:set_globals', {
    globals: { theme: 'dark', toolOutput: { kind: 'usage_card_ref', threadId: 'task-1' } }
  });
  assert.strictEqual(host.sent.filter(m => m.params?.name === 'refresh_usage_card').length, 0, 'must not hydrate over a rendered card');
  assert.ok(host.root.innerHTML.includes('GOOD'), 'rendered card must survive');
});

test('a later tool result cannot overwrite a completed card', async () => {
  const host = boot();
  await initialize(host);
  const original = report({ thread: { id: 'task-1', name: 'ORIGINAL' } });
  const later = report({ generatedAt: '2026-09-15T20:05:00+00:00', thread: { id: 'task-1', name: 'LATER' } });
  host.fire('openai:set_globals', { globals: { toolResponseMetadata: { [META_KEY]: original } } });
  host.fire('message', { jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { _meta: { [META_KEY]: later } } });
  assert.ok(host.root.innerHTML.includes('ORIGINAL'), 'original snapshot must remain');
  assert.ok(!host.root.innerHTML.includes('LATER'));
});

test('a render error during hydration does not loop the fallback', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', { globals: { toolOutput: { kind: 'usage_card_ref', threadId: 'task-1' } } });
  const first = host.sent.filter(m => m.params?.name === 'refresh_usage_card');
  assert.strictEqual(first.length, 1);
  // A report that makes render throw (non-numeric reset epoch reaches `when`).
  const poison = report({ limit: { usedPercent: 50, resetsAt: 'not-a-number', windowMinutes: 60 } });
  host.reply(first[0].id, { structuredContent: poison });
  await new Promise(resolve => setTimeout(resolve, 1600));
  const after = host.sent.filter(m => m.params?.name === 'refresh_usage_card');
  assert.strictEqual(after.length, 1, `render errors must not re-request; saw ${after.length}`);
});

test('a failed hydration retries instead of stranding the card', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: { toolOutput: { kind: 'usage_card_ref', threadId: 'task-1' } }
  });
  const first = host.sent.filter(m => m.params?.name === 'refresh_usage_card');
  assert.strictEqual(first.length, 1);

  // Fail it the way the bridge would.
  host.fire('message', { jsonrpc: '2.0', id: first[0].id, error: { message: 'nope' } });
  await new Promise(resolve => setTimeout(resolve, 1400));

  const after = host.sent.filter(m => m.params?.name === 'refresh_usage_card');
  assert.ok(after.length > 1, `expected a retry, saw ${after.length} call(s)`);
});

(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      await fn();
      console.log(`ok   ${name}`);
    } catch (error) {
      failed += 1;
      console.log(`FAIL ${name}\n     ${error.message}`);
    }
  }
  console.log(`\n${tests.length - failed}/${tests.length} passed`);
  process.exit(failed ? 1 : 0);
})();
