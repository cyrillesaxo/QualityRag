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
const catalog=tools.map(([name,description,properties])=>({name,description,inputSchema:{type:"object",properties:Object.fromEntries(properties.map(k=>[k,{type:"string",description:"JSON-compatible argument; send structured values for objects and arrays"}])),required:required[name]||[],additionalProperties:false}}));
const headers={"content-type":"application/json","cache-control":"no-store","access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type,mcp-protocol-version,mcp-session-id","access-control-allow-methods":"GET,POST,OPTIONS"};
const reply=(payload,status=200)=>new Response(JSON.stringify(payload),{status,headers});
const err=(id,code,message)=>({jsonrpc:"2.0",id,error:{code,message}});
export default async function handler(request){
 if(request.method==="OPTIONS")return new Response(null,{status:204,headers});
 if(request.method==="GET")return reply({error:"Use POST for JSON-RPC requests"},405);
 if(request.method!=="POST")return reply({error:"Method not allowed"},405);
 const auth=request.headers.get("authorization")||"";
 const configured=process.env.QUALITYRAG_MCP_ACCESS_TOKEN;
 if(!configured || auth!==`Bearer ${configured}`)return reply({error:"Unauthorized"},401);
 let msg;try{msg=await request.json()}catch{return reply(err(null,-32700,"Invalid JSON"),400)}
 if(!msg || msg.jsonrpc!=="2.0" || typeof msg.method!=="string")return reply(err(msg?.id??null,-32600,"Invalid JSON-RPC"),400);
 if(msg.method==="notifications/initialized")return new Response(null,{status:202,headers});
 if(msg.method==="initialize")return reply({jsonrpc:"2.0",id:msg.id,result:{protocolVersion:version,capabilities:{tools:{listChanged:false}},serverInfo:{name:"qualityrag-remote",version:"0.1.0"}}});
 if(msg.method==="ping")return reply({jsonrpc:"2.0",id:msg.id,result:{}});
 if(msg.method==="tools/list")return reply({jsonrpc:"2.0",id:msg.id,result:{tools:catalog}});
 if(msg.method!=="tools/call")return reply(err(msg.id,-32601,"Method not found"),404);
 const name=msg.params?.name,args=msg.params?.arguments||{};
 if(!tools.some(t=>t[0]===name))return reply(err(msg.id,-32602,"Unknown tool"),400);
 const endpoint=process.env.QUALITYRAG_API_ENDPOINT;
 const upstreamToken=process.env.QUALITYRAG_API_TOKEN;
 if(!endpoint || !upstreamToken)return reply({jsonrpc:"2.0",id:msg.id,result:{isError:true,content:[{type:"text",text:"QualityRAG backend is not configured"}]}});
 let target;try{target=new URL(endpoint);if(target.protocol!=="https:")throw Error("HTTPS required")}catch{return reply(err(msg.id,-32603,"Invalid backend configuration"),500)}
 // Existing runtime uses a single authenticated operation API. Do not synthesize policy results.
 try{
  const upstream=await fetch(target,{method:"POST",headers:{"authorization":`Bearer ${upstreamToken}`,"content-type":"application/json"},body:JSON.stringify({operation:name.replaceAll("_","."),...args}),signal:AbortSignal.timeout(25000)});
  const body=await upstream.text();
  if(!upstream.ok)return reply({jsonrpc:"2.0",id:msg.id,result:{isError:true,content:[{type:"text",text:`Backend returned HTTP ${upstream.status}`}]}});
  return reply({jsonrpc:"2.0",id:msg.id,result:{content:[{type:"text",text:body}]}});
 }catch{return reply({jsonrpc:"2.0",id:msg.id,result:{isError:true,content:[{type:"text",text:"Backend unavailable"}]}})}
}
export const config={path:"/mcp"};
