import test from 'node:test';
import assert from 'node:assert/strict';
import handler from '../netlify/functions/mcp.mjs';
const original={...process.env};
const request=(method,payload,token='test-secret')=>new Request('https://example.test/mcp',{method,headers:{authorization:'Bearer '+token,'content-type':'application/json'},body:JSON.stringify(payload)});
const rpc=(id,method,params)=>({jsonrpc:'2.0',id,method,params});
test.beforeEach(()=>{process.env.QUALITYRAG_MCP_ACCESS_TOKEN='test-secret';process.env.QUALITYRAG_MCP_TOKEN_ISSUED_AT=new Date(Date.now()-1000).toISOString().replace(/\.\d{3}Z$/, 'Z');process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT=new Date(Date.now()+60*24*60*60*1000-1000).toISOString().replace(/\.\d{3}Z$/, 'Z');delete process.env.QUALITYRAG_API_ENDPOINT;delete process.env.QUALITYRAG_API_TOKEN_JSON});
test.after(()=>{process.env=original});
test('unauthorized callers cannot initialize or enumerate tools',async()=>{assert.equal((await handler(request('POST',rpc(1,'initialize'),'wrong'))).status,401)});
test('initialize negotiates MCP protocol',async()=>{const r=await handler(request('POST',rpc(1,'initialize')));assert.equal(r.status,200);assert.equal((await r.json()).result.protocolVersion,'2025-06-18')});
test('tool schemas preserve structured argument types',async()=>{const r=await handler(request('POST',rpc(2,'tools/list')));const tools=(await r.json()).result.tools;assert.equal(tools.length,6);assert.equal(tools.find(t=>t.name==='policy_test').inputSchema.properties.documents.type,'array');assert.equal(tools.find(t=>t.name==='garden_query').inputSchema.properties.limit.type,'integer')});
test('reject invalid tool arguments before backend call',async()=>{const r=await handler(request('POST',rpc(3,'tools/call',{name:'policy_test',arguments:{pack:{},documents:'bad',retrieved:[]}})));assert.equal(r.status,400);assert.equal((await r.json()).error.code,-32602)});
test('never invent verdict when backend not configured',async()=>{const r=await handler(request('POST',rpc(4,'tools/call',{name:'garden_query',arguments:{}})));const out=(await r.json()).result;assert.equal(out.isError,true)});
test('no wildcard cross-origin access',async()=>{const r=await handler(request('POST',rpc(5,'ping')));assert.equal(r.headers.get('access-control-allow-origin'),null)});

test('expired access token is refused, including initialization',async()=>{
 process.env.QUALITYRAG_MCP_TOKEN_ISSUED_AT='2026-01-01T00:00:00Z';
 process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT='2026-03-02T00:00:00Z';
 assert.equal((await handler(request('POST',rpc(8,'initialize')))).status,401);
});
test('missing or invalid token expiry fails closed',async()=>{
 delete process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT;
 assert.equal((await handler(request('POST',rpc(9,'tools/list')))).status,401);
 process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT='not-a-date';
 assert.equal((await handler(request('POST',rpc(10,'tools/list')))).status,401);
});
test('token lifetime exceeding 60 days is refused',async()=>{
 process.env.QUALITYRAG_MCP_TOKEN_ISSUED_AT='2026-11-01T00:00:00Z';
 process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT='2027-02-01T00:00:00Z';
 assert.equal((await handler(request('POST',rpc(11,'initialize')))).status,401);
});
test('future-issued token is refused',async()=>{
 process.env.QUALITYRAG_MCP_TOKEN_ISSUED_AT='2099-01-01T00:00:00Z';
 process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT='2099-02-01T00:00:00Z';
 assert.equal((await handler(request('POST',rpc(12,'initialize')))).status,401);
});
