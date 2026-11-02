import http from 'node:http';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {RegistryStore} from './store.js';

const MAX_BODY=200_000;
function reply(res,status,data){res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(data));}
function fail(res,error) {
 const code=error.message;
 return reply(res,code==='NOT_FOUND'||code==='UNKNOWN_SERVICE'||code==='UNBOUND_SERVICE'?404:
   code==='VERSION_EXISTS'||code==='NOT_DRAFT'?409:400,{error:code});
}
async function body(req) {
 let txt='';
 for await (const chunk of req) {
  txt+=chunk;
  if (txt.length>MAX_BODY) throw new Error('BODY_TOO_LARGE');
 }
 try {return JSON.parse(txt)}catch{throw new Error('INVALID_JSON')}
}
export function createHandler(store,token) {
 if (!token) throw new Error('REGISTRY_TOKEN_REQUIRED');
 return async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if (url.pathname==='/health') return reply(res,200,{ok:true,service:'qualityrag-registry'});
  const provided=req.headers.authorization;
  if (provided!== 'Bearer '+token) return reply(res,401,{error:'UNAUTHORIZED'});
  const actor='registry-token'; // Single-key local development only; replace with OIDC/RBAC before production.
  try {
   if(req.method==='GET'&&url.pathname==='/v1/state'){
    return reply(res,200,{services:Object.values(store.data.services),policies:Object.values(store.data.policies),bindings:Object.values(store.data.bindings)});
   }
   if(req.method==='POST'&&url.pathname==='/v1/services') return reply(res,201,store.register(await body(req),actor));
   if(req.method==='POST'&&url.pathname==='/v1/policies/drafts') return reply(res,201,store.draft(await body(req),actor));
   const approve=url.pathname.match(/^\/v1\/policies\/([^/]+)\/([^/]+)\/approve$/);
   if(req.method==='POST'&&approve) return reply(res,200,store.approve(decodeURIComponent(approve[1]),decodeURIComponent(approve[2]),actor));
   if(req.method==='POST'&&url.pathname==='/v1/bindings'){
    const b=await body(req);
    return reply(res,200,store.bind(b.serviceId,b.environment,b.policyId,b.version,actor));
   }
   const resolve=url.pathname.match(/^\/v1\/resolve\/([^/]+)\/([^/]+)$/);
   if(req.method==='GET'&&resolve){
    const result=store.resolve(decodeURIComponent(resolve[1]),decodeURIComponent(resolve[2]));
    res.setHeader('etag','"'+result.sha256+'"');
    return reply(res,200,result);
   }
   return reply(res,404,{error:'NOT_FOUND'});
  }catch(error){return fail(res,error)}
 };
}
const own=fileURLToPath(import.meta.url);
if(process.argv[1]&&path.resolve(process.argv[1])===own){
 const store=new RegistryStore(process.env.QUALITYRAG_REGISTRY_FILE||'./.qualityrag/registry.json');
 const server=http.createServer(createHandler(store,process.env.QUALITYRAG_REGISTRY_TOKEN));
 server.listen(Number(process.env.PORT||5055),'127.0.0.1',()=>console.log('QualityRag local registry listening on '+server.address().port));
}
