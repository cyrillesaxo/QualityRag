/**
 * Netlify-to-QualityRAG Streamable HTTP pass-through.
 *
 * No MCP state, OAuth token validation or video corpus lives at Netlify.
 * A separate trusted Python MCP resource server validates JWTs, source ACLs
 * and source provenance. The upstream URL is operator-controlled only.
 */
const MAX_REQUEST_BYTES = 128 * 1024;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const TIMEOUT_MS = 12000;
const METADATA_PATHS = new Set([
  "/.well-known/oauth-protected-resource",
  "/.well-known/oauth-protected-resource/mcp",
]);
const EXPOSED_HEADERS = new Set([
  "content-type", "www-authenticate", "mcp-session-id",
  "mcp-protocol-version", "retry-after",
]);

function configValue(name, env) {
  return env?.[name] ?? null;
}

export function validateGatewayConfig(env) {
  const upstreamValue = configValue("QUALITYRAG_VIDEO_MCP_UPSTREAM_URL", env);
  if (typeof upstreamValue !== "string" || upstreamValue.length > 512) {
    throw new Error("Missing upstream");
  }
  let upstream;
  try {
    upstream = new URL(upstreamValue);
  } catch {
    throw new Error("Invalid upstream");
  }
  if (upstream.protocol !== "https:" || !upstream.hostname ||
      upstream.username || upstream.password || upstream.search ||
      upstream.hash || upstream.pathname !== "/mcp") {
    throw new Error("Upstream must be a dedicated HTTPS /mcp endpoint");
  }
  // Never let an external request choose the destination. Block loopback
  // and common private literals even in an operator-supplied env var.
  const host = upstream.hostname.toLowerCase();
  if (host === "localhost" || host.endsWith(".localhost") ||
      host === "0.0.0.0" || host === "[::1]" ||
      /^127\./.test(host) || /^10\./.test(host) ||
      /^192\.168\./.test(host) ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
      /^169\.254\./.test(host)) {
    throw new Error("Private upstream is disallowed");
  }
  const allowedOrigin = configValue("QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGIN", env);
  if (allowedOrigin) {
    let parsed;
    try {
      parsed = new URL(allowedOrigin);
    } catch {
      throw new Error("Invalid allowed origin");
    }
    if (parsed.protocol !== "https:" || parsed.pathname !== "/" ||
        parsed.search || parsed.hash || parsed.username || parsed.password ||
        allowedOrigin !== parsed.origin) {
      throw new Error("Allowed Origin must be an exact HTTPS origin");
    }
  }
  return { upstream, allowedOrigin: allowedOrigin ?? null };
}

function sanitized(status, message, extraHeaders = {}) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json",
      "cache-control": "no-store", ...extraHeaders },
  });
}

function targetFor(upstream, route) {
  if (route === "/mcp") return upstream.href;
  if (METADATA_PATHS.has(route)) {
    return new URL(route, upstream.origin).href;
  }
  throw new Error("Route not supported");
}

export function createVideoGateway(env, doFetch = fetch) {
  return async function gateway(request, route) {
    let config;
    try {
      config = validateGatewayConfig(env);
    } catch {
      return sanitized(503, "Video MCP upstream is not configured");
    }
    if (route !== "/mcp" && !METADATA_PATHS.has(route)) {
      return sanitized(404, "Unknown endpoint");
    }
    if (request.method !== (route === "/mcp" ? "POST" : "GET")) {
      return sanitized(405, "Method not allowed",
        { allow: route === "/mcp" ? "POST" : "GET" });
    }
    // Native MCP clients don't require CORS. Browser origins are rejected
    // unless the operator has explicitly configured an exact HTTPS origin.
    const origin = request.headers.get("origin");
    if (origin && origin !== config.allowedOrigin) {
      return sanitized(403, "Origin not allowed");
    }
    const authorization = request.headers.get("authorization");
    if (route === "/mcp" && (!authorization ||
        !/^Bearer [^\s]{10,8192}$/.test(authorization))) {
      return sanitized(401, "Bearer access token required");
    }
    const declared = Number(request.headers.get("content-length"));
    if (route === "/mcp" && Number.isFinite(declared) && declared > MAX_REQUEST_BYTES) {
      return sanitized(413, "MCP request too large");
    }
    let body;
    if (route === "/mcp") {
      body = await request.arrayBuffer();
      if (body.byteLength > MAX_REQUEST_BYTES) {
        return sanitized(413, "MCP request too large");
      }
    }
    const headers = new Headers();
    if (route === "/mcp") {
      headers.set("authorization", authorization);
      headers.set("accept", request.headers.get("accept") ||
        "application/json, text/event-stream");
      headers.set("content-type", "application/json");
      for (const name of ["mcp-session-id", "mcp-protocol-version"]) {
        const value = request.headers.get(name);
        if (value) headers.set(name, value);
      }
    } else {
      headers.set("accept", "application/json");
    }
    let upstreamResponse;
    try {
      upstreamResponse = await doFetch(targetFor(config.upstream, route), {
        method: request.method, headers, body, redirect: "manual",
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch {
      return sanitized(502, "Video MCP upstream unavailable");
    }
    // Never forward Authorization on redirects, or redirect the client
    // to an unrelated site which may receive its bearer credentials.
    if (upstreamResponse.status >= 300 && upstreamResponse.status < 400) {
      return sanitized(502, "Video MCP upstream redirected unexpectedly");
    }
    const indicated = Number(upstreamResponse.headers.get("content-length"));
    if (Number.isFinite(indicated) && indicated > MAX_RESPONSE_BYTES) {
      return sanitized(502, "Video MCP response exceeds gateway limit");
    }
    let result;
    try {
      result = await upstreamResponse.arrayBuffer();
    } catch {
      return sanitized(502, "Video MCP upstream response failed");
    }
    if (result.byteLength > MAX_RESPONSE_BYTES) {
      return sanitized(502, "Video MCP response exceeds gateway limit");
    }
    const responseHeaders = new Headers({ "cache-control": "no-store" });
    for (const name of EXPOSED_HEADERS) {
      const value = upstreamResponse.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    responseHeaders.delete("set-cookie");
    responseHeaders.delete("location");
    return new Response(result, {
      status: upstreamResponse.status,
      headers: responseHeaders,
    });
  };
}
