const test = require('node:test');
const assert = require('node:assert/strict');
const simulator = require('../app/agent-simulator.js');

test('full-access plan uses catalogue discovery before documentation retrieval', () => {
  const tools = [
    { name: 'documentation_search' },
    { name: 'documentation_section_get' },
    { name: 'openapi_spec_get' },
    { name: 'api_catalogue_search' }
  ];

  const plan = simulator.planScenario(tools, 'payment-implementation');

  assert.deepEqual(plan.map(step => step.tool), [
    'api_catalogue_search',
    'documentation_search',
    'documentation_section_get',
    'openapi_spec_get'
  ]);
  assert.equal(plan[0].arguments.query, 'payment APIs');
  assert.match(plan[0].reason, /discover/i);
});

test('restricted plan adapts to discovered entitlements and explains the missing capability', () => {
  const tools = [
    { name: 'documentation_search' },
    { name: 'documentation_section_get' },
    { name: 'openapi_spec_get' }
  ];

  const plan = simulator.planScenario(tools, 'payment-implementation');
  const access = simulator.describeAccess(tools);

  assert.deepEqual(plan.map(step => step.tool), [
    'documentation_search',
    'documentation_section_get',
    'openapi_spec_get'
  ]);
  assert.equal(access.label, 'Restricted access');
  assert.deepEqual(access.missing, ['api_catalogue_search']);
  assert.match(access.explanation, /cannot discover APIs/i);
});

test('outcome summary names actual evidence and missing tools for arbitrary partial access', () => {
  const access = simulator.describeAccess([
    { name: 'api_catalogue_search' },
    { name: 'documentation_search' }
  ]);
  const summary = simulator.summarizeOutcome(access, [
    { tool: 'api_catalogue_search' },
    { tool: 'documentation_search' }
  ]);

  assert.match(summary, /api_catalogue_search, documentation_search/);
  assert.match(summary, /documentation_section_get, openapi_spec_get/);
  assert.doesNotMatch(summary, /catalogue discovery was unavailable/i);
  assert.doesNotMatch(summary, /exact OpenAPI contract/i);
});

test('MCP client initializes, preserves the session, lists tools, and redacts credentials from traces', async () => {
  const requests = [];
  const traces = [];
  const responses = [
    response({
      jsonrpc: '2.0',
      id: 1,
      result: {
        protocolVersion: '2025-11-25',
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: 'example-mcp', version: '1.0.0' }
      }
    }, { 'Mcp-Session-Id': 'session-123' }),
    response(null, {}, 202),
    response({
      jsonrpc: '2.0',
      id: 2,
      result: { tools: [{ name: 'documentation_search', inputSchema: { type: 'object' } }] }
    })
  ];
  const fakeFetch = async (url, options) => {
    requests.push({ url, options, payload: JSON.parse(options.body) });
    return responses.shift();
  };
  const client = simulator.createClient({
    endpoint: 'https://api.example.com/mcp',
    apiKey: 'example-key-value',
    fetchImpl: fakeFetch,
    onTrace: event => traces.push(event)
  });

  const connected = await client.connectAndList();

  assert.deepEqual(requests.map(item => item.payload.method), [
    'initialize',
    'notifications/initialized',
    'tools/list'
  ]);
  assert.equal(requests[1].options.headers['Mcp-Session-Id'], 'session-123');
  assert.equal(requests[2].options.headers['MCP-Protocol-Version'], '2025-11-25');
  assert.deepEqual(connected.tools.map(tool => tool.name), ['documentation_search']);
  assert.equal(connected.serverInfo.name, 'example-mcp');
  assert.doesNotMatch(JSON.stringify(traces), /example-key-value/);
  assert.match(JSON.stringify(traces), /\[REDACTED\]/);
});

test('MCP client redacts a credential echoed in a successful tool response', async () => {
  const traces = [];
  const client = simulator.createClient({
    endpoint: 'https://api.example.com/mcp',
    apiKey: 'example-key-value',
    fetchImpl: async () => response({
      jsonrpc: '2.0',
      id: 1,
      result: { content: [{ type: 'text', text: 'echo: example-key-value' }] }
    }),
    onTrace: event => traces.push(event)
  });

  const result = await client.callTool('documentation_search', { query: 'payments' });

  assert.doesNotMatch(JSON.stringify({ result, traces }), /example-key-value/);
  assert.match(JSON.stringify({ result, traces }), /\[REDACTED\]/);
});

