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
    innerHTML: '',
    open: false,
    dataset: {},
    disabled: false,
    value: '',
    textContent: '',
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {},
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
  const root = makeElement();
  const openai = (options && options.noOpenai)
    ? undefined
    : { toolOutput: undefined, notifyIntrinsicHeight() {}, setWidgetState() {} };

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
      body: { scrollHeight: 10, getBoundingClientRect: () => ({ height: 10 }) },
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
  return { listeners, sent, root, openai, fire, reply, windowStub };
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

test('an unrelated globals update does not restore the stale snapshot', async () => {
  const host = boot();
  // The persistent global still holds the ORIGINAL show_usage_card snapshot.
  host.openai.toolResponseMetadata = {
    [META_KEY]: report({ detailsLoaded: false, thread: { id: 'task-1', name: 'STALE' } })
  };
  await initialize(host);

  // A refresh renders newer data.
  host.fire('openai:set_globals', {
    globals: { toolResponseMetadata: { [META_KEY]: report({ thread: { id: 'task-1', name: 'FRESH' } }) } }
  });
  assert.ok(host.root.innerHTML.includes('FRESH'), 'fresh data should render');

  // Now an update about something else entirely arrives.
  host.fire('openai:set_globals', { globals: { theme: 'dark' } });
  assert.ok(!host.root.innerHTML.includes('STALE'), 'stale snapshot must not be restored');
  assert.ok(host.root.innerHTML.includes('FRESH'), 'fresh data should survive');
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
    globals: { toolOutput: { kind: 'usage_card_ref', threadId: 'task-1' } }
  });
  const call = host.sent.find(m => m.method === 'tools/call' && m.params?.name === 'refresh_usage_card');
  assert.ok(call, 'card should request its own data when metadata is absent');
  assert.strictEqual(call.params.arguments.thread_id, 'task-1');
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

test('hydration preserves live:false from the reference', async () => {
  const host = boot();
  await initialize(host);
  host.fire('openai:set_globals', {
    globals: { toolOutput: { kind: 'usage_card_ref', threadId: 'task-1', live: false, liveUntilEpochMs: 0 } }
  });
  const call = host.sent.find(m => m.params?.name === 'refresh_usage_card');
  assert.ok(call, 'should hydrate');
  assert.strictEqual(call.params.arguments.live, false, 'must not turn live:false into polling');
  assert.strictEqual(call.params.arguments.live_until_epoch_ms, 0);
});

test('hydration preserves a live window when the caller asked for one', async () => {
  const host = boot();
  await initialize(host);
  const deadline = Date.now() + 60000;
  host.fire('openai:set_globals', {
    globals: { toolOutput: { kind: 'usage_card_ref', threadId: 'task-1', live: true, liveUntilEpochMs: deadline } }
  });
  const call = host.sent.find(m => m.params?.name === 'refresh_usage_card');
  assert.strictEqual(call.params.arguments.live, true);
  assert.strictEqual(call.params.arguments.live_until_epoch_ms, deadline);
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

test('an older snapshot of the same thread cannot overwrite a newer one', async () => {
  const host = boot();
  await initialize(host);
  const older = report({ generatedAt: '2026-09-15T20:00:00+00:00', detailsLoaded: false, thread: { id: 'task-1', name: 'OLDER' } });
  const newer = report({ generatedAt: '2026-09-15T20:05:00+00:00', thread: { id: 'task-1', name: 'NEWER' } });
  host.fire('openai:set_globals', { globals: { toolResponseMetadata: { [META_KEY]: newer } } });
  assert.ok(host.root.innerHTML.includes('NEWER'));
  // A host that re-sends full globals, or a late tool-result for the original call.
  host.fire('message', { jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { _meta: { [META_KEY]: older } } });
  host.fire('openai:set_globals', { globals: { toolResponseMetadata: { [META_KEY]: older } } });
  assert.ok(host.root.innerHTML.includes('NEWER'), 'older snapshot must be ignored');
  assert.ok(!host.root.innerHTML.includes('OLDER'));
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
