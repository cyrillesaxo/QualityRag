import {verifyHumanReviewAttestations,humanReviewDecision} from './protected-admission.js';
// Historical decision dependency drift. This is a metadata check only;
// it never reads Google source bytes or grants a release.
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ROUTE=/^\/v1\/evidence\/protected-decisions\/([0-9a-f-]{36})\/dependency-status$/i;
function reply(res,status,payload){
 res.writeHead(status,{'content-type':'application/json; charset=utf-8',
   'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(payload));
}
export async function handleProtectedDependencyStatus(req,res,{
 pathname,actor,identity,authenticate,evidenceLedger,store,driveManager,
 driveIndex,protectedReviewTrust
}){
 const m=pathname.match(ROUTE);
 if(!m)return false;
 if(req.method!=='GET'||!UUID.test(m[1])){
   reply(res,404,{error:'NOT_FOUND'});return true;
 }
 if(!authenticate||!evidenceLedger||!store||!driveManager){
   reply(res,404,{error:'PROTECTED_DEPENDENCY_STATUS_DISABLED'});return true;
 }
 if(!identity?.roles?.has('evidence.reader')||
    !identity?.roles?.has('drive.reader')){
   reply(res,403,{error:'FORBIDDEN'});return true;
 }
 try{
   const decision=evidenceLedger.protectedDecisionForOwner(m[1],actor);
   const scope=decision.serviceId+'@'+decision.environment;
   if(!identity.evidenceServices?.has(scope)){
     reply(res,404,{error:'PROTECTED_DECISION_NOT_FOUND'});return true;
   }
   const revoked=Boolean(evidenceLedger.protectedDecisionRevocation(decision.id));
   let policyState='UNKNOWN';
   try{
     const current=await store.resolve(decision.serviceId,decision.environment);
     if(typeof current?.sha256==='string'&&/^[a-f0-9]{64}$/.test(current.sha256))
       policyState=current.sha256===decision.policySha256?'UNCHANGED':'CHANGED';
   }catch{}
   let driveState='UNKNOWN';
   try{
     const drive=driveManager.status(actor);
     if(!drive?.connected||!drive.folderId||drive.folderId==='root')
       driveState='DISCONNECTED';
     else {
       const signedFolder=decision.signedCustody?.payload?.observations?.folder_id;
       if(typeof signedFolder==='string'&&signedFolder)
         driveState=drive.folderId===signedFolder?'BOUND':'FOLDER_CHANGED';
     }
   }catch{}
   // Bounded, last-mile live recheck uses the SAME owner-specific source verifier
   // as protected grounded delivery. Never record another protected use.
   let liveSourceState='UNKNOWN',liveCheckedAt=null;
   if(!revoked&&policyState==='UNCHANGED'&&driveState==='BOUND'&&
      driveIndex&&protectedReviewTrust){
     try{
       const activePolicy=await store.resolve(decision.serviceId,decision.environment);
       const ownerBefore=driveManager.status(actor);
       const signed=verifyHumanReviewAttestations(
         decision.signedCustody,decision.signedMeaning,protectedReviewTrust,{
           serviceId:decision.serviceId,environment:decision.environment,
           policySha256:activePolicy.sha256,subject:actor,folderId:ownerBefore.folderId
         });
       if(signed.signedPayloadSha256!==decision.signedPayloadSha256)
         throw Error('PROTECTED_USE_SIGNATURE_RECORD_MISMATCH');
       const live=await driveIndex.verifyLiveApprovedWitnesses(
         actor,driveManager,signed.payload.witnesses,{
           includeWitnessLines:true,includeConstraintScan:true,includeRelationshipScan:true
         });
       const policyAfter=await store.resolve(decision.serviceId,decision.environment);
       const ownerAfter=driveManager.status(actor);
       if(policyAfter.sha256!==activePolicy.sha256||
          ownerBefore.email!==ownerAfter.email||
          ownerBefore.folderId!==ownerAfter.folderId||!ownerAfter.connected)
         throw Error('PROTECTED_OWNER_CONTEXT_CHANGED');
       const evaluation=humanReviewDecision(policyAfter.policy,policyAfter.sha256,
         signed.payload.witnesses,live.checkedAt);
       if(evaluation.result.verdict!=='ADMIT'||
          JSON.stringify(evaluation.result)!==JSON.stringify(decision.result))
         throw Error('PROTECTED_USE_EVIDENCE_CHANGED');
       if(live.constraintScan?.candidateCount!==0||
          live.constraintScan?.candidatesTruncated!==false||
          live.relationshipScan?.candidateCount!==0||
          live.relationshipScan?.candidatesTruncated!==false)
         throw Error('PROTECTED_REVIEW_CONFLICTING_CONSTRAINTS');
       // A signed-witness match does not cover newly added or deleted
       // files in the owner-selected folder. Reuse the existing encrypted
       // index baseline for a complete bounded folder drift check.
       const folder=typeof driveIndex.inspectSelectedFolderDrift==='function'
         ?await driveIndex.inspectSelectedFolderDrift(actor,driveManager)
         :{state:'UNKNOWN'};
       if(folder.state==='CHANGED')
         throw Error('PROTECTED_SELECTED_FOLDER_DRIFT');
       if(folder.state==='MATCHED_AT_CHECK_TIME'){
         liveSourceState='MATCHED_AT_CHECK_TIME';
         liveCheckedAt=folder.checkedAt;
       }
     }catch(error){
       const confirmedChange=new Set([
         'PROTECTED_SOURCE_REVISION_CHANGED',
         'PROTECTED_SELECTED_FOLDER_DRIFT',
         'PROTECTED_SOURCE_NOT_FOUND',
         'PROTECTED_SOURCE_ANCHOR_MISSING',
         'PROTECTED_LIVE_SOURCE_REVISION_MISMATCH',
         'PROTECTED_LIVE_EXTRACTED_TEXT_MISMATCH',
         'PROTECTED_SOURCE_LINE_CHANGED',
         'PROTECTED_OWNER_EXCLUDED_SOURCE',
         'PROTECTED_USE_SIGNATURE_RECORD_MISMATCH',
         'PROTECTED_USE_EVIDENCE_CHANGED',
         'PROTECTED_REVIEW_CONFLICTING_CONSTRAINTS'
       ]);
       liveSourceState=confirmedChange.has(error?.message)?'CHANGED':'UNKNOWN';
     }
   }
   const stale=liveSourceState==='CHANGED'||revoked||policyState==='CHANGED'||
     driveState==='DISCONNECTED'||driveState==='FOLDER_CHANGED';
   reply(res,200,{
     schema:'qualityrag.protected-dependency-status/v1',
     decisionId:decision.id,serviceId:decision.serviceId,
     environment:decision.environment,
     recordedPolicySha256:decision.policySha256,
     revoked,policyState,driveState,
     dependencyState:stale?'STALE':'UNKNOWN',
     liveSourceState,liveCheckedAt,
     sourceBytesRevalidated:liveSourceState==='MATCHED_AT_CHECK_TIME',
     reviewerKeyValidityRevalidated:false,
     permissionRevalidatedForUse:false,
     releasePermitted:false
   });
 }catch{
   reply(res,404,{error:'PROTECTED_DECISION_NOT_FOUND'});
 }
 return true;
}
