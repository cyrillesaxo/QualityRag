import { createVideoGateway } from "../lib/video-mcp-gateway.mjs";

export default async (request) => {
  const env = {
    QUALITYRAG_VIDEO_MCP_UPSTREAM_URL: Netlify.env.get("QUALITYRAG_VIDEO_MCP_UPSTREAM_URL"),
    QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGIN: Netlify.env.get("QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGIN"),
  };
  const requested = new URL(request.url).pathname;
  return createVideoGateway(env)(request, requested);
};

export const config = {
  path: [
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
  ],
  rateLimit: { windowSize: 60, windowLimit: 120, aggregateBy: ["ip", "domain"] },
};
