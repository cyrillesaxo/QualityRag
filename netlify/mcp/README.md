# QualityRAG MCP — isolated Netlify deployment

Site created: https://app.netlify.com/projects/qualityrag-mcp (site ID dbab8219-bd78-4fe5-9d70-da33adab1d48). No deploy has been published yet.

Deploy this repository's branch `feat/netlify-remote-mcp-20261108` to the dedicated site using base directory `netlify/mcp`, publish `public`, and Netlify Functions directory `netlify/functions` (as specified in netlify.toml). **Do not change the existing `quality-rag` PackSpec site.**

Required Netlify environment variables (functions scope, secret):
- `QUALITYRAG_MCP_ACCESS_TOKEN`: long random bearer token used by MCP clients. Static token is staging-only; replace with OAuth for ChatGPT production.
- `QUALITYRAG_API_ENDPOINT`: publicly reachable HTTPS URL for the QualityRAG activation runtime (without /api).
- `QUALITYRAG_API_TOKEN_JSON`: JSON representation of the signed access token expected by the existing Python QualityRAG SDK. The function encodes this JSON as base64url in the upstream Bearer header.

The adapter exposes six **read-only** tools. The existing Python stdio server is the contract reference. For now the API runtime must be deployed separately; a Neon database alone is not the runtime.

Validation after deployment:
1. GET /health returns service qualityrag-mcp and status ready (this is a process check, not proof the backend works).
2. POST /mcp without Bearer returns 401.
3. POST /mcp with Bearer and JSON-RPC initialize returns protocolVersion 2025-06-18.
4. tools/list returns six read-only tools with structured input schemas.
5. tools/call garden_query and policy_test must be checked against a live authenticated QualityRAG runtime; errors must never be reported as successful governance verdicts.

**Do not claim ChatGPT connection readiness before OAuth, endpoint testing, and backend persistence are verified.**
