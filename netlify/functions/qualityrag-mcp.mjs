import { createVideoGateway } from "../lib/video-mcp-gateway.mjs";

export default async (request) => {
  const env = {
    QUALITYRAG_VIDEO_MCP_UPSTREAM_URL: Netlify.env.get("QUALITYRAG_VIDEO_MCP_UPSTREAM_URL"),
    QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGIN: Netlify.env.get("QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGIN"),
  };
  return createVideoGateway(env)(request, "/mcp");
};

// This is a proxy to the independently authenticated Python MCP server,
// not a separate unauthenticated video intelligence implementation.
export const config = {
  path: "/mcp",
  rateLimit: { windowSize: 60, windowLimit: 60, aggregateBy: ["ip", "domain"] },
};
