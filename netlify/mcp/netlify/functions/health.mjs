// Readiness must never claim the policy engine is connected without credentials.
// This public diagnostic discloses no tokens, hostnames or source catalog.
export default async () => {
  const configured = Boolean(
    Netlify.env.get("QUALITYRAG_MCP_ACCESS_TOKEN") &&
    Netlify.env.get("QUALITYRAG_API_ENDPOINT") &&
    Netlify.env.get("QUALITYRAG_API_TOKEN_JSON")
  );
  return Response.json({
    service: "qualityrag-mcp",
    status: configured ? "gateway_configured_not_end_to_end_verified" : "unconfigured",
    transport: "streamable-http",
    backend_verified: false,
  }, { status: configured ? 200 : 503, headers: {"cache-control":"no-store"} });
};
export const config = { path: "/health" };
