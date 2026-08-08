(function (root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.AgentSimulator = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';

  const PAYMENT_IMPLEMENTATION_PLAN = [
    {
      tool: 'api_catalogue_search',
      reason: 'Discover which payment APIs are available before choosing documentation.',
      arguments: { query: 'payment APIs', limit: 3 }
    },
    {
      tool: 'documentation_search',
      reason: 'Find the most relevant implementation section for payment initiation.',
      arguments: { query: 'payment initiation', api_name: 'payments', limit: 3 }
    },
    {
      tool: 'documentation_section_get',
      reason: 'Retrieve the complete implementation guidance identified by search.',
      arguments: { api_name: 'payments', section_id: 'payment-initiation' }
    },
    {
      tool: 'openapi_spec_get',
      reason: 'Inspect exact paths, parameters, and schemas before presenting an answer.',
      arguments: { api_name: 'payments' }
    }
  ];

  function planScenario(tools, scenarioId) {
    if (scenarioId !== 'payment-implementation') return [];
    const available = new Set((tools || []).map(tool => tool.name));
    return PAYMENT_IMPLEMENTATION_PLAN
      .filter(step => available.has(step.tool))
      .map(step => ({ ...step, arguments: { ...step.arguments } }));
  }

  function describeAccess(tools) {
    const available = new Set((tools || []).map(tool => tool.name));
    const expected = PAYMENT_IMPLEMENTATION_PLAN.map(step => step.tool);
    const missing = expected.filter(name => !available.has(name));
    return {
      label: missing.length ? 'Restricted access' : 'Full access',
      missing,
      explanation: missing.includes('api_catalogue_search')
        ? 'This agent cannot discover APIs through the catalogue, so it starts with documentation it is entitled to use.'
        : missing.length
          ? 'This agent adapts its plan to the tools exposed by its API product.'
          : 'This agent can discover APIs and retrieve both implementation guidance and exact API contracts.'
    };
  }

  function parseMcpResponse(text, contentType) {
    if (!text.trim()) return null;
    if (String(contentType).includes('text/event-stream')) {
      const events = text.split(/\r?\n/)
        .filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trim())
        .filter(Boolean)
        .map(line => JSON.parse(line));
      return events.at(-1) || null;
    }
    return JSON.parse(text);
  }

  function redactCredential(value, credential) {
    if (!credential) return value;
    if (typeof value === 'string') return value.split(credential).join('[REDACTED]');
    if (Array.isArray(value)) return value.map(item => redactCredential(item, credential));
    if (value && typeof value === 'object') {
      return Object.fromEntries(
        Object.entries(value).map(([key, item]) => [
          redactCredential(key, credential),
          redactCredential(item, credential)
        ])
      );
    }
    return value;
  }

  function createClient({ endpoint, apiKey, fetchImpl, onTrace }) {
    const send = fetchImpl || root.fetch.bind(root);
    const trace = onTrace || (() => {});
    let requestId = 0;
    let sessionId = null;
    let protocolVersion = '2025-03-26';

    async function request(method, params, notification = false) {
      const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'MCP-Protocol-Version': protocolVersion,
        'x-api-key': apiKey
      };
      if (sessionId) headers['Mcp-Session-Id'] = sessionId;
      const payload = { jsonrpc: '2.0', method };
      if (!notification) payload.id = ++requestId;
      if (params !== undefined) payload.params = params;
      trace({
        type: 'request',
        method,
        payload: redactCredential(payload, apiKey),
        headers: {
          ...redactCredential(headers, apiKey),
          'x-api-key': '[REDACTED]'
        }
      });

      let response;
      try {
        response = await send(endpoint, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload)
        });
      } catch (error) {
        throw new Error(redactCredential(error?.message || 'MCP request failed.', apiKey));
      }
      sessionId = response.headers.get('Mcp-Session-Id') || sessionId;
      let text;
      try {
        text = await response.text();
      } catch (error) {
        throw new Error(redactCredential(error?.message || 'Could not read the MCP response.', apiKey));
      }
      const safeText = redactCredential(text, apiKey);
      let data;
      try {
        data = parseMcpResponse(text, response.headers.get('content-type') || '');
      } catch (_) {
        trace({
          type: 'response',
          method,
          status: response.status,
          data: { parseError: 'Invalid JSON or SSE data', raw: safeText }
        });
        throw new Error('MCP response was not valid JSON or SSE data.');
      }
      const safeData = redactCredential(data, apiKey);
      trace({ type: 'response', method, status: response.status, data: safeData });
      if (!response.ok) throw new Error(safeData?.error?.message || safeText || `HTTP ${response.status}`);
      if (safeData?.error) throw new Error(safeData.error.message || JSON.stringify(safeData.error));
      return safeData?.result ?? null;
    }

    async function connectAndList() {
      const initialized = await request('initialize', {
        protocolVersion,
        capabilities: {},
        clientInfo: { name: 'apigee-agent-simulator', version: '1.0.0' }
      });
      protocolVersion = initialized?.protocolVersion || protocolVersion;
      await request('notifications/initialized', {}, true);
      const listed = await request('tools/list', {});
      return {
        capabilities: initialized?.capabilities || {},
        serverInfo: initialized?.serverInfo || {},
        tools: Array.isArray(listed?.tools) ? listed.tools : []
      };
    }

    async function callTool(name, args) {
      return request('tools/call', { name, arguments: args });
    }

    return { callTool, connectAndList };
  }

  function summarizeResult(result) {
    const text = result?.content?.length === 1 ? result.content[0]?.text : null;
    let document = null;
    if (text) {
      try { document = JSON.parse(text); } catch (_) { /* raw text remains visible in the protocol trace */ }
    }
    if (Number.isInteger(document?.returned)) {
      return `Tool returned ${document.returned} result${document.returned === 1 ? '' : 's'}.`;
    }
    if (document?.content_type === 'text/markdown') {
      return `Retrieved the complete Markdown section${document.title ? ` “${document.title}”` : ''}.`;
    }
    if (document?.content_type === 'application/yaml') {
      return 'Retrieved the authoritative OpenAPI YAML document.';
    }
    return result?.isError ? 'The tool returned an application error.' : 'Tool call completed.';
  }

  async function runPlan(client, plan, onAction) {
    const emit = onAction || (() => {});
    const results = [];
    for (const step of plan) {
      emit({ type: 'decision', ...step });
      const result = await client.callTool(step.tool, step.arguments);
      emit({ type: 'observation', tool: step.tool, summary: summarizeResult(result), result });
      if (result?.isError) throw new Error(`${step.tool} reported an error.`);
      results.push({ tool: step.tool, result });
    }
    return results;
  }

  function summarizeOutcome(access, results) {
    const evidence = (results || []).map(item => item.tool);
    const evidenceText = evidence.length ? evidence.join(', ') : 'no successful tool calls';
    const availabilityText = access.missing.length
      ? `Unavailable planned tools: ${access.missing.join(', ')}.`
      : 'All planned tools were available.';
    return `The agent assembled its answer from: ${evidenceText}. ${availabilityText}`;
  }

  return {
    createClient,
    describeAccess,
    parseMcpResponse,
    planScenario,
    runPlan,
    summarizeOutcome,
    summarizeResult
  };
}));
