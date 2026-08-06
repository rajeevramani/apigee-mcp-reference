# What the PoC taught us

These notes separate behaviour reproduced in the reference environment from general architecture recommendations. They intentionally omit tenant identifiers, customer material, credentials, and transient infrastructure details.

## The implementation has three layers

A working Apigee MCP implementation has three distinct layers:

1. **The ordinary API** — a REST backend exposed through a normal Apigee reverse proxy.
2. **API Hub metadata and operation mapping** — API Hub ingests the reverse proxy's OpenAPI operation and maps it to the MCP tool.
3. **The MCP Discovery Proxy** — the MCP protocol endpoint and its authentication, entitlement, quota, and analytics policies.

The dependency is real:

```text
MCP tool
  → deployed ordinary Apigee reverse proxy
  → REST backend
```

A reachable backend alone was not enough. The operation had to be represented by an ordinary deployed Apigee proxy that API Hub could identify.

## OpenAPI is part of the runtime assembly

The PoC required two aligned views of each operation:

- **MCP source OpenAPI:** full operation path used to generate the tool and its schema.
- **Reverse-proxy OpenAPI:** operation path relative to the proxy base path, embedded in the deployed bundle for API Hub ingestion.

For example:

```text
MCP source operation:    POST /developer-intelligence/v1/documentation/search
Reverse proxy base path:      /developer-intelligence/v1
Reverse OAS operation:   POST /documentation/search
Operation ID:                 documentation_search
```

The method, effective path, `operationId`, schemas, and hostname assumptions must agree. A source proxy can be deployed and callable while still being unusable as an MCP source if its OpenAPI metadata is missing, stale, or mismatched.

Treat OpenAPI validation and API Hub ingestion as release gates, not documentation cleanup.

## API Hub errors describe mapping, not only existence

The message `Reverse proxy not found for some tools` did not mean that no proxy resource existed. In the reproduced case, the proxy existed but API Hub could not match the MCP operation to an ingested reverse-proxy OpenAPI operation.

The useful diagnostic sequence is:

1. Is the ordinary proxy deployed?
2. Does direct REST return the expected response?
3. Does its deployed bundle declare an OpenAPI resource?
4. Has API Hub ingested the specification and operation?
5. Do method, effective path, environment, and base path match the MCP source contract?

## Tool arguments come from the generated schema

A referenced request-body schema generated a wrapper object in the MCP `inputSchema`. The successful call therefore used:

```json
{
  "DocumentationSearchRequest": {
    "query": "payment process endpoints",
    "api_name": "payments",
    "limit": 5
  }
}
```

The portable lesson is not the wrapper name. It is that MCP clients should inspect the `inputSchema` returned by `tools/list` rather than infer arguments from the REST request body.

## API products can govern individual tools

The secured reference used this policy order:

```text
ParsePayload
→ VerifyAPIKey
→ Quota
```

It then assigned exact payload operations to two products. The reproduced behaviour was:

- the all-tools key discovered and invoked both tools;
- the documentation-only key discovered only `documentation_search`;
- the documentation-only key invoked `documentation_search` successfully;
- a direct attempt to invoke `api_catalogue_search` with that key was rejected;
- a request without a key was rejected.

An implementation detail worth preserving: each `payloadOperationGroup.operationConfigs` entry contained exactly one payload operation. Combining several operations into one entry was rejected by the API.

## Test the layers in order

Use this order to avoid debugging MCP when the source API is broken:

```text
known runtime route
  → direct source REST operation
  → MCP initialize
  → tools/list
  → tools/call
  → entitlement denial and quota cases
```

A successful direct REST call proves routing and backend behaviour. It does not prove managed MCP registration, API Hub mapping, entitlement, or argument shape.

## Error-to-layer guide

| Symptom | Likely layer | Check |
|---|---|---|
| Gateway or ingress error | Runtime route | DNS, load balancer, backend health, environment-group hostname |
| Managed MCP target cannot resolve | MCP/API Hub prerequisites | API Hub instance, project association, Apigee plug-in |
| `Reverse proxy not found for some tools` | API Hub operation mapping | Embedded OAS, ingestion, relative path, method, environment |
| `tools/list` is empty | Entitlement or mapping | Product payload operations, caller credential, operation mapping |
| `tools/call` fails but direct REST works | MCP dispatch or contract | Tool name, generated `inputSchema`, product entitlement |
| Direct REST fails | Source API | Proxy deployment, route, target, mock/backend behaviour |

## Production boundary

This repository proves a read-only governance pattern. It does not settle production identity or risk decisions. Production design must separately answer:

- Who or what is the authenticated caller?
- How does that identity map to an Apigee developer app and API products?
- Which tools may the caller discover and invoke?
- What identity reaches the source API and backend?
- How are write operations approved, audited, limited, or reversed?
- Who owns the tool contract and lifecycle?

## Official references

- [Apigee MCP quickstart](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-quickstart)
- [Manage MCP servers in API Hub](https://docs.cloud.google.com/apigee/docs/apihub/manage-mcp-proxies)
- [Auto-register Apigee APIs in API Hub](https://docs.cloud.google.com/apigee/docs/apihub/auto-register-apis#attach-a-runtime-project)
- [Manage Google Cloud plug-ins in API Hub](https://docs.cloud.google.com/apigee/docs/apihub/manage-gcp-plugins)
