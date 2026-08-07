# Deployment guide

This guide turns the customer-neutral templates into artifacts for your own Apigee organisation. Product behaviour changes; check the current official documentation before deploying.

## 1. Confirm prerequisites

The official Apigee MCP quickstart currently directs users to create an **MCP Discovery Proxy**, upload an OpenAPI document, add policies, and deploy it to a supported environment.[1] API Hub must be provisioned and associated with the Apigee runtime project so its Apigee plug-in can ingest proxy metadata.[2][3]

Confirm:

- your Apigee organisation and region are eligible;
- the target environment supports the current MCP capability;
- an environment group and externally reachable hostname exist;
- API Hub is provisioned in the appropriate region;
- the runtime project is attached to API Hub;
- the Apigee plug-in and metadata import are active;
- you can create proxies, products, developers, and apps.

## 2. Render the templates

Use a hostname without `https://`:

```bash
python3 scripts/configure.py \
  --hostname api.example.com \
  --org my-apigee-org

python3 scripts/verify.py --root build/configured --configured
python3 scripts/package.py --source build/configured/apigee
```

This produces configured source under `build/configured/` and proxy ZIP files under `dist/`. Both directories are ignored by Git.

## 3. Deploy the ordinary source proxies first

Import and deploy:

```text
dist/documentation-search-mock.zip
dist/api-catalogue-search-mock.zip
```

The mock proxies return controlled JSON responses. Call each REST endpoint directly before involving MCP:

```text
GET https://YOUR_HOST/developer-intelligence/v1/documentation/search?query=payments&limit=1
GET https://YOUR_HOST/api-catalogue/v1/search?query=payments&limit=1
```

A deployment response alone is not enough. Confirm each call reaches Apigee and returns the expected mock payload.

## 4. Wait for API Hub ingestion

Each ordinary proxy embeds a reverse-proxy OpenAPI document. API Hub needs to ingest the proxy, specification, and operation before it can map the MCP operation.

Confirm that API Hub shows:

- both deployed source proxies;
- one OpenAPI specification for each;
- `documentation_search` and `api_catalogue_search` operations;
- the correct deployment/environment association.

If a proxy appears without a specification or operation, do not continue. Fix the proxy bundle or wait for metadata ingestion.

## 5. Create the MCP Discovery Proxy

Use the current documented flow:

```text
Apigee → API proxies → Create → MCP Discovery Proxy
```

Upload:

```text
build/configured/specs/mcp-tools.openapi.yaml
```

The source OpenAPI contains full paths. The embedded reverse-proxy OpenAPI files contain paths relative to each proxy base path:

```text
MCP source:       /developer-intelligence/v1/documentation/search
Proxy base path:  /developer-intelligence/v1
Reverse OAS path: /documentation/search
operationId:      documentation_search
```

The effective method, path, operation ID, query parameters, successful response schema, and hostname assumptions must remain aligned. Both contracts model these read-only searches as `GET` operations with bounded query parameters. In the reproduced environment, that produced flat MCP inputs; component-referenced and inline request bodies both produced wrappers.

The MCP source contract also documents `401`, `403`, and `429` responses that can be emitted by the authenticated, product-governed MCP edge. The unauthenticated source-mock contracts omit those edge-only responses and document only the errors their own proxy path can return.

Use this GET pattern only when inputs are bounded and non-sensitive. Query strings can appear in client history, gateway logs, caches, and observability data. Keep sensitive or larger search inputs in a `POST` body and accept the generated wrapper, or design a separate source operation for the MCP tool.

Each source proxy runs `RF-Missing-Query` and then `OAS-Validate-Request` before returning the mock response. The explicit guard is required because the tested OAS validation runtime did not reject an absent required query parameter by itself. OAS validation enforces the remaining declared parameter constraints and rejects unspecified query parameters.

The checked-in generated bundle under `apigee/mcp-discovery-proxy/` is an implementation reference. Compare generated policies and targets with it, but use the current product workflow unless current official documentation explicitly supports your chosen import path.

## 6. Add governance policies

For API-product-aware MCP access, use this request order:

```text
CORS (when a browser client is required)
ParsePayload-MCP
VerifyAPIKey-1
Quota-PerToolLimit
```

`ParsePayload` must run before API-key verification and quota so Apigee can derive payload operations such as `tools/list` and `tools/call/documentation_search` from the JSON-RPC request.

The API key reference in this example is:

```xml
<APIKey ref="request.header.x-api-key"/>
```

This policy protects the MCP Discovery Proxy. The two read-only source mocks declare `security: []` because they do not implement source-API authentication. Do not copy that boundary into production without explicitly designing source-API authorization and backend identity propagation.

## 7. Create API products and apps

Use the JSON files under:

```text
build/configured/apigee/api-products/
```

The products demonstrate two audiences:

| Product | Visible and callable tools |
|---|---|
| `mcp-all-tools` | `documentation_search`, `api_catalogue_search` |
| `mcp-documentation-only` | `documentation_search` |

Both include `tools/list`. The API-product payload-operation model supports only `tools/list` and `tools/call/*`; MCP lifecycle methods such as `initialize`, `notifications/initialized`, and `ping` must not be added as product operations.

The reference proxy therefore runs `Quota-PerToolLimit` only when `ParsePayload-MCP` derives `tools/list` or `tools/call/*`. Lifecycle requests are still API-key authenticated, but they do not attempt to resolve a quota configuration from an unsupported product operation.

Create a developer and one app for each product. Keep consumer keys in your credential store; do not write them into this repository.

## 8. Test the MCP lifecycle

Test in this order:

1. Direct source REST operation.
2. `initialize` without a key — expect rejection once API-key verification is active.
3. `initialize` with an allowed key.
4. `tools/list` with the all-tools key — expect two tools.
5. `tools/list` with the documentation-only key — expect one tool.
6. `tools/call/documentation_search` with the documentation-only key — expect success.
7. Direct `tools/call/api_catalogue_search` with the documentation-only key — expect denial.
8. Both tool calls with the all-tools key — expect success.
9. Omit `query`, send a legacy body wrapper, add an unspecified argument, and exceed `limit` — expect rejection.

Inspect the `inputSchema` returned by `tools/list`. Confirm that both tools expose `query` and `limit` directly, with `api_name` also available for `documentation_search`, and that `query` is required. The schema returned by `tools/list` is the contract the MCP client actually sees. If a wrapper appears, treat that generated schema as the immediate client contract and investigate the source OpenAPI and Apigee/API Hub transformation before release.

## 9. Use the browser client

Serve the configured directory:

```bash
cd build/configured
python3 -m http.server 8080
```

Open <http://localhost:8080/app/mcp-tool-browser.html>, enter the API key, and connect. The endpoint must support CORS, preflight, the negotiated MCP protocol header, and any session header returned by the server.

## Sources

1. [Create an MCP server using an Apigee API proxy](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-quickstart)
2. [Auto-register Apigee APIs in API Hub](https://docs.cloud.google.com/apigee/docs/apihub/auto-register-apis#attach-a-runtime-project)
3. [Manage Google Cloud plug-ins in API Hub](https://docs.cloud.google.com/apigee/docs/apihub/manage-gcp-plugins)
