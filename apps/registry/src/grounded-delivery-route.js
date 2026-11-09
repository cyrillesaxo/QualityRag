// Last-mile extractive answer gateway: never accepts or releases free-form prose.
// Requires current OIDC scope, approved human-signed anchors, unchanged Google
// source bytes, zero known lexical/relationship conflicts and synchronous
// revocation/replay check at ledger append. Not proof of semantic completeness.
import {createHash} from 'node:crypto';
import {verifyHumanReviewAttestations,humanReviewDecision} from './protected-admission.js';
import {buildSourceGroundedAnswer} from './source-grounded-answer.js';
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ID=/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const ROUTE=/^\/v1\/evidence\/protected-decisions\/([0-9a-f-]{36})\/grounded-deliver$/i;
const sha=x=>createHash('sha256').update(x,'utf8').digest('hex');
function reply(res,status,data){
 res.writeHead(status,{'content-type':'application/json; charset=utf-8',
 'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(data));
}
const known=new Set(['PROTECTED_DECISION_REVOKED','PROTECTED_USE_POLICY_CHANGED',
 'PROTECTED_OWNER_CONTEXT_CHANGED','PROTECTED_USE_DECISION_NOT_ADMITTED',
 'PROTECTED_USE_EVIDENCE_CHANGED','PROTECTED_USE_SIGNATURE_RECORD_MISMATCH',
 'PROTECTED_SOURCE_INDEX_STALE','PROTECTED_OWNER_EXCLUDED_SOURCE',
 'PROTECTED_LIVE_GOOGLE_VERIFICATION_FAILED','PROTECTED_LIVE_SOURCE_REVISION_MISMATCH',
 'PROTECTED_GROUNDED_CROSS_SOURCE_RELATION_CONFLICT',
 'PROTECTED_SUFFICIENCY_UNREVIEWED_SIGNAL','PROTECTED_GROUNDED_SUFFICIENCY_CHECK_REQUIRED',
 'PROTECTED_GROUNDED_REVIEW_INCOMPLETE','PROTECTED_USE_REPLAY',
 'PROTECTED_GROUNDED_SOURCE_CHANGED']);
export async function handleGroundedDelivery(req,res,{pathname,identity,actor,
 authenticate,evidenceLedger,driveManager,driveIndex,protectedReviewTrust,
 protectedDriveServices,store,parseBody}){
 const m=pathname.match(ROUTE);
 if(!m)return false;
 if(req.method!=='POST'||!UUID.test(m[1])){reply(res,404,{error:'NOT_FOUND'});return true}
 if(!authenticate||!evidenceLedger||!driveManager||!driveIndex||
   !protectedReviewTrust||!(protectedDriveServices instanceof Set)){
  reply(res,404,{error:'PROTECTED_DELIVERY_DISABLED'});return true;
 }
 if(!identity?.roles?.has('evidence.ingest')||!identity?.roles?.has('drive.reader')){
  reply(res,403,{error:'FORBIDDEN'});return true;
 }
 try{
  const input=await parseBody(req);
  if(!input||typeof input!=='object'||Array.isArray(input)||
    Object.keys(input).length!==1||!ID.test(input.requestId)){
   reply(res,400,{error:'INVALID_PROTECTED_DELIVERY_REQUEST'});return true;
  }
  const decision=evidenceLedger.protectedDecisionForOwner(m[1],actor);
  const scope=decision.serviceId+'@'+decision.environment;
  if(!identity.evidenceServices?.has(scope)||!protectedDriveServices.has(scope)){
   reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});return true;
  }
  if(decision.result?.verdict!=='ADMIT')throw Error('PROTECTED_USE_DECISION_NOT_ADMITTED');
  if(evidenceLedger.protectedDecisionRevocation(decision.id))
   throw Error('PROTECTED_DECISION_REVOKED');
  const policy=await store.resolve(decision.serviceId,decision.environment);
  if(policy.sha256!==decision.policySha256)throw Error('PROTECTED_USE_POLICY_CHANGED');
  const owner=driveManager.status(actor);
  if(!owner?.connected||!owner.folderId||owner.folderId==='root')
   throw Error('PROTECTED_OWNER_CONTEXT_CHANGED');
  const verified=verifyHumanReviewAttestations(
   decision.signedCustody,decision.signedMeaning,protectedReviewTrust,{
    serviceId:decision.serviceId,environment:decision.environment,
    policySha256:policy.sha256,subject:actor,folderId:owner.folderId});
  if(verified.signedPayloadSha256!==decision.signedPayloadSha256)
   throw Error('PROTECTED_USE_SIGNATURE_RECORD_MISMATCH');
  const live=await driveIndex.verifyLiveApprovedWitnesses(
   actor,driveManager,verified.payload.witnesses,{
    includeWitnessLines:true,includeConstraintScan:true,includeRelationshipScan:true});
  const latestPolicy=await store.resolve(decision.serviceId,decision.environment);
  const latestOwner=driveManager.status(actor);
  if(latestPolicy.sha256!==policy.sha256||!latestOwner?.connected||
     latestOwner.email!==owner.email||latestOwner.folderId!==owner.folderId)
   throw Error('PROTECTED_USE_POLICY_CHANGED');
  const replay=humanReviewDecision(latestPolicy.policy,latestPolicy.sha256,
    verified.payload.witnesses,live.checkedAt);
  if(replay.result.verdict!=='ADMIT'||
     JSON.stringify(replay.result)!==JSON.stringify(decision.result))
   throw Error('PROTECTED_USE_EVIDENCE_CHANGED');
  // Signing both contradictory clauses does not make them consistent.
  if(!live.relationshipScan||
     live.relationshipScan.candidateCount!==0||
     live.relationshipScan.candidatesTruncated===true)
   throw Error('PROTECTED_GROUNDED_CROSS_SOURCE_RELATION_CONFLICT');
  if(!live.constraintScan||live.constraintScan.candidateCount!==0||
     live.constraintScan.candidatesTruncated!==false)
   throw Error('PROTECTED_SUFFICIENCY_UNREVIEWED_SIGNAL');
  const extract=buildSourceGroundedAnswer({
    policy:latestPolicy.policy,witnesses:verified.payload.witnesses,
    verifiedLines:live.verifiedLines,constraintScan:live.constraintScan});
  // A synchronous ledger write is the final revocation and replay check.
  const receipt=evidenceLedger.recordProtectedUse({
   decision,actor,requestId:input.requestId,
   answerSha256:sha(extract.answer),checkedAt:live.checkedAt,
   mode:'SOURCE_GROUNDED_EXTRACT'});
  reply(res,200,{...extract,receipt,delivery:'SERVER_GENERATED_EXTRACT_ONLY',
    answerSemanticsVerified:false,globalEnforcement:false,externallyAnchored:false});
 }catch(e){
  const reason=known.has(e?.message)?e.message:'PROTECTED_DELIVERY_DENIED';
  reply(res,409,{error:reason,releasePermitted:false});
 }
 return true;
}
