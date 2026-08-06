# Security policy

## Do not publish credentials

This repository intentionally contains no API keys, OAuth tokens, service-account material, private hostnames, or live tenant identifiers. Keep credentials out of source files, URLs, screenshots, issues, and pull requests.

The browser client stores the API key only in page memory and sends it in the `x-api-key` header. Close or reload the page to clear it.

## Supported use

The repository is a reference implementation using read-only mock operations. It is not a production security baseline. Production deployments must separately design caller authentication, developer-app and API-product mapping, backend identity, source-API authorization, quota, audit, secret storage, CORS, and write-operation controls.

## Report a vulnerability

Please do not open a public issue for a suspected vulnerability or exposed credential. Email `rajeev.ramani@itfrombit.com.au` with a concise description and reproduction details. Do not include live credentials; revoke them immediately through the owning system.
