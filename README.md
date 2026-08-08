# Apigee MCP reference implementation

A customer-neutral, working reference implementation for exposing operations from multiple REST APIs as governed MCP tools through one Apigee MCP Discovery Proxy.

It demonstrates the part that simple architecture diagrams usually omit:

```text
MCP client
  → Apigee MCP Discovery Proxy
  → Apigee managed MCP service
  → ordinary Apigee reverse proxy
  → REST backend
```

The repository includes two mock REST APIs, their ordinary Apigee reverse proxies, aligned OpenAPI contracts, a generated MCP proxy bundle for inspection, API-product definitions for tool-level entitlement, representative Markdown and OpenAPI content, and a browser-only MCP client. The documentation proxy uses Apigee `AssignMessage` policies and a null route, so no documentation backend is required.

> This is an independent community reference implementation. It is not an official Google product, is not affiliated with or endorsed by Google, and does not provide an Apigee environment or public MCP endpoint.

## What the reference proves

- One MCP Discovery Proxy can expose operations from separate source proxies.
- Every MCP tool maps to an operation on a deployed ordinary Apigee reverse proxy.
- The full-path MCP source contract and relative-path reverse-proxy contract must align.
- Read-only `GET` operations with bounded query parameters generate flat, model-facing MCP arguments while preserving the same contract in the reverse proxy.
- API products can filter `tools/list` by caller entitlement.
- A caller can be allowed to discover and invoke one tool while being denied another.
- `ParsePayload → VerifyAPIKey → Quota` enables operation-aware access and quota enforcement.
- A static browser client can exercise `initialize`, `tools/list`, and `tools/call` without storing a credential.
- Apigee can simulate a documentation service that searches content, returns complete Markdown with a textual sequence diagram, and returns an OpenAPI YAML document.
- The browser can safely render the Markdown and sequence flow, summarize OpenAPI operations, and retain the raw MCP response for inspection.
- A deterministic agent simulation compares full and restricted API-product access while exposing initialization, discovery, planning, tool calls, and observations.

## Repository layout

```text
apigee/
  api-products/               API-product payload-operation definitions
  api-catalogue-search-mock/  Ordinary source reverse-proxy bundle
  documentation-search-mock/  Ordinary source reverse-proxy bundle
  mcp-discovery-proxy/         Generated MCP proxy bundle for inspection
app/
  agent-simulator.js           Entitlement-aware deterministic agent and MCP trace client
  content-renderer.js          Dependency-free Markdown, sequence, and OpenAPI renderer
  mcp-tool-browser.html        Static MCP lifecycle client
samples/
  payments/                    Customer-neutral Markdown and OpenAPI content
specs/
  mcp-tools.openapi.yaml
  api-catalogue-search-reverse-proxy.openapi.yaml
  documentation-search-reverse-proxy.openapi.yaml
docs/
  deployment.md                Environment preparation and deployment sequence
  learnings.md                 Architecture and troubleshooting field notes
scripts/
  configure.py                 Render placeholders for your Apigee environment
  package.py                   Build importable proxy ZIP files
  sync_mock_content.py         Synchronize readable samples into AssignMessage policies
  verify.py                    Validate the public or rendered artifact tree
```

## Prerequisites

You need your own eligible Apigee environment and API Hub setup. Confirm current product eligibility, regions, limits, and supported OpenAPI versions in the [official Apigee MCP documentation](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-quickstart) before deploying.

You will also need:

- Python 3.9 or newer for the local helper scripts;
- an Apigee runtime hostname;
- an Apigee organisation name;
- permission to create and deploy proxies, products, developers, and apps;
- a static web server if you want to use the browser client.

## Configure a local working copy

The checked-in artifacts intentionally contain placeholders and no live endpoint:

```text
YOUR_APIGEE_HOSTNAME
YOUR_APIGEE_ORG
```

Render them into an ignored build directory:

```bash
python3 scripts/configure.py \
  --hostname api.example.com \
  --org my-apigee-org

python3 scripts/verify.py --root build/configured --configured
python3 scripts/package.py --source build/configured/apigee
```

The packaged proxy ZIP files are written to `dist/`. The source tree remains customer-neutral.

## Deploy and test

Follow [`docs/deployment.md`](docs/deployment.md). The short sequence is:

1. Prepare API Hub and attach the Apigee runtime project.
2. Import and deploy both ordinary reverse proxies.
3. Confirm their OpenAPI operations have been ingested by API Hub.
4. Create the MCP Discovery Proxy through **Apigee → API proxies → Create → MCP Discovery Proxy** using `build/configured/specs/mcp-tools.openapi.yaml`.
5. Add the included CORS, `ParsePayload`, API-key verification, and quota policies in the documented order.
6. Create the API products, developer, and developer apps in your own organisation.
7. Test direct REST before testing MCP.
8. Exercise `initialize → tools/list → tools/call`.
9. Inspect each generated `inputSchema`; do not infer MCP arguments from the source YAML alone.

The generated MCP bundle under `apigee/mcp-discovery-proxy/` is retained as an inspectable reference. Use the current documented Apigee creation flow rather than assuming that importing a previously generated bundle is supported in every tenant or release.

## Browser client

After configuration:

```bash
cd build/configured
python3 -m http.server 8080
```

Open <http://localhost:8080/app/mcp-tool-browser.html>. The **Tool browser** tab accepts one API key and exposes the generated schemas and direct tool calls. The **Agent simulation** tab accepts full-access and documentation-only keys, gives both profiles the same payment-implementation goal, and shows how each profile discovers tools and adapts its plan. Every protocol request and response is available under **Behind the scenes** with API-key values redacted.

The simulation is deterministic and does not run an LLM. Its purpose is to make MCP discovery, API-product filtering, tool selection, and evidence gathering visible. Keys remain in browser memory and are sent only in the `x-api-key` header. Calls to `documentation_section_get` render the returned Markdown and sequence flow; calls to `openapi_spec_get` render an operation summary. Direct tool calls retain a **Raw response** view.

Never commit credentials, place them in URLs, or embed them in the static file.

## Verify the checked-in repository

```bash
python3 scripts/verify.py
```

The verifier checks customer-neutral placeholders and content, literal IPv4 addresses, XML and JSON syntax, synchronized mock payloads, duplicate OpenAPI copies, bounded MCP inputs, source-proxy OpenAPI validation, missing-query guards, tool-selection guidance, OpenAPI licensing and security declarations, browser HTML structure, and required repository files. Before publishing from a private source, pass an untracked blocklist with `--forbidden-file /path/to/private-identifiers.txt` to check exact tenant and customer identifiers without embedding them in the public verifier.

## Security and production use

This repository uses mock read-only operations to demonstrate architecture and entitlement. The source mocks explicitly declare `security: []`; the example `x-api-key` check protects the MCP Discovery Proxy, not the ordinary source proxies. This is not a production security baseline. Before production use, resolve caller identity, developer-app mapping, API-product ownership, source-API authorization, backend identity propagation, secret handling, audit requirements, quotas, and write-operation risk.

See [`SECURITY.md`](SECURITY.md) for reporting and credential guidance.

## Licence

Apache License 2.0. See [`LICENSE`](LICENSE).
