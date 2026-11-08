import http from 'node:http';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {RegistryStore} from './store.js';
import {createPgSignedRegistryStore} from './pg-store.js';
import {loadTrustedPolicyKeys} from './signed.js';
import {createOidcAuthenticator,permissionFor} from './oidc.js';
import {EvidenceLedger} from './evidence-ledger.js';
import {GoogleDriveConnections,safeDriveError} from './google-drive-connections.js';
import {UserDriveIndex} from './user-drive-index.js';
import {parseProtectedDriveServices} from './protected-drive.js';
import {loadProtectedReviewTrust,verifyHumanReviewAttestations,
  humanReviewDecision} from './protected-admission.js';

const MAX_BODY=200_000;
function reply(res,status,data){res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(data));}
function fail(res,error) {
 const code=error.message;
 if(['SELF_APPROVAL_FORBIDDEN','SAME_ACTOR_PROMOTION_FORBIDDEN','SELF_REVIEW_FORBIDDEN',
     'EVIDENCE_SCOPE_FORBIDDEN'].includes(code))return reply(res,403,{error:code});
 if(code==='EVIDENCE_LEDGER_INTEGRITY_FAILURE'||code==='EVIDENCE_LEDGER_CAPACITY_EXCEEDED')
   return reply(res,503,{error:code});
 if(code==='EVIDENCE_REQUEST_CONFLICT')return reply(res,409,{error:code});
 if(code==='PROTECTED_USE_RATE_LIMITED')return reply(res,429,{error:code,permission:'DENIED'});
 if(code==='PROTECTED_USE_REPLAY')return reply(res,409,{error:code,permission:'DENIED'});
 if(code==='PROTECTED_DECISION_REVOKED'||code==='PROTECTED_DECISION_ALREADY_REVOKED')
   return reply(res,409,{error:code,permission:'DENIED'});
 if(code.startsWith('PROTECTED_')&&code!=='PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED'){
   const safe=[
     'PROTECTED_REVIEW_KEYS_NOT_CONFIGURED','PROTECTED_REVIEW_KEYS_REQUIRED',
     'PROTECTED_UNTRUSTED_REVIEW_KEY','PROTECTED_INVALID_REVIEW_SIGNATURE',
     'PROTECTED_INVALID_REVIEW_ENVELOPE','PROTECTED_INVALID_REVIEW_PAYLOAD',
     'PROTECTED_INVALID_REVIEW_CONTEXT','PROTECTED_INVALID_REVIEW_WITNESS',
     'PROTECTED_NONCANONICAL_REVIEW',
     'PROTECTED_REVIEW_SIGNERS_DISAGREE','PROTECTED_REVIEW_EXPIRED',
     'PROTECTED_REVIEW_POLICY_MISMATCH','PROTECTED_REVIEW_OWNER_OR_SCOPE_MISMATCH',
     'PROTECTED_REVIEW_UNKNOWN_REQUIREMENT','PROTECTED_REVIEW_WITNESS_LIMIT',
     'PROTECTED_SOURCE_INDEX_STALE','PROTECTED_SOURCE_COVERAGE_INCOMPLETE',
     'PROTECTED_OWNER_EXCLUDED_SOURCE','PROTECTED_SOURCE_REVISION_CHANGED',
     'PROTECTED_SOURCE_LINE_CHANGED','PROTECTED_SOURCE_ANCHOR_MISSING',
     'PROTECTED_SOURCE_NOT_FOUND','PROTECTED_LIVE_GOOGLE_VERIFICATION_FAILED',
     'PROTECTED_LIVE_SOURCE_REVISION_MISMATCH',
     'PROTECTED_LIVE_EXTRACTED_TEXT_MISMATCH','PROTECTED_OWNER_CONTEXT_CHANGED',
     'PROTECTED_SOURCE_SYNC_IN_PROGRESS','PROTECTED_POLICY_REQUIRES_UNSUPPORTED_PROOF',
     'PROTECTED_ATTESTATION_REPLAY','PROTECTED_REQUEST_REPLAY',
     'PROTECTED_DECISION_RATE_LIMITED','PROTECTED_DECISION_NOT_FOUND',
     'PROTECTED_DECISION_OWNER_FORBIDDEN',
     'PROTECTED_USE_POLICY_CHANGED','PROTECTED_USE_DECISION_NOT_ADMITTED',
     'PROTECTED_USE_SERVICE_UNPROTECTED','PROTECTED_USE_SIGNATURE_RECORD_MISMATCH',
     'PROTECTED_USE_EVIDENCE_CHANGED','PROTECTED_USE_INVALID',
     'PROTECTED_REVOCATION_REASON_INVALID'
   ].includes(code)?code:'PROTECTED_ADMISSION_REJECTED';
   const status=safe==='PROTECTED_DECISION_NOT_FOUND'?404:
     safe==='PROTECTED_DECISION_OWNER_FORBIDDEN'?403:
     safe==='PROTECTED_DECISION_RATE_LIMITED'?429:
     safe==='PROTECTED_ATTESTATION_REPLAY'||safe==='PROTECTED_REQUEST_REPLAY'?409:
     safe==='PROTECTED_REVIEW_KEYS_NOT_CONFIGURED'||safe==='PROTECTED_REVIEW_KEYS_REQUIRED'?503:
     safe.includes('REVIEW')?403:409;
   return reply(res,status,{error:safe,admissionStatus:'BLOCKED'});
 }
 if(code==='PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED')
   return reply(res,403,{error:code,admissionStatus:'BLOCKED',
     explanation:'Protected service rejects unreviewed generic evidence submissions.',
     nextStep:'Review source controls and provenance in the scoped Drive candidate path.'});
 if(code.startsWith('DRIVE_')||code.startsWith('GOOGLE_')){
   const safe=safeDriveError(error);
   const status=['DRIVE_CONNECTION_NOT_FOUND','DRIVE_CONNECT_DISABLED',
       'DRIVE_FOLDER_NOT_FOUND','DRIVE_SOURCE_NOT_FOUND','DRIVE_INDEX_NOT_FOUND'].includes(safe)?404:
     ['DRIVE_STORAGE_INTEGRITY_FAILURE','DRIVE_INDEX_INTEGRITY_FAILURE'].includes(safe)?503:
     ['DRIVE_AUTHORIZATION_REQUIRED','DRIVE_FOLDER_NOT_CONFIGURED',
       'DRIVE_SYNC_IN_PROGRESS','DRIVE_SYNC_INVALIDATED'].includes(safe)?409:
     safe==='DRIVE_CHALLENGE_RATE_LIMITED'?429:
     ['DRIVE_RATE_LIMITED','GOOGLE_DRIVE_UNAVAILABLE'].includes(safe)?502:400;
   return reply(res,status,{error:safe});
 }
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
   enforceSeparation=false,evidenceLedger=null,driveManager=null,driveIndex=null,
   protectedDriveServices=new Set(),protectedReviewTrust=null}={}) {
 if (!authenticate && !token) throw new Error('REGISTRY_TOKEN_REQUIRED');
 if(enforceSeparation && !authenticate)throw new Error('AUTHENTICATED_APPROVAL_REQUIRED');
 if(driveManager&&!authenticate)throw new Error('DRIVE_REQUIRES_OIDC');
 if(driveIndex&&(!driveManager||!authenticate))throw new Error('DRIVE_INDEX_REQUIRES_OIDC');
 if(!(protectedDriveServices instanceof Set)||
    [...protectedDriveServices].some(v=>typeof v!=='string'||
      !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}@[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(v)))
   throw Error('INVALID_PROTECTED_DRIVE_SERVICES');
 if(protectedDriveServices.size>0&&
    (!authenticate||!driveIndex||!driveManager||!evidenceLedger))
   throw Error('PROTECTED_DRIVE_RUNTIME_REQUIREMENTS_UNMET');
 // A protected service cannot silently become unprotected on a restart.
 // File-backed activation records are locally hash-chained, not externally anchored.
 const configured=new Set(protectedDriveServices);
 for(const previous of evidenceLedger?.protectedScopes?.()||[]){
   if(!configured.has(previous))throw Error('PROTECTED_DRIVE_CONFIGURATION_DOWNGRADE');
 }
 for(const scope of configured){
   const [serviceId,environment]=scope.split('@');
   evidenceLedger.recordProtectionActivation(serviceId,environment);
 }
 protectedDriveServices=configured;
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
  // The OAuth callback has no bearer token; one-time state binds to the OIDC
  // subject from the authenticated start request, never to a shared Drive user.
  if(req.method==='GET'&&url.pathname==='/v1/drives/google/callback'){
    if(!driveManager)return reply(res,404,{error:'DRIVE_CONNECT_DISABLED'});
    let success=false;
    try{
      const completed=await driveManager.callback({
        state:url.searchParams.get('state'),
        code:url.searchParams.get('code'),
        error:url.searchParams.get('error')
      });
      if(driveIndex)driveIndex.clear(completed.subject);
      success=true;
    }catch{}
    const target=driveManager.studioOrigin+'/?drive='+(success?'connected':'authorization-failed');
    res.writeHead(303,{'Location':target,'Cache-Control':'no-store',
      'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'});
    return res.end();
  }
  const provided=req.headers.authorization;
  let actor='registry-token';
  let evidenceServices=null;
  let actorRoles=null;
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
   actorRoles=identity.roles;
  }else if(provided!== 'Bearer '+token)return reply(res,401,{error:'UNAUTHORIZED'});
  try {
   if(url.pathname.startsWith('/v1/drives/google/')){
     if(!authenticate||!driveManager)return reply(res,404,{error:'DRIVE_CONNECT_DISABLED'});
     if(req.method==='GET'&&url.pathname==='/v1/drives/google/status')
       return reply(res,200,{...driveManager.status(actor),indexEnabled:!!driveIndex,
         index:driveIndex?driveIndex.status(actor,driveManager.status(actor)):null});
     if(req.method==='POST'&&url.pathname==='/v1/drives/google/start')
       return reply(res,200,driveManager.start(actor));
     if(req.method==='GET'&&url.pathname==='/v1/drives/google/folders')
       return reply(res,200,await driveManager.folders(actor,
         url.searchParams.get('parentId')||'root',url.searchParams.get('pageToken')));
     if(req.method==='POST'&&url.pathname==='/v1/drives/google/folder'){
       const b=await body(req);
       if(!b||typeof b!=='object'||Array.isArray(b)||
          Object.keys(b).length!==1||!Object.hasOwn(b,'folderId'))throw Error('INVALID_DRIVE_FOLDER_ID');
       const before=driveManager.status(actor);
       const updated=await driveManager.selectFolder(actor,b.folderId);
       if(driveIndex&&before.folderId!==updated.folderId)driveIndex.clear(actor);
       return reply(res,200,{...updated,indexEnabled:!!driveIndex,
         index:driveIndex?driveIndex.status(actor,updated):null});
     }
     if(req.method==='GET'&&url.pathname==='/v1/drives/google/files')
       return reply(res,200,await driveManager.selectedFiles(actor));
     if(req.method==='GET'&&url.pathname==='/v1/drives/google/index'){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       return reply(res,200,driveIndex.status(actor,driveManager.status(actor)));
     }
     if(req.method==='GET'&&url.pathname==='/v1/drives/google/visibility'){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       return reply(res,200,driveIndex.visibility(actor,driveManager.status(actor)));
     }
     if(req.method==='POST'&&url.pathname==='/v1/drives/google/source-control'){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       return reply(res,200,driveIndex.controlSource(actor,driveManager.status(actor),await body(req)));
     }
     if(req.method==='GET'&&url.pathname==='/v1/drives/google/governed-requirements'){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       if(!actorRoles?.has('evidence.reader'))return reply(res,403,{error:'FORBIDDEN'});
       const serviceId=url.searchParams.get('serviceId'),environment=url.searchParams.get('environment');
       if(!serviceId||!environment||
          !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(serviceId)||
          !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(environment))
         throw Error('INVALID_DRIVE_GATE_REQUEST');
       if(!evidenceServices?.has(serviceId+'@'+environment))
         return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
       const bound=await store.resolve(serviceId,environment);
       return reply(res,200,{schema:'qualityrag.drive-governed-requirements/v1',
         policy:{id:bound.policy.id,version:bound.policy.version,sha256:bound.sha256},
         requirements:bound.policy.requirements.map(r=>({id:r.id})),
         admissionStatus:'NOT_EVALUATED',sourceProvenance:'NOT_VERIFIED'});
     }
     if(req.method==='POST'&&['/v1/drives/google/governed-check',
       '/v1/drives/google/record-check'].includes(url.pathname)){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       // Preview needs Drive + evidence reading; a durable challenge also needs
       // explicit reviewer authority and an enabled evidence ledger.
       if(!actorRoles?.has('evidence.reader'))return reply(res,403,{error:'FORBIDDEN'});
       const record=url.pathname==='/v1/drives/google/record-check';
       if(record&&!actorRoles?.has('evidence.reviewer'))
         return reply(res,403,{error:'REVIEWER_ROLE_REQUIRED'});
       if(record&&!evidenceLedger)
         return reply(res,404,{error:'EVIDENCE_TELEMETRY_DISABLED'});
       const input=await body(req);
       if(!input||typeof input!=='object'||Array.isArray(input)||
          Object.keys(input).length!==3||
          !['serviceId','environment','candidates'].every(k=>Object.hasOwn(input,k))||
          typeof input.serviceId!=='string'||typeof input.environment!=='string'||
          !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(input.serviceId)||
          !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(input.environment))
         throw Error('INVALID_DRIVE_GATE_REQUEST');
       if(!evidenceServices?.has(input.serviceId+'@'+input.environment))
         return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
       const governed=await store.resolve(input.serviceId,input.environment);
       const result=driveIndex.checkGovernedCandidates(actor,
         driveManager.status(actor),governed.policy,governed.sha256,input.candidates);
       const receipt=record?evidenceLedger.recordCandidateCheck(
         input.serviceId,input.environment,actor,governed.sha256,result):null;
       return reply(res,200,{...result,telemetry:{
         recorded:!!receipt,receiptId:receipt?.id||null,
         chainHash:receipt?.chainHash||null,externallyAnchored:false,
         scope:'REGISTRY_EVENT_ONLY'
       }});
     }
     if(req.method==='POST'&&url.pathname==='/v1/drives/google/sync'){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       const input=await body(req);
       if(!input||typeof input!=='object'||Array.isArray(input)||
          Object.keys(input).length!==0)throw Error('DRIVE_SYNC_ARGUMENTS_NOT_ALLOWED');
       return reply(res,200,await driveIndex.sync(actor,driveManager));
     }
     if(req.method==='POST'&&url.pathname==='/v1/drives/google/search'){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       const input=await body(req);
       if(!input||typeof input!=='object'||Array.isArray(input)||
          Object.keys(input).length!==1||typeof input.query!=='string')
         throw Error('INVALID_DRIVE_SEARCH_QUERY');
       return reply(res,200,driveIndex.search(actor,driveManager.status(actor),input.query));
     }
     if(req.method==='POST'&&url.pathname==='/v1/drives/google/clear-index'){
       if(!driveIndex)return reply(res,404,{error:'DRIVE_INDEX_DISABLED'});
       return reply(res,200,driveIndex.clear(actor));
     }
     if(req.method==='POST'&&url.pathname==='/v1/drives/google/disconnect'){
       if(driveIndex)driveIndex.clear(actor);
       return reply(res,200,await driveManager.disconnect(actor));
     }
     return reply(res,404,{error:'NOT_FOUND'});
   }
   // The evidence ledger is explicitly opt-in; live monitoring is not inferred.
   const parts=url.pathname.split('/').filter(Boolean);
   if(req.method==='POST'&&url.pathname==='/v1/evidence/protected-admit'){
     if(!authenticate||!evidenceLedger||!driveIndex||!driveManager||
        !protectedReviewTrust)
       return reply(res,404,{error:'PROTECTED_ADMISSION_DISABLED'});
     if(!actorRoles?.has('drive.reader'))return reply(res,403,{error:'FORBIDDEN'});
     const input=await body(req);
     if(!input||typeof input!=='object'||Array.isArray(input)||
       Object.keys(input).length!==6||
       !['serviceId','environment','requestId','traceId','custody','meaning']
         .every(k=>Object.hasOwn(input,k)))
       throw Error('INVALID_PROTECTED_ADMISSION_REQUEST');
     const {serviceId,environment,requestId,traceId,custody,meaning}=input;
     if(![serviceId,environment,requestId,traceId].every(v=>
       typeof v==='string'&&
       /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(v)))
       throw Error('INVALID_PROTECTED_ADMISSION_REQUEST');
     if(!evidenceServices?.has(serviceId+'@'+environment))
       return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
     if(!protectedDriveServices.has(serviceId+'@'+environment))
       return reply(res,403,{error:'PROTECTED_ADMISSION_SCOPE_NOT_PROTECTED'});
     const policy=await store.resolve(serviceId,environment);
     const conn=driveManager.status(actor);
     if(!conn?.connected||!conn.folderId||conn.folderId==='root')
       throw Error('PROTECTED_OWNER_CONTEXT_CHANGED');
     const verified=verifyHumanReviewAttestations(custody,meaning,
       protectedReviewTrust,{
         serviceId,environment,policySha256:policy.sha256,
         subject:actor,folderId:conn.folderId
       });
     // Refuse policies requiring document-age or multi-origin proof the
     // current Google text-index bridge cannot establish independently.
     const preview=humanReviewDecision(policy.policy,policy.sha256,
       verified.payload.witnesses,new Date().toISOString());
     const live=await driveIndex.verifyLiveApprovedWitnesses(
       actor,driveManager,verified.payload.witnesses);
     // File-backed registry binding can change; re-check after Google I/O.
     const current=store.resolve(serviceId,environment);
     if(current.sha256!==policy.sha256)
       throw Error('PROTECTED_REVIEW_POLICY_MISMATCH');
     const decision=humanReviewDecision(current.policy,current.sha256,
       verified.payload.witnesses,live.checkedAt);
     const receipt=evidenceLedger.recordProtectedDecision({
       serviceId,environment,actor,policy:current.policy,
       policySha256:current.sha256,requestId,traceId,
       custody,meaning,verified,result:decision.result,
       evidence:decision.evidence,live
     });
     return reply(res,decision.result.verdict==='ADMIT'?201:200,{
       ...receipt,admissionStatus:decision.result.verdict==='ADMIT'?
         'ADMITTED_AS_HUMAN_REVIEWED_ASSERTION':'NOT_ADMITTED',
       result:decision.result,meaningVerifiedByMachine:false,
       originalPublisherAuthenticated:false,
       independentOriginProven:false
     });
   }
   if(req.method==='GET'&&
     /^\/v1\/evidence\/protected-decisions\/[0-9a-f-]{36}\/export$/.test(url.pathname)){
     if(!evidenceLedger)return reply(res,404,{error:'EVIDENCE_TELEMETRY_DISABLED'});
     if(!actorRoles?.has('drive.reader'))return reply(res,403,{error:'FORBIDDEN'});
     const id=url.pathname.split('/')[4];
     const receipt=evidenceLedger.exportProtectedDecision(id,actor);
     if(!evidenceServices?.has(receipt.serviceId+'@'+receipt.environment))
       return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
     return reply(res,200,receipt);
   }
   if(req.method==='POST'&&
     url.pathname.startsWith('/v1/evidence/protected-decisions/')&&
     url.pathname.endsWith('/revoke')&&
     url.pathname.split('/').length===6&&
     /^[0-9a-f-]{36}$/.test(url.pathname.split('/')[4])){
     if(!authenticate||!evidenceLedger)
       return reply(res,404,{error:'PROTECTED_REVOCATION_DISABLED'});
     // Evidence-review rights alone are insufficient; this is a *source
     // owner's* explicit withdrawal, not a generic policy reviewer action.
     if(!actorRoles?.has('drive.manager'))
       return reply(res,403,{error:'FORBIDDEN'});
     const row=evidenceLedger.protectedDecisionForOwner(
       url.pathname.split('/')[4],actor);
     if(!evidenceServices?.has(row.serviceId+'@'+row.environment))
       return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
     const input=await body(req);
     if(!input||typeof input!=='object'||Array.isArray(input)||
        Object.keys(input).length!==1||
        !Object.hasOwn(input,'reason'))
       throw Error('PROTECTED_REVOCATION_REASON_INVALID');
     return reply(res,200,evidenceLedger.revokeProtectedDecision(
       row.id,actor,input.reason));
   }
   if(req.method==='GET'&&
     url.pathname.startsWith('/v1/evidence/protected-decisions/')&&
     url.pathname.endsWith('/status')&&
     url.pathname.split('/').length===6&&
     /^[0-9a-f-]{36}$/.test(url.pathname.split('/')[4])){
     if(!authenticate||!evidenceLedger)
       return reply(res,404,{error:'PROTECTED_DECISION_NOT_FOUND'});
     if(!actorRoles?.has('drive.reader'))
       return reply(res,403,{error:'FORBIDDEN'});
     const row=evidenceLedger.protectedDecisionForOwner(
       url.pathname.split('/')[4],actor);
     if(!evidenceServices?.has(row.serviceId+'@'+row.environment))
       return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
     const revoked=evidenceLedger.protectedDecisionRevocation(row.id);
     return reply(res,200,{
       schema:'qualityrag.protected-decision-status/v1',
       decisionId:row.id,recordedVerdict:row.result.verdict,
       revoked:!!revoked,
       revokedAt:revoked?.at||null,reason:revoked?.reason||null,
       useCheckRequired:true,
       currentUseAuthorized:false,
       note:'Only a successful fresh use-check can permit a particular request; historical admission is never a standing authorization.'
     });
   }
   // The local delivery gateway holds the complete answer until the exact
   // same last-mile checks succeed. Unlike /use-check, it necessarily receives
   // plaintext: deploy it within the customer's own trusted boundary.
   const protectedDecisionRoute=url.pathname.split('/');
   const decisionAction=protectedDecisionRoute[5];
   if(req.method==='POST'&&protectedDecisionRoute.length===6&&
     protectedDecisionRoute[1]==='v1'&&
     protectedDecisionRoute[2]==='evidence'&&
     protectedDecisionRoute[3]==='protected-decisions'&&
     /^[0-9a-f-]{36}$/.test(protectedDecisionRoute[4]||'')&&
     ['use-check','deliver'].includes(decisionAction)){
     if(!authenticate||!evidenceLedger||!driveIndex||!driveManager||
        !protectedReviewTrust)
       return reply(res,404,{error:'PROTECTED_USE_NOT_CONFIGURED'});
     if(!actorRoles?.has('drive.reader'))
       return reply(res,403,{error:'FORBIDDEN'});
     const decisionId=protectedDecisionRoute[4];
     const input=await body(req);
     const gateway=decisionAction==='deliver';
     const keys=gateway?['requestId','answer']:['requestId','answerSha256'];
     if(!input||typeof input!=='object'||Array.isArray(input)||
        Object.keys(input).length!==2||
        !keys.every(k=>Object.hasOwn(input,k))||
        typeof input.requestId!=='string'||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(input.requestId)||
        (gateway?(typeof input.answer!=='string'||
          !input.answer.trim()||Buffer.byteLength(input.answer,'utf8')>16384||
          /[\\u0000]/.test(input.answer)):
          (typeof input.answerSha256!=='string'||
          !/^[0-9a-f]{64}$/.test(input.answerSha256))))
       throw Error('PROTECTED_USE_INVALID');
     const answerSha256=gateway?
       createHash('sha256').update(input.answer,'utf8').digest('hex'):
       input.answerSha256;
     const row=evidenceLedger.protectedDecisionForOwner(decisionId,actor);
     if(evidenceLedger.protectedDecisionRevocation(row.id))
       throw Error('PROTECTED_DECISION_REVOKED');
     if(!evidenceServices?.has(row.serviceId+'@'+row.environment))
       return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
     if(!protectedDriveServices.has(row.serviceId+'@'+row.environment))
       throw Error('PROTECTED_USE_SERVICE_UNPROTECTED');
     if(row.result?.verdict!=='ADMIT')
       throw Error('PROTECTED_USE_DECISION_NOT_ADMITTED');
     const current=await store.resolve(row.serviceId,row.environment);
     if(current.sha256!==row.policySha256)
       throw Error('PROTECTED_USE_POLICY_CHANGED');
     const connection=driveManager.status(actor);
     if(!connection?.connected||!connection.folderId||connection.folderId==='root')
       throw Error('PROTECTED_OWNER_CONTEXT_CHANGED');
     const verified=verifyHumanReviewAttestations(
       row.signedCustody,row.signedMeaning,protectedReviewTrust,{
         serviceId:row.serviceId,environment:row.environment,
         policySha256:current.sha256,subject:actor,
         folderId:connection.folderId
       });
     if(verified.signedPayloadSha256!==row.signedPayloadSha256)
       throw Error('PROTECTED_USE_SIGNATURE_RECORD_MISMATCH');
     const live=await driveIndex.verifyLiveApprovedWitnesses(
       actor,driveManager,verified.payload.witnesses);
     const refreshed=await store.resolve(row.serviceId,row.environment);
     if(refreshed.sha256!==current.sha256)
       throw Error('PROTECTED_USE_POLICY_CHANGED');
     const replay=humanReviewDecision(
       refreshed.policy,refreshed.sha256,verified.payload.witnesses,
       live.checkedAt);
     if(replay.result.verdict!=='ADMIT'||
        JSON.stringify(replay.result)!==JSON.stringify(row.result))
       throw Error('PROTECTED_USE_EVIDENCE_CHANGED');
     // Final ledger append also checks decision-level revocations and request
     // replay synchronously; no async work can interleave before output.
     const permit=evidenceLedger.recordProtectedUse({
       decision:row,actor,requestId:input.requestId,
       answerSha256,checkedAt:live.checkedAt,
       mode:gateway?'SERVER_BUFFERED_RELEASE':'DIGEST_ONLY_CLIENT_RELEASE'
     });
     if(!gateway)return reply(res,200,permit);
     return reply(res,200,{
       schema:'qualityrag.protected-answer-delivery/v1',
       answer:input.answer,
       receipt:permit,
       delivery:'BUFFERED_SINGLE_RESPONSE',
       answerSemanticsVerified:false,
       globalEnforcement:false,
       externallyAnchored:false
     });
   }
   if(req.method==='GET'&&url.pathname==='/v1/evidence/enforcement'){
     if(!evidenceLedger)return reply(res,404,{error:'EVIDENCE_TELEMETRY_DISABLED'});
     const serviceId=url.searchParams.get('serviceId');
     const environment=url.searchParams.get('environment');
     if(!serviceId||!environment||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(serviceId)||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(environment))
       throw Error('INVALID_ENFORCEMENT_QUERY');
     if(authenticate&&!evidenceServices?.has(serviceId+'@'+environment))
       return reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});
     const bound=await store.resolve(serviceId,environment);
     const isProtected=protectedDriveServices.has(serviceId+'@'+environment);
     const status=evidenceLedger.list(serviceId,environment);
     return reply(res,200,{
       schema:'qualityrag.drive-protection/v1',
       serviceId,environment,
       policy:{id:bound.policy.id,version:bound.policy.version,sha256:bound.sha256},
       protected:isProtected,
       mode:isProtected?'BLOCK_UNATTESTED_GENERIC_EVIDENCE':'LEGACY_METADATA_GATE',
       genericEvidenceIngress:isProtected?'BLOCKED':'ALLOWED',
       sourceAdmission:isProtected&&protectedReviewTrust?
         'TWO_TRUSTED_HUMAN_SIGNATURES_AND_LIVE_BYTES':
         'NOT_ENABLED',
       independentSourceVerification:isProtected&&protectedReviewTrust?
         'CUSTODIAN_ATTESTED_NOT_EXTERNAL_PUBLISHER_PROOF':
         'NOT_IMPLEMENTED',
       globalApplicationEnforcement:false,
       guardTelemetry:status.guardTelemetry
     });
   }
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
       if(protectedDriveServices.has(input.serviceId+'@'+input.environment)){
         // Every attempt is rejected at ingress; no caller's metadata can
         // bypass the owner's Drive exclusion by submitting a synthetic origin.
         // Log only actor hash, scope, policy digest and fixed reason.
         evidenceLedger.recordBlockedIngress(input.serviceId,input.environment,actor,bound.sha256);
         throw Error('PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED');
       }
       return reply(res,201,evidenceLedger.ingest(input,bound.policy,bound.sha256,actor));
     }
     if(parts.length>=4&&parts.length<=5&&
       /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(parts[3])){
       const entry=evidenceLedger.snapshot(parts[3]);
       authorize(entry.serviceId,entry.environment);
       if(req.method==='GET'&&parts.length===4)return reply(res,200,entry);
       if(req.method==='GET'&&parts[4]==='export')
         return reply(res,200,evidenceLedger.exportReplay(parts[3]));
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
 const driveSettings=[
   process.env.QUALITYRAG_DRIVE_FILE,process.env.QUALITYRAG_DRIVE_ENCRYPTION_KEY,
   process.env.QUALITYRAG_GOOGLE_OAUTH_CLIENT_ID,process.env.QUALITYRAG_GOOGLE_OAUTH_CLIENT_SECRET,
   process.env.QUALITYRAG_GOOGLE_REDIRECT_URI,process.env.QUALITYRAG_STUDIO_ORIGIN
 ];
 if(driveSettings.some(Boolean)&&!driveSettings.every(Boolean))
   throw Error('DRIVE_CONFIGURATION_INCOMPLETE');
 if(driveSettings.every(Boolean)&&(authMode!=='oidc'||backend!=='file'))
   throw Error('DRIVE_REQUIRES_OIDC_SINGLE_INSTANCE_FILE_MODE');
 const driveManager=driveSettings.every(Boolean)?new GoogleDriveConnections({
   file:process.env.QUALITYRAG_DRIVE_FILE,
   encryptionKey:process.env.QUALITYRAG_DRIVE_ENCRYPTION_KEY,
   clientId:process.env.QUALITYRAG_GOOGLE_OAUTH_CLIENT_ID,
   clientSecret:process.env.QUALITYRAG_GOOGLE_OAUTH_CLIENT_SECRET,
   redirectUri:process.env.QUALITYRAG_GOOGLE_REDIRECT_URI,
   studioOrigin:process.env.QUALITYRAG_STUDIO_ORIGIN
 }):null;
 if(process.env.QUALITYRAG_DRIVE_INDEX_DIR && !driveManager)
   throw Error('DRIVE_INDEX_REQUIRES_GOOGLE_CONNECTIONS');
 const driveIndex=driveManager&&process.env.QUALITYRAG_DRIVE_INDEX_DIR?
   new UserDriveIndex({dir:process.env.QUALITYRAG_DRIVE_INDEX_DIR,
     encryptionKey:process.env.QUALITYRAG_DRIVE_ENCRYPTION_KEY}):null;
 const protectedDriveServices=parseProtectedDriveServices(
   process.env.QUALITYRAG_PROTECTED_DRIVE_SERVICES||'');
 const protectedReviewTrust=process.env.QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE?
   loadProtectedReviewTrust(process.env.QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE):null;
 if(protectedDriveServices.size>0&&(!driveIndex||!evidenceLedger||authMode!=='oidc'))
   throw Error('PROTECTED_DRIVE_RUNTIME_REQUIREMENTS_UNMET');
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
    {trustedPolicyKeys:keys,authenticate:oidc,enforceSeparation:!!oidc,evidenceLedger,
     driveManager,driveIndex,protectedDriveServices,protectedReviewTrust}));
  const host=process.env.QUALITYRAG_BIND_HOST||'127.0.0.1';
  server.listen(Number(process.env.PORT||5055),host,
    ()=>console.log('QualityRag registry listening on '+host+':'+server.address().port));
 }catch(error){
  console.error('QualityRag startup blocked:',error.message);
  if(store.close)await store.close();
  process.exitCode=1;
 }
}
