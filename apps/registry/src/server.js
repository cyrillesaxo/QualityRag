import http from 'node:http';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {RegistryStore} from './store.js';
import {createPgSignedRegistryStore} from './pg-store.js';
import {loadTrustedPolicyKeys} from './signed.js';
import {createOidcAuthenticator,permissionFor} from './oidc.js';
import {EvidenceLedger} from './evidence-ledger.js';

const MAX_BODY=200_000;
function reply(res,status,data){res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(data));}
function fail(res,error) {
 const code=error.message;
 if(['SELF_APPROVAL_FORBIDDEN','SAME_ACTOR_PROMOTION_FORBIDDEN','SELF_REVIEW_FORBIDDEN',
     'EVIDENCE_SCOPE_FORBIDDEN'].includes(code))return reply(res,403,{error:code});
 if(code==='EVIDENCE_LEDGER_INTEGRITY_FAILURE'||code==='EVIDENCE_LEDGER_CAPACITY_EXCEEDED')
   return reply(res,503,{error:code});
 if(code==='EVIDENCE_REQUEST_CONFLICT')return reply(res,409,{error:code});
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
export function createHandler(store,token,{trustedPolicyKeys=new Map(),authenticate=null,
   enforceSeparation=false,evidenceLedger=null}={}) {
 if (!authenticate && !token) throw new Error('REGISTRY_TOKEN_REQUIRED');
 if(enforceSeparation && !authenticate)throw new Error('AUTHENTICATED_APPROVAL_REQUIRED');
 return async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if (url.pathname==='/health') return reply(res,200,{ok:true,service:'qualityrag-registry'});
  if(url.pathname==='/ready'){
   try{
    const status=store.readiness?await store.readiness():{ready:true,backend:'file'};
    return reply(res,200,status);
   }catch{
    return reply(res,503,{ready:false,reason:'REGISTRY_NOT_READY'});
   }
  }
  const provided=req.headers.authorization;
  let actor='registry-token';
  let evidenceServices=null;
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
   evidenceServices=identity.evidenceServices;
  }else if(provided!== 'Bearer '+token)return reply(res,401,{error:'UNAUTHORIZED'});
  try {
   // The evidence ledger is explicitly opt-in; live monitoring is not inferred.
   const parts=url.pathname.split('/').filter(Boolean);
   if(parts[0]==='v1'&&parts[1]==='evidence'&&parts[2]==='evaluations'){
     if(!evidenceLedger)return reply(res,404,{error:'EVIDENCE_TELEMETRY_DISABLED'});
     const authorize=(serviceId,environment)=>{
       if(authenticate&&!evidenceServices?.has(serviceId+'@'+environment))
         throw Error('EVIDENCE_SCOPE_FORBIDDEN');
     };
     if(parts.length===3&&req.method==='GET'){
       const serviceId=url.searchParams.get('serviceId');
       const environment=url.searchParams.get('environment');
       authorize(serviceId,environment);
       return reply(res,200,evidenceLedger.list(serviceId,environment));
     }
     if(parts.length===3&&req.method==='POST'){
       const input=await body(req);
       if(!input||typeof input!=='object')throw Error('INVALID_EVALUATION');
       authorize(input.serviceId,input.environment);
       const bound=await store.resolve(input.serviceId,input.environment);
       return reply(res,201,evidenceLedger.ingest(input,bound.policy,bound.sha256,actor));
     }
     if(parts.length>=4&&parts.length<=5&&
       /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(parts[3])){
       const entry=evidenceLedger.snapshot(parts[3]);
       authorize(entry.serviceId,entry.environment);
       if(req.method==='GET'&&parts.length===4)return reply(res,200,entry);
       if(req.method==='POST'&&parts[4]==='replay')return reply(res,200,evidenceLedger.replay(parts[3]));
       if(req.method==='POST'&&parts[4]==='reviews')
         return reply(res,201,evidenceLedger.review(parts[3],await body(req),actor));
     }
     return reply(res,404,{error:'NOT_FOUND'});
   }
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
 const backend=process.env.QUALITYRAG_REGISTRY_BACKEND||'file';
 const authMode=process.env.QUALITYRAG_AUTH_MODE||'local';
 if(!['file','postgres'].includes(backend))throw new Error('UNSUPPORTED_REGISTRY_BACKEND');
 if(backend!=='file'&&process.env.QUALITYRAG_EVIDENCE_LEDGER_FILE)
   throw new Error('EVIDENCE_LEDGER_FILE_BACKEND_ONLY');
 if(!['oidc','local'].includes(authMode))throw new Error('UNSUPPORTED_AUTH_MODE');
 // PostgreSQL is not an opt-in weakening of governance: no shared token.
 if(backend==='postgres' && authMode!=='oidc')throw new Error('POSTGRES_REQUIRES_OIDC');
 const store=backend==='postgres'?createPgSignedRegistryStore(process.env.DATABASE_URL):
    new RegistryStore(process.env.QUALITYRAG_REGISTRY_FILE||'./.qualityrag/registry.json');
 const evidenceLedger=process.env.QUALITYRAG_EVIDENCE_LEDGER_FILE?
   new EvidenceLedger(process.env.QUALITYRAG_EVIDENCE_LEDGER_FILE):null;
 const keys=process.env.QUALITYRAG_POLICY_KEYS_FILE?
    loadTrustedPolicyKeys(process.env.QUALITYRAG_POLICY_KEYS_FILE):new Map();
 if(backend==='postgres' && keys.size===0)throw new Error('TRUSTED_POLICY_KEYS_REQUIRED');
 const oidc=authMode==='oidc'
  ?createOidcAuthenticator({issuer:process.env.QUALITYRAG_OIDC_ISSUER,
     audience:process.env.QUALITYRAG_OIDC_AUDIENCE,jwksUri:process.env.QUALITYRAG_OIDC_JWKS_URI,
     roleClaim:process.env.QUALITYRAG_OIDC_ROLE_CLAIM||'roles'}):null;
 try{
  // Require explicit, checksummed migration before serving any requests.
  if(store.readiness)await store.readiness();
  const server=http.createServer(createHandler(store,process.env.QUALITYRAG_REGISTRY_TOKEN,
    {trustedPolicyKeys:keys,authenticate:oidc,enforceSeparation:!!oidc,evidenceLedger}));
  const host=process.env.QUALITYRAG_BIND_HOST||'127.0.0.1';
  server.listen(Number(process.env.PORT||5055),host,
    ()=>console.log('QualityRag registry listening on '+host+':'+server.address().port));
 }catch(error){
  console.error('QualityRag startup blocked:',error.message);
  if(store.close)await store.close();
  process.exitCode=1;
 }
}
