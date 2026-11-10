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
 pathname,actor,identity,authenticate,evidenceLedger,store,driveManager
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
   const stale=revoked||policyState==='CHANGED'||
     driveState==='DISCONNECTED'||driveState==='FOLDER_CHANGED';
   reply(res,200,{
     schema:'qualityrag.protected-dependency-status/v1',
     decisionId:decision.id,serviceId:decision.serviceId,
     environment:decision.environment,
     recordedPolicySha256:decision.policySha256,
     revoked,policyState,driveState,
     dependencyState:stale?'STALE':'UNKNOWN',
     sourceBytesRevalidated:false,
     reviewerKeyValidityRevalidated:false,
     permissionRevalidatedForUse:false,
     releasePermitted:false
   });
 }catch{
   reply(res,404,{error:'PROTECTED_DECISION_NOT_FOUND'});
 }
 return true;
}
