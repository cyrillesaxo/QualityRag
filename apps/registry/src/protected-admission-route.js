import {verifyHumanReviewAttestations,humanReviewDecision} from './protected-admission.js';

const ID=/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
function send(res,status,data){
 res.writeHead(status,{'content-type':'application/json; charset=utf-8',
  'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(data));
}
const safeCodes=new Set(['INVALID_PROTECTED_ADMISSION_REQUEST','PROTECTED_REVIEW_POLICY_MISMATCH',
 'PROTECTED_OWNER_CONTEXT_CHANGED','PROTECTED_REVIEW_EXPIRED',
 'PROTECTED_REVIEW_OWNER_OR_SCOPE_MISMATCH','PROTECTED_REVIEW_SIGNERS_DISAGREE',
 'PROTECTED_INVALID_REVIEW_SIGNATURE','PROTECTED_POLICY_REQUIRES_UNSUPPORTED_PROOF',
 'PROTECTED_SOURCE_COVERAGE_INCOMPLETE','PROTECTED_SOURCE_INDEX_STALE',
 'PROTECTED_OWNER_EXCLUDED_SOURCE','PROTECTED_SOURCE_REVISION_CHANGED',
 'PROTECTED_LIVE_SOURCE_REVISION_MISMATCH','PROTECTED_LIVE_GOOGLE_VERIFICATION_FAILED',
 'PROTECTED_SOURCE_NOT_FOUND','PROTECTED_ATTESTATION_REPLAY','PROTECTED_REQUEST_REPLAY']);
export async function handleProtectedAdmission(req,res,{pathname,authenticate,actor,identity,
 store,evidenceLedger,driveManager,driveIndex,protectedReviewTrust,protectedDriveServices,parseBody}){
 if(pathname!=='/v1/evidence/protected-admit')return false;
 if(req.method!=='POST'){send(res,404,{error:'NOT_FOUND'});return true;}
 if(!authenticate||!evidenceLedger||!driveManager||!driveIndex||
    !protectedReviewTrust||!(protectedDriveServices instanceof Set)){
  send(res,404,{error:'PROTECTED_ADMISSION_DISABLED'});return true;
 }
 if(!identity?.roles?.has('drive.reader')||!identity?.roles?.has('evidence.ingest')){
  send(res,403,{error:'FORBIDDEN'});return true;
 }
 try{
  const input=await parseBody(req);
  if(!input||typeof input!=='object'||Array.isArray(input)||
   Object.keys(input).length!==6||
   !['serviceId','environment','requestId','traceId','custody','meaning'].every(k=>
    Object.hasOwn(input,k)))throw Error('INVALID_PROTECTED_ADMISSION_REQUEST');
  const {serviceId,environment,requestId,traceId,custody,meaning}=input;
  if(![serviceId,environment,requestId,traceId].every(x=>typeof x==='string'&&ID.test(x)))
   throw Error('INVALID_PROTECTED_ADMISSION_REQUEST');
  const scope=serviceId+'@'+environment;
  if(!(identity.evidenceServices instanceof Set)||!identity.evidenceServices.has(scope)){
   send(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});return true;
  }
  if(!protectedDriveServices.has(scope)){
   send(res,403,{error:'PROTECTED_ADMISSION_SCOPE_NOT_PROTECTED'});return true;
  }
  const policy=await store.resolve(serviceId,environment);
  const connection=(await driveManager.status(actor));
  if(!connection?.connected||!connection.folderId||connection.folderId==='root')
   throw Error('PROTECTED_OWNER_CONTEXT_CHANGED');
  const verified=verifyHumanReviewAttestations(custody,meaning,protectedReviewTrust,{
    serviceId,environment,policySha256:policy.sha256,
    subject:actor,folderId:connection.folderId
  });
  // Reject unsupported policy claims BEFORE initiating remote Google reads.
  humanReviewDecision(policy.policy,policy.sha256,verified.payload.witnesses,new Date().toISOString());
  const live=await driveIndex.verifyLiveApprovedWitnesses(actor,driveManager,verified.payload.witnesses);
  // Re-resolve asynchronously; no admission if policy or owner scope changed during I/O.
  const current=await store.resolve(serviceId,environment);
  const latest=(await driveManager.status(actor));
  if(current.sha256!==policy.sha256||!latest.connected||
     latest.folderId!==connection.folderId||latest.email!==connection.email)
    throw Error('PROTECTED_OWNER_CONTEXT_CHANGED');
  const decision=humanReviewDecision(current.policy,current.sha256,
    verified.payload.witnesses,live.checkedAt);
  const receipt=evidenceLedger.recordProtectedDecision({
    serviceId,environment,actor,policy:current.policy,
    policySha256:current.sha256,requestId,traceId,custody,meaning,
    verified,result:decision.result,evidence:decision.evidence,live
  });
  send(res,decision.result.verdict==='ADMIT'?201:200,{
    ...receipt,admissionStatus:decision.result.verdict==='ADMIT'?
      'ADMITTED_AS_HUMAN_REVIEWED_ASSERTION':'NOT_ADMITTED',
    result:decision.result,meaningVerifiedByMachine:false,
    originalPublisherAuthenticated:false,independentOriginProven:false
  });
 }catch(error){
  // No source text, tokens, signatures or Google-provider details in error response.
  const reason=safeCodes.has(error?.message)?error.message:'PROTECTED_ADMISSION_FAILED';
  send(res,reason==='PROTECTED_REVIEW_EXPIRED'||reason==='PROTECTED_OWNER_CONTEXT_CHANGED'||
   reason==='PROTECTED_SOURCE_INDEX_STALE'?409:400,{error:reason});
 }
 return true;
}
