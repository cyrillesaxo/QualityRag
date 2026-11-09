// Stateless Streamable HTTP MCP adapter for the existing QualityRAG governance API.
// The bearer token is forwarded only to the configured HTTPS backend, never logged.
const version = "2025-06-18";
const tools = [
  ["garden_query","Search source-anchored Semantic Garden branches and evidence",["text","evidence_status","depends_on","open_challenge","active","lineage_of","since","limit"]],
  ["garden_suggestions","Read current review suggestions",[]],
  ["policy_test","Evaluate a PackSpec against retrieved evidence",["pack","documents","retrieved","question","as_of"]],
  ["policy_advise","Read governance advisory findings",["pack","test","benchmark","far_limit"]],
  ["policy_replay","Compare base and branch policy outcomes",["base","branch","cases","as_of"]],
  ["functional_siblings","Evaluate candidate mechanisms against functional contracts",["function","contracts","candidates","as_of"]],
];
const required={policy_test:["pack","documents","retrieved"],policy_replay:["base","branch","cases"],functional_siblings:["function","contracts","candidates"]};
const fieldTypes={pack:"object",documents:"array",retrieved:"array",test:"object",benchmark:"object",base:"object",branch:"object",cases:"array",contracts:"object",candidates:"array",open_challenge:"boolean",active:"boolean",since:"integer",limit:"integer",far_limit:"number"};
const catalog=tools.map(([name,description,properties])=>({name,description,inputSchema:{type:"object",properties:Object.fromEntries(properties.map(k=>[k,{type:fieldTypes[k]||"string"}])),required:required[name]||[],additionalProperties:false},annotations:{readOnlyHint:true}}));
const headers={"content-type":"application/json","cache-control":"no-store","access-control-allow-headers":"authorization,content-type,mcp-protocol-version,mcp-session-id","access-control-allow-methods":"GET,POST,OPTIONS"};
const reply=(payload,status=200)=>new Response(JSON.stringify(payload),{status,headers});
const err=(id,code,message)=>({jsonrpc:"2.0",id,error:{code,message}});
const MAX_CLIENT_TOKEN_AGE_MS = 60 * 24 * 60 * 60 * 1000;
const utcTimestamp = (value) => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)) return NaN;
  const time = Date.parse(value);
  return Number.isFinite(time) && new Date(time).toISOString().replace(".000Z", "Z") === value ? time : NaN;
};
const clientTokenIsCurrent = (now = Date.now()) => {
  const issued = utcTimestamp(process.env.QUALITYRAG_MCP_TOKEN_ISSUED_AT);
  const expires = utcTimestamp(process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT);
  return Number.isFinite(issued) && Number.isFinite(expires) &&
    expires > issued && expires - issued <= MAX_CLIENT_TOKEN_AGE_MS &&
    now >= issued && now < expires;
};
export default async function handler(request){
 if(request.method==="OPTIONS")return new Response(null,{status:204,headers});
 if(request.method==="GET")return reply({error:"Use POST for JSON-RPC requests"},405);
 if(request.method!=="POST")return reply({error:"Method not allowed"},405);
 const auth=request.headers.get("authorization")||"";
 const configured=process.env.QUALITYRAG_MCP_ACCESS_TOKEN;
 if(!configured || !clientTokenIsCurrent() || auth!==`Bearer ${configured}`)return reply({error:"Unauthorized"},401);
 let msg;try{msg=await request.json()}catch{return reply(err(null,-32700,"Invalid JSON"),400)}
 if(!msg || msg.jsonrpc!=="2.0" || typeof msg.method!=="string")return reply(err(msg?.id??null,-32600,"Invalid JSON-RPC"),400);
 if(msg.method==="notifications/initialized")return new Response(null,{status:202,headers});
 if(msg.method==="initialize")return reply({jsonrpc:"2.0",id:msg.id,result:{protocolVersion:version,capabilities:{tools:{listChanged:false}},serverInfo:{name:"qualityrag-remote",version:"0.1.0"}}});
 if(msg.method==="ping")return reply({jsonrpc:"2.0",id:msg.id,result:{}});
 if(msg.method==="tools/list")return reply({jsonrpc:"2.0",id:msg.id,result:{tools:catalog}});
 if(msg.method!=="tools/call")return reply(err(msg.id,-32601,"Method not found"),404);
 const name=msg.params?.name,args=msg.params?.arguments||{};
 if(!args || typeof args!=="object" || Array.isArray(args))return reply(err(msg.id,-32602,"Arguments must be an object"),400);
 const spec=catalog.find(t=>t.name===name)?.inputSchema;
 if(spec){for(const k of spec.required){if(!(k in args))return reply(err(msg.id,-32602,"Missing required argument: "+k),400)}
 for(const [k,v] of Object.entries(args)){if(!spec.properties[k])return reply(err(msg.id,-32602,"Unsupported argument: "+k),400);
 const type=spec.properties[k].type;const valid=type==="array"?Array.isArray(v):type==="object"?(v!==null&&typeof v==="object"&&!Array.isArray(v)):type==="integer"?Number.isInteger(v):typeof v===type;
 if(!valid)return reply(err(msg.id,-32602,"Invalid type for "+k),400)}}
 if(!tools.some(t=>t[0]===name))return reply(err(msg.id,-32602,"Unknown tool"),400);
 const endpoint=process.env.QUALITYRAG_API_ENDPOINT;
 const upstreamToken=process.env.QUALITYRAG_API_TOKEN_JSON;
 if(!endpoint || !upstreamToken)return reply({jsonrpc:"2.0",id:msg.id,result:{isError:true,content:[{type:"text",text:"QualityRAG backend is not configured"}]}});
 let target;try{target=new URL(endpoint);if(target.protocol!=="https:")throw Error("HTTPS required")}catch{return reply(err(msg.id,-32603,"Invalid backend configuration"),500)}
 // Existing runtime uses a single authenticated operation API. Do not synthesize policy results.
 try{
  const route=({garden_query:"gardener/query",garden_suggestions:"gardener/proposals",policy_test:"policy/test",policy_advise:"policy/advise",policy_replay:"policy/replay",functional_siblings:"policy/siblings"})[name];
  const upstreamUrl=new URL(target.origin+target.pathname.replace(/\/$/,"")+"/api/"+route);
  const encodedToken=Buffer.from(JSON.stringify(JSON.parse(upstreamToken))).toString("base64url");
  const upstream=await fetch(upstreamUrl,{method:"POST",headers:{"authorization":`Bearer ${encodedToken}`,"content-type":"application/json"},body:JSON.stringify(args),signal:AbortSignal.timeout(25000)});
  const body=await upstream.text();
  if(!upstream.ok)return reply({jsonrpc:"2.0",id:msg.id,result:{isError:true,content:[{type:"text",text:`Backend returned HTTP ${upstream.status}`}]}});
  return reply({jsonrpc:"2.0",id:msg.id,result:{content:[{type:"text",text:body}]}});
 }catch{return reply({jsonrpc:"2.0",id:msg.id,result:{isError:true,content:[{type:"text",text:"Backend unavailable"}]}})}
}
export const config={path:"/mcp"};
