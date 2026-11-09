import http from 'node:http';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {RegistryStore} from './store.js';
import {createPgSignedRegistryStore} from './pg-store.js';
import {loadTrustedPolicyKeys} from './signed.js';
import {createOidcAuthenticator,permissionFor} from './oidc.js';
import {handleScopedDriveControl,handleDriveOauthCallback} from './scoped-drive-control.js';

const MAX_BODY=200_000;
function reply(res,status,data){res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(data));}
function fail(res,error) {
 const code=error.message;
 if(code==='SELF_APPROVAL_FORBIDDEN'||code==='SAME_ACTOR_PROMOTION_FORBIDDEN')return reply(res,403,{error:code});
 return reply(res,code==='NOT_FOUND'||code==='UNKNOWN_SERVICE'||code==='UNBOUND_SERVICE'||code==='UNBOUND_CONTRACT'?404:
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
export function createHandler(store,token,{trustedPolicyKeys=new Map(),trustedContractKeys=new Map(),authenticate=null,enforceSeparation=false,
  driveManager=null,driveIndex=null}={}) {
 if (!authenticate && !token) throw new Error('REGISTRY_TOKEN_REQUIRED');
 if(enforceSeparation && !authenticate)throw new Error('AUTHENTICATED_APPROVAL_REQUIRED');
 if((driveManager||driveIndex)&&(!authenticate||!driveManager||!driveIndex))
  throw new Error('DRIVE_REQUIRES_OIDC_AND_INDEX');
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
  if(await handleDriveOauthCallback(req,res,{url,authenticate,driveManager,driveIndex}))return;
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
   if(await handleScopedDriveControl(req,res,{pathname:url.pathname,actor,
      authenticate,driveManager,driveIndex,parseBody:body,url}))return;
   if(req.method==='GET'&&url.pathname==='/v1/state'){
    return reply(res,200,store.state?await store.state():{services:Object.values(store.data.services),policies:Object.values(store.data.policies),bindings:Object.values(store.data.bindings),signedPromotions:Object.values(store.data.signedPromotions).map(({bundle,...summary})=>summary),signedBindings:Object.values(store.data.signedBindings),contractPromotions:Object.values(store.data.contractPromotions).map(({envelope,...summary})=>summary),contractBindings:Object.values(store.data.contractBindings)});
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
   // ---------- Data contracts (ADR-0002): stage signed -> approve -> publish -> resolve ----------
   if(req.method==='POST'&&url.pathname==='/v1/contracts/validate'){
    return reply(res,200,await store.validateContractDraft(await body(req)));
   }
   if(req.method==='POST'&&url.pathname==='/v1/contracts/signed'){
    return reply(res,201,await store.stageContract(await body(req),actor,trustedContractKeys));
   }
   const contractAction=url.pathname.match(/^\/v1\/contracts\/signed\/([^/]+)\/([0-9]+)\/(approve|publish)$/);
   if(req.method==='POST'&&contractAction){
    const id=decodeURIComponent(contractAction[1]),sequence=Number(contractAction[2]);
    if(!Number.isSafeInteger(sequence)||sequence<=0)throw new Error('INVALID_SIGNED_SEQUENCE');
    const result=contractAction[3]==='approve'
      ?await store.approveContract(id,sequence,actor,trustedContractKeys,{enforceSeparation})
      :await store.publishContract(id,sequence,actor,trustedContractKeys,{enforceSeparation});
    return reply(res,200,result);
   }
   const contractResolve=url.pathname.match(/^\/v1\/contracts\/resolve\/([^/]+)$/);
   if(req.method==='GET'&&contractResolve){
    const result=await store.resolveContract(decodeURIComponent(contractResolve[1]),trustedContractKeys);
    res.setHeader('etag','"'+result.signedContract.signature+'"');
    return reply(res,200,result);
   }
   if(req.method==='GET'&&url.pathname==='/v1/contracts/published'){
    return reply(res,200,await store.publishedContracts(url.searchParams.get('tenant'),trustedContractKeys));
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
 if(!['oidc','local'].includes(authMode))throw new Error('UNSUPPORTED_AUTH_MODE');
 // PostgreSQL is not an opt-in weakening of governance: no shared token.
 if(backend==='postgres' && authMode!=='oidc')throw new Error('POSTGRES_REQUIRES_OIDC');
 const store=backend==='postgres'?createPgSignedRegistryStore(process.env.DATABASE_URL):
    new RegistryStore(process.env.QUALITYRAG_REGISTRY_FILE||'./.qualityrag/registry.json');
 const keys=process.env.QUALITYRAG_POLICY_KEYS_FILE?
    loadTrustedPolicyKeys(process.env.QUALITYRAG_POLICY_KEYS_FILE):new Map();
 if(backend==='postgres' && keys.size===0)throw new Error('TRUSTED_POLICY_KEYS_REQUIRED');
 const contractKeys=process.env.QUALITYRAG_CONTRACT_KEYS_FILE?
    loadTrustedPolicyKeys(process.env.QUALITYRAG_CONTRACT_KEYS_FILE):new Map();
 const oidc=authMode==='oidc'
  ?createOidcAuthenticator({issuer:process.env.QUALITYRAG_OIDC_ISSUER,
     audience:process.env.QUALITYRAG_OIDC_AUDIENCE,jwksUri:process.env.QUALITYRAG_OIDC_JWKS_URI,
     roleClaim:process.env.QUALITYRAG_OIDC_ROLE_CLAIM||'roles'}):null;
 try{
  // Require explicit, checksummed migration before serving any requests.
  if(store.readiness)await store.readiness();
  const server=http.createServer(createHandler(store,process.env.QUALITYRAG_REGISTRY_TOKEN,
    {trustedPolicyKeys:keys,trustedContractKeys:contractKeys,authenticate:oidc,enforceSeparation:!!oidc}));
  const host=process.env.QUALITYRAG_BIND_HOST||'127.0.0.1';
  server.listen(Number(process.env.PORT||5055),host,
    ()=>console.log('QualityRag registry listening on '+host+':'+server.address().port));
 }catch(error){
  console.error('QualityRag startup blocked:',error.message);
  if(store.close)await store.close();
  process.exitCode=1;
 }
}
