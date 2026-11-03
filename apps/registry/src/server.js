import http from 'node:http';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {RegistryStore} from './store.js';
import {createPgSignedRegistryStore} from './pg-store.js';
import {loadTrustedPolicyKeys} from './signed.js';
import {createOidcAuthenticator,permissionFor} from './oidc.js';

const MAX_BODY=200_000;
function reply(res,status,data){res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(data));}
function fail(res,error) {
 const code=error.message;
 if(code==='SELF_APPROVAL_FORBIDDEN'||code==='SAME_ACTOR_PROMOTION_FORBIDDEN')return reply(res,403,{error:code});
 return reply(res,code==='NOT_FOUND'||code==='UNKNOWN_SERVICE'||code==='UNBOUND_SERVICE'?404:
   code==='VERSION_EXISTS'||code==='NOT_DRAFT'||code==='SIGNED_SEQUENCE_EXISTS'||code==='SIGNED_SEQUENCE_ROLLBACK'||code==='SIGNED_NOT_STAGED'||code==='SIGNED_NOT_APPROVED'?409:400,{error:code});
}
async function body(req) {
 let txt='';
 for await (const chunk of req) {
  txt+=chunk;
  if (txt.length>MAX_BODY) throw new Error('BODY_TOO_LARGE');
 }
 try {return JSON.parse(txt)}catch{throw new Error('INVALID_JSON')}
}
export function createHandler(store,token,{trustedPolicyKeys=new Map(),authenticate=null,enforceSeparation=false}={}) {
 if (!authenticate && !token) throw new Error('REGISTRY_TOKEN_REQUIRED');
 if(enforceSeparation && !authenticate)throw new Error('AUTHENTICATED_APPROVAL_REQUIRED');
 return async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if (url.pathname==='/health') return reply(res,200,{ok:true,service:'qualityrag-registry'});
  const provided=req.headers.authorization;
  let actor='registry-token';
  if(authenticate){
   if(typeof provided!=='string'||!provided.startsWith('Bearer '))return reply(res,401,{error:'UNAUTHORIZED'});
   let identity=null;
   try {identity=await authenticate(provided.slice(7));}catch{return reply(res,401,{error:'UNAUTHORIZED'})}
   if(!identity||typeof identity.subject!=='string'||!identity.subject.trim()||
      !(identity.roles instanceof Set))return reply(res,401,{error:'UNAUTHORIZED'});
   const permission=permissionFor(req.method,url.pathname);
   if(!permission)return reply(res,404,{error:'NOT_FOUND'});
   if(!identity.roles.has(permission))return reply(res,403,{error:'FORBIDDEN'});
   actor=identity.subject;
  }else if(provided!== 'Bearer '+token)return reply(res,401,{error:'UNAUTHORIZED'});
  try {
   if(req.method==='GET'&&url.pathname==='/v1/state'){
    return reply(res,200,store.state?await store.state():{services:Object.values(store.data.services),policies:Object.values(store.data.policies),bindings:Object.values(store.data.bindings),signedPromotions:Object.values(store.data.signedPromotions).map(({bundle,...summary})=>summary),signedBindings:Object.values(store.data.signedBindings)});
   }
   if(req.method==='POST'&&url.pathname==='/v1/services') return reply(res,201,await store.register(await body(req),actor));
   if(req.method==='POST'&&url.pathname==='/v1/policies/drafts') return reply(res,201,await store.draft(await body(req),actor));
   const approve=url.pathname.match(/^\/v1\/policies\/([^/]+)\/([^/]+)\/approve$/);
   if(req.method==='POST'&&approve) return reply(res,200,await store.approve(decodeURIComponent(approve[1]),decodeURIComponent(approve[2]),actor,{enforceSeparation}));
   if(req.method==='POST'&&url.pathname==='/v1/bindings'){
    const b=await body(req);
    return reply(res,200,await store.bind(b.serviceId,b.environment,b.policyId,b.version,actor));
   }
   if(req.method==='POST'&&url.pathname==='/v1/signed/promotions'){
    return reply(res,201,await store.stageSigned(await body(req),actor,trustedPolicyKeys));
   }
   const signedAction=url.pathname.match(/^\/v1\/signed\/promotions\/([^/]+)\/([^/]+)\/([0-9]+)\/(approve|publish)$/);
   if(req.method==='POST'&&signedAction){
    const service=decodeURIComponent(signedAction[1]),environment=decodeURIComponent(signedAction[2]);
    const sequence=Number(signedAction[3]);
    if(!Number.isSafeInteger(sequence)||sequence<=0)throw new Error('INVALID_SIGNED_SEQUENCE');
    const result=signedAction[4]==='approve'
       ?await store.approveSigned(service,environment,sequence,actor,trustedPolicyKeys,{enforceSeparation})
       :await store.publishSigned(service,environment,sequence,actor,trustedPolicyKeys,{enforceSeparation});
    return reply(res,200,result);
   }
   const signedResolve=url.pathname.match(/^\/v1\/signed\/resolve\/([^/]+)\/([^/]+)$/);
   if(req.method==='GET'&&signedResolve){
     const result=await store.resolveSigned(decodeURIComponent(signedResolve[1]),
          decodeURIComponent(signedResolve[2]),trustedPolicyKeys);
     res.setHeader('etag','"'+result.signedPolicy.signature+'"');
     return reply(res,200,result);
   }
   const resolve=url.pathname.match(/^\/v1\/resolve\/([^/]+)\/([^/]+)$/);
   if(req.method==='GET'&&resolve){
    const result=await store.resolve(decodeURIComponent(resolve[1]),decodeURIComponent(resolve[2]));
    res.setHeader('etag','"'+result.sha256+'"');
    return reply(res,200,result);
   }
   return reply(res,404,{error:'NOT_FOUND'});
  }catch(error){return fail(res,error)}
 };
}
const own=fileURLToPath(import.meta.url);
if(process.argv[1]&&path.resolve(process.argv[1])===own){
 const store=process.env.QUALITYRAG_REGISTRY_BACKEND==='postgres'
   ?createPgSignedRegistryStore(process.env.DATABASE_URL)
   :new RegistryStore(process.env.QUALITYRAG_REGISTRY_FILE||'./.qualityrag/registry.json');
 if(process.env.QUALITYRAG_REGISTRY_BACKEND && !['postgres','file'].includes(process.env.QUALITYRAG_REGISTRY_BACKEND))
   throw new Error('UNSUPPORTED_REGISTRY_BACKEND');
 const keys=process.env.QUALITYRAG_POLICY_KEYS_FILE?loadTrustedPolicyKeys(process.env.QUALITYRAG_POLICY_KEYS_FILE):new Map();
 const oidc=process.env.QUALITYRAG_AUTH_MODE==='oidc'
  ? createOidcAuthenticator({issuer:process.env.QUALITYRAG_OIDC_ISSUER,
      audience:process.env.QUALITYRAG_OIDC_AUDIENCE,jwksUri:process.env.QUALITYRAG_OIDC_JWKS_URI,
      roleClaim:process.env.QUALITYRAG_OIDC_ROLE_CLAIM||'roles'}) : null;
 if(process.env.QUALITYRAG_AUTH_MODE && !['oidc','local'].includes(process.env.QUALITYRAG_AUTH_MODE))
  throw new Error('UNSUPPORTED_AUTH_MODE');
 const server=http.createServer(createHandler(store,process.env.QUALITYRAG_REGISTRY_TOKEN,
   {trustedPolicyKeys:keys,authenticate:oidc,enforceSeparation:!!oidc}));
 server.listen(Number(process.env.PORT||5055),'127.0.0.1',()=>console.log('QualityRag local registry listening on '+server.address().port));
}
