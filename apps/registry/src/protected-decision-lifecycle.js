// Owner-bound protected decision status, signed receipt export and revocation.
// A status request is NOT a new source verification or a release permit.
const DECISION=/^\/v1\/evidence\/protected-decisions\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/(status|export|revoke)$/i;
const REASONS=new Set(['OWNER_WITHDRAWN','REVIEW_DISPUTED','CUSTODY_DISPUTED']);
function send(res,code,data){
 res.writeHead(code,{'content-type':'application/json; charset=utf-8',
  'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(data));
}
export async function handleProtectedDecisionLifecycle(req,res,{
 pathname,actor,identity,authenticate,evidenceLedger,parseBody
}){
 const match=pathname.match(DECISION);
 if(!match)return false;
 const [_,decisionId,action]=match;
 const method=action==='revoke'?'POST':'GET';
 if(req.method!==method){send(res,404,{error:'NOT_FOUND'});return true}
 if(!authenticate||!evidenceLedger){
  send(res,404,{error:'PROTECTED_DECISION_CONTROL_DISABLED'});return true;
 }
 if(typeof actor!=='string'||!actor||!(identity?.roles instanceof Set)){
  send(res,401,{error:'UNAUTHORIZED'});return true;
 }
 if(!identity.roles.has(action==='revoke'?'evidence.reviewer':'evidence.reader')){
  send(res,403,{error:'FORBIDDEN'});return true;
 }
 try{
  // Crucially, the ledger checks the authenticated owner before returning
  // any decision metadata, signature or revocation information.
  const row=evidenceLedger.protectedDecisionForOwner(decisionId,actor);
  const scope=row.serviceId+'@'+row.environment;
  if(!(identity.evidenceServices instanceof Set)||!identity.evidenceServices.has(scope)){
   send(res,404,{error:'PROTECTED_DECISION_NOT_FOUND'});return true;
  }
  if(action==='status'){
   const revocation=evidenceLedger.protectedDecisionRevocation(decisionId);
   send(res,200,{
    schema:'qualityrag.protected-decision-status/v1',
    decisionId:row.id,serviceId:row.serviceId,environment:row.environment,
    status:revocation?'REVOKED':row.result?.verdict==='ADMIT'?'HUMAN_REVIEWED_ADMISSION':'NOT_ADMITTED',
    verdict:row.result?.verdict||'UNKNOWN',
    revokedAt:revocation?.at||null,
    reason:revocation?.reason||null,
    releasePermittedByStatus:false,
    sourceRevalidatedForThisRequest:false,
    humanReviewAuthenticityIndependentlyProven:false,
    externallyAnchored:false
   });return true;
  }
  if(action==='export'){
   // Exact stored signed evidence, explicitly no claim of current source bytes.
   const exportData=evidenceLedger.exportProtectedDecision(decisionId,actor);
   const revocation=evidenceLedger.protectedDecisionRevocation(decisionId);
   send(res,200,{...exportData,
    currentStatus:revocation?'REVOKED':'HISTORICAL_SIGNED_DECISION',
    revokedAt:revocation?.at||null,
    currentSourceVerified:false,releasePermittedByExport:false
   });return true;
  }
  const input=await parseBody(req);
  if(!input||typeof input!=='object'||Array.isArray(input)||
    Object.keys(input).length!==1||!REASONS.has(input.reason)){
   send(res,400,{error:'PROTECTED_REVOCATION_REASON_INVALID'});return true;
  }
  // The append-only ledger rechecks owner and prevents replay before mutation.
  const result=evidenceLedger.revokeProtectedDecision(decisionId,actor,input.reason);
  send(res,200,{...result,releasePermitted:false});
 }catch(error){
  if(error?.message==='PROTECTED_DECISION_ALREADY_REVOKED'){
   send(res,409,{error:'PROTECTED_DECISION_ALREADY_REVOKED'});return true;
  }
  // Uniform unknown-owner response, including damaged/foreign decisions.
  send(res,404,{error:'PROTECTED_DECISION_NOT_FOUND'});
 }
 return true;
}
