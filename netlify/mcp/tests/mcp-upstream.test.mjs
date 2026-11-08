import test from "node:test";
import assert from "node:assert/strict";
import handler from "../netlify/functions/mcp.mjs";

const original={...process.env};
const fetchOriginal=globalThis.fetch;
const token={kid:"test-key",payload:{sub:"test-operator"},signature:"test-signature"};
const rpc=(id,name,args)=>({jsonrpc:"2.0",id,method:"tools/call",params:{name,arguments:args}});
const make=(body,headers={})=>new Request("https://qualityrag-mcp.netlify.app/mcp",{
  method:"POST",
  headers:{"authorization":"Bearer test-secret","content-type":"application/json",...headers},
  body:typeof body==="string"?body:JSON.stringify(body),
});
test.beforeEach(()=>{
  process.env.QUALITYRAG_MCP_ACCESS_TOKEN="test-secret";
  process.env.QUALITYRAG_API_ENDPOINT="https://governance.example/host";
  process.env.QUALITYRAG_API_TOKEN_JSON=JSON.stringify(token);
});
test.afterEach(()=>{globalThis.fetch=fetchOriginal});
test.after(()=>{process.env=original});

test("real backend JSON receipt returned, never synthetic verdict",async()=>{
  let calls=0;
  globalThis.fetch=async(url,opts)=>{
    calls++;
    assert.equal(url.href,"https://governance.example/host/api/policy/test");
    assert.equal(opts.redirect,"error");
    assert.equal(opts.method,"POST");
    assert.equal(opts.headers.authorization,
      "Bearer "+Buffer.from(JSON.stringify(token)).toString("base64url"));
    assert.deepEqual(JSON.parse(opts.body),{pack:{},documents:[],retrieved:[]});
    return Response.json({verdict:"INCONCLUSIVE",reason:"test-only upstream stub"});
  };
  const r=await handler(make(rpc(9,"policy_test",{pack:{},documents:[],retrieved:[]})));
  assert.equal(r.status,200);
  const payload=await r.json();
  assert.equal(payload.result.isError,undefined);
  assert.deepEqual(JSON.parse(payload.result.content[0].text),
    {verdict:"INCONCLUSIVE",reason:"test-only upstream stub"});
  assert.equal(calls,1);
});

test("backend errors must remain MCP errors, never confirmations",async()=>{
  globalThis.fetch=async()=>new Response("down",{status:503});
  const r=await handler(make(rpc(10,"garden_query",{})));
  const p=await r.json();
  assert.equal(p.result.isError,true);
  assert.match(p.result.content[0].text,/HTTP 503/);
});

test("html or non-object responses rejected rather than shown as evidence",async()=>{
  for(const response of [new Response("<html>ok</html>"),Response.json(["unexpected"])]) {
    globalThis.fetch=async()=>response;
    const r=await handler(make(rpc(11,"garden_query",{})));
    assert.equal((await r.json()).result.isError,true);
  }
});

test("outbound network never called when backend destination is private",async()=>{
  process.env.QUALITYRAG_API_ENDPOINT="https://127.0.0.1/host";
  globalThis.fetch=async()=>{throw Error("network should not be called")};
  const result=await handler(make(rpc(12,"garden_query",{})));
  assert.equal((await result.json()).result.isError,true);
});

test("requests and cross-site browser origins fail before backend",async()=>{
  let called=false;
  globalThis.fetch=async()=>{called=true;return Response.json({})};
  const cross=await handler(make(rpc(13,"garden_query",{}),{origin:"https://untrusted.example"}));
  assert.equal(cross.status,403);
  const large=await handler(make("x".repeat(65537)));
  assert.equal(large.status,413);
  assert.equal(called,false);
});

test("excessive upstream content is rejected without returning it",async()=>{
  globalThis.fetch=async()=>new Response("x".repeat(262145),{
    status:200,headers:{"content-type":"application/json"},
  });
  const r=await handler(make(rpc(14,"garden_query",{})));
  assert.equal((await r.json()).result.isError,true);
});