test('MCP client redacts a credential echoed in a server error', async () => {
  const traces = [];
  const client = simulator.createClient({
    endpoint: 'https://api.example.com/mcp',
    apiKey: 'example-key-value',
    fetchImpl: async () => response({
      jsonrpc: '2.0',
      id: 1,
      error: { code: -32000, message: 'Rejected example-key-value' }
    }, {}, 403),
    onTrace: event => traces.push(event)
  });

  await assert.rejects(
    client.callTool('documentation_search', { query: 'payments' }),
    error => !error.message.includes('example-key-value') && error.message.includes('[REDACTED]')
  );
  assert.doesNotMatch(JSON.stringify(traces), /example-key-value/);
});

test('MCP trace redacts credentials from payloads, session headers, and response property names', async () => {
  const traces = [];
  let call = 0;
  const client = simulator.createClient({
    endpoint: 'https://api.example.com/mcp',
    apiKey: 'example-key-value',
    fetchImpl: async () => {
      call += 1;
      return response({
        jsonrpc: '2.0',
        id: call,
        result: { ['example-key-value']: 'echoed as a property name' }
      }, call === 1 ? { 'Mcp-Session-Id': 'session-example-key-value' } : {});
    },
    onTrace: event => traces.push(event)
  });

  await client.callTool('documentation_search', {
    query: 'example-key-value',
    ['example-key-value']: true
  });
  await client.callTool('documentation_search', { query: 'payments' });

  assert.doesNotMatch(JSON.stringify(traces), /example-key-value/);
  assert.match(JSON.stringify(traces), /\[REDACTED\]/);
});

test('MCP client does not leak a credential through malformed JSON parser errors', async () => {
  const traces = [];
  const client = simulator.createClient({
    endpoint: 'https://api.example.com/mcp',
    apiKey: 'example-key-value',
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      headers: { get: name => name.toLowerCase() === 'content-type' ? 'application/json' : null },
      text: async () => 'example-key-value is not JSON'
    }),
    onTrace: event => traces.push(event)
  });

  await assert.rejects(
    client.callTool('documentation_search', { query: 'payments' }),
    error => error.message === 'MCP response was not valid JSON or SSE data.'
  );
  assert.doesNotMatch(JSON.stringify(traces), /example-key-value/);
  assert.match(JSON.stringify(traces), /\[REDACTED\]/);
});

test('MCP client redacts credentials from transport exceptions', async () => {
  const client = simulator.createClient({
    endpoint: 'https://api.example.com/mcp',
    apiKey: 'example-key-value',
    fetchImpl: async () => { throw new Error('Network rejected example-key-value'); }
  });

  await assert.rejects(
    client.callTool('documentation_search', { query: 'payments' }),
    error => !error.message.includes('example-key-value') && error.message.includes('[REDACTED]')
  );
});

test('browser client defaults to the platform fetch implementation', () => {
  assert.doesNotThrow(() => simulator.createClient({
    endpoint: 'https://api.example.com/mcp',
    apiKey: 'browser-key'
  }));
});

test('plan runner exposes each agent decision and observation in execution order', async () => {
  const calls = [];
  const actions = [];
  const client = {
    callTool: async (name, args) => {
      calls.push({ name, args });
      return {
        content: [{ type: 'text', text: JSON.stringify({ returned: 1, content_type: 'text/markdown' }) }]
      };
    }
  };
  const plan = [
    { tool: 'documentation_search', reason: 'Find guidance.', arguments: { query: 'payments' } },
    { tool: 'documentation_section_get', reason: 'Read the section.', arguments: { api_name: 'payments', section_id: 'payment-initiation' } }
  ];

  const results = await simulator.runPlan(client, plan, action => actions.push(action));

  assert.deepEqual(calls.map(call => call.name), ['documentation_search', 'documentation_section_get']);
  assert.deepEqual(actions.map(action => action.type), [
    'decision', 'observation', 'decision', 'observation'
  ]);
  assert.equal(results.length, 2);
  assert.match(actions[1].summary, /returned 1 result/i);
  assert.doesNotMatch(JSON.stringify(actions), /undefined/);
});

test('plan runner stops instead of claiming success when an MCP tool reports an error', async () => {
  const client = {
    callTool: async () => ({
      isError: true,
      content: [{ type: 'text', text: 'The caller is not entitled to this operation.' }]
    })
  };

  await assert.rejects(
    simulator.runPlan(client, [{
      tool: 'openapi_spec_get',
      reason: 'Inspect the contract.',
      arguments: { api_name: 'payments' }
    }]),
    /openapi_spec_get reported an error/
  );
});

function response(document, headers = {}, status = 200) {
  const normalized = Object.fromEntries(
    Object.entries(headers).map(([name, value]) => [name.toLowerCase(), value])
  );
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: name => normalized[name.toLowerCase()] || null },
    text: async () => document === null ? '' : JSON.stringify(document)
  };
}
