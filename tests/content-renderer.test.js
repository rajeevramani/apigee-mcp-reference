const test = require('node:test');
const assert = require('node:assert/strict');
const renderer = require('../app/content-renderer.js');

test('Markdown renderer escapes HTML and renders Mermaid sequence steps', () => {
  const markdown = `# Payment flow\n\n<script>alert('x')</script>\n\n\`\`\`mermaid\nsequenceDiagram\n  Client->>Payments API: Create payment\n  Payments API-->>Client: 202 Accepted\n\`\`\``;
  const html = renderer.renderMarkdown(markdown);

  assert.match(html, /<h1>Payment flow<\/h1>/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /class="sequence-diagram"/);
  assert.match(html, /Client/);
  assert.match(html, /Create payment/);
  assert.match(html, /202 Accepted/);
});

test('OpenAPI renderer summarizes methods, paths, and operation identifiers', () => {
  const yaml = `openapi: 3.0.3\ninfo:\n  title: Payments API\n  version: 1.0.0\npaths:\n  /payments:\n    post:\n      operationId: create_payment\n      summary: Create a payment\n  /payments/{payment_id}:\n    get:\n      operationId: get_payment\n      summary: Retrieve payment status\n`;
  const html = renderer.renderOpenApi(yaml);

  assert.match(html, /Payments API/);
  assert.match(html, /POST/);
  assert.match(html, /\/payments/);
  assert.match(html, /create_payment/);
  assert.match(html, /GET/);
  assert.match(html, /get_payment/);
});

test('Rich-content detection selects Markdown and OpenAPI presentations', () => {
  assert.equal(renderer.detectContentKind({ content_type: 'text/markdown' }), 'markdown');
  assert.equal(renderer.detectContentKind({ content_type: 'application/yaml', format: 'openapi-3.0-yaml' }), 'openapi');
  assert.equal(renderer.detectContentKind({ content_type: 'application/json' }), null);
});
