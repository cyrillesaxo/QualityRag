// Public, credential-free smoke for the QualityRAG governance MCP preview.
// Never send the static MCP token or upstream credentials to CI logs.
const url = process.env.QUALITYRAG_MCP_PREVIEW_URL;
if (!url || !/^https:\/\/deploy-preview-\d+--qualityrag-mcp\.netlify\.app\/$/.test(url))
  throw Error("Expected the explicit Netlify deploy-preview URL");

async function probe(path, init, expected) {
  let last = null;
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const res = await fetch(new URL(path, url), {
        ...init, redirect: "manual", signal: AbortSignal.timeout(10000),
      });
      if (res.status === expected) {
        if (!res.headers.get("content-type")?.includes("application/json"))
          throw Error("Missing JSON response");
        console.log(JSON.stringify({ path, status: res.status,
          result: "GATEWAY_PRESENT_NOT_AUTHORIZED" }));
        return;
      }
      last = `status ${res.status}`;
    } catch (error) {
      last = error.name;
    }
    if (attempt < 5) await new Promise(resolve => setTimeout(resolve, 4000));
  }
  throw Error(`Expected HTTP ${expected} on ${path}, got ${last}`);
}

await probe("/mcp", {
  method: "POST",
  headers: {"content-type":"application/json",
            "accept":"application/json,text/event-stream"},
  body: JSON.stringify({jsonrpc:"2.0",id:1,method:"tools/list"}),
}, 401);
await probe("/health", {method:"GET"}, 503);
