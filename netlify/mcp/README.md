# QualityRAG remote MCP — Netlify adapter

This is an **independent** Netlify site. Do not deploy it over the existing `quality-rag` site, which currently serves PackSpec from another repository.

Deploy with Netlify base directory `netlify/mcp` and publish directory `public`. Set secret environment variables `QUALITYRAG_MCP_ACCESS_TOKEN`, `QUALITYRAG_API_ENDPOINT` (HTTPS), and `QUALITYRAG_API_TOKEN`. Do not commit tokens. The public endpoint is `https://<assigned-site>.netlify.app/mcp` after deployment.

The adapter supports MCP initialize, ping, tools/list and tools/call. **Backend operation routing must be validated against the QualityRAG HTTP API before production**; this is a staging integration, not a verified live tool server. The stdio MCP server in `tools/activation_runtime/mcp_server.py` remains the reference contract. The adapter currently provides a subset of read-only tools; write tools are intentionally excluded pending authorization and audit integration.

Production checklist: verify the exact upstream operation protocol, implement structured input schemas from the Python server, configure OAuth for ChatGPT remote connectors instead of a static token, add CORS origin restrictions, integration tests, rate limits, and connect Neon persistence to the backend. Do not publicly advertise an endpoint until these pass.
