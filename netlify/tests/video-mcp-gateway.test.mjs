import test from "node:test";
import assert from "node:assert/strict";
import { createVideoGateway, validateGatewayConfig } from "../lib/video-mcp-gateway.mjs";

const env = { QUALITYRAG_VIDEO_MCP_UPSTREAM_URL: "https://private-service.example/mcp" };
const request = (headers = {}, method = "POST", path = "/mcp") =>
  new Request("https://quality-rag.netlify.app" + path, {
    method, headers, ...(method === "POST" ? {body: JSON.stringify({
      jsonrpc: "2.0", method: "tools/list", id: 1,
    })} : {}),
  });

test("gateway cannot start without secure preconfigured upstream", () => {
  for (const value of ["http://example.com/mcp", "http://localhost:8039/mcp",
    "https://127.0.0.1/mcp", "https://private-service.example/mcp?token=x",
    "https://username:password@example.com/mcp", "https://example.com/other"]) {
    assert.throws(() => validateGatewayConfig({
      QUALITYRAG_VIDEO_MCP_UPSTREAM_URL: value,
    }));
  }
});

test("does not call upstream without bearer or with disallowed Origin", async () => {
  let calls = 0;
  const fetcher = async () => {calls++; throw Error("never");};
  const g = createVideoGateway(env, fetcher);
  assert.equal((await g(request(), "/mcp")).status, 401);
  assert.equal((await g(request({
    authorization: "Bearer " + "a".repeat(32), origin: "https://evil.example",
  }), "/mcp")).status, 403);
  assert.equal(calls, 0);
});

test("relays valid MCP JSON and bearer only to configured HTTPS upstream", async () => {
  let observed;
  const fetcher = async (url, init) => {
    observed = {url, init};
    return new Response(JSON.stringify({jsonrpc:"2.0", id:1, result:{tools:[]}}), {
      status:200,headers:{"content-type":"application/json","set-cookie":"unsafe=x"},
    });
  };
  const token = "Bearer " + "a".repeat(48);
  const result = await createVideoGateway(env, fetcher)(
    request({authorization:token,accept:"application/json, text/event-stream"}), "/mcp");
  assert.equal(observed.url, env.QUALITYRAG_VIDEO_MCP_UPSTREAM_URL);
  assert.equal(observed.init.headers.get("authorization"), token);
  assert.equal(observed.init.redirect,"manual");
  assert.equal(result.status,200);
  assert.equal(result.headers.get("set-cookie"),null);
  assert.equal(result.headers.get("cache-control"),"no-store");
});

test("public metadata route does not send caller bearer credentials", async () => {
  let header;
  const g=createVideoGateway(env,async (_,init)=>{
    header=init.headers.get("authorization");
    return new Response(JSON.stringify({resource:"https://quality-rag.netlify.app/mcp",
      authorization_servers:["https://issuer.example"]}),
      {headers:{"content-type":"application/json"}});
  });
  const res=await g(request({authorization:"Bearer " + "x".repeat(32)},
    "GET", "/.well-known/oauth-protected-resource/mcp"),
    "/.well-known/oauth-protected-resource/mcp");
  assert.equal(res.status,200);
  assert.equal(header,null);
});

test("rejects redirects, oversized responses and unknown route", async () => {
  const authorizedRequest=()=>request({authorization:"Bearer " + "a".repeat(48)});
  const moved=createVideoGateway(env,async()=>new Response(null,{
    status:302,headers:{location:"https://other.example/"}}));
  assert.equal((await moved(authorizedRequest(),"/mcp")).status,502);
  const large=createVideoGateway(env,async()=>new Response("x".repeat(1048577)));
  assert.equal((await large(authorizedRequest(),"/mcp")).status,502);
  assert.equal((await moved(authorizedRequest(),"/unsupported")).status,404);
});

test("fails closed with missing upstream", async () => {
  const g=createVideoGateway({},async()=>{ throw Error("not invoked"); });
  assert.equal((await g(request({authorization:"Bearer "+"x".repeat(40)}),"/mcp")).status,503);
});
