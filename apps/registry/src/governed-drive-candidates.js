// Read-only governed candidate previews and append-only owner-scoped challenges.
// A lexical candidate is never a human-reviewed admission or a proof of semantics.
const ID=/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const PATHS=new Set(['/v1/drives/google/governed-requirements',
 '/v1/drives/google/governed-check','/v1/drives/google/record-check']);
function reply(res,code,payload){
 res.writeHead(code,{'content-type':'application/json; charset=utf-8',
  'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(payload));
}
export async function handleGovernedDriveCandidates(req,res,{url,identity,actor,
 authenticate,driveManager,driveIndex,evidenceLedger,store,parseBody}){
 const path=url.pathname;
 if(!PATHS.has(path))return false;
 if(!authenticate||!driveManager||!driveIndex){
  reply(res,404,{error:'DRIVE_GOVERNED_CHECK_DISABLED'});return true;
 }
 if(!identity?.roles?.has('drive.reader')||!identity.roles.has('evidence.reader')){
  reply(res,403,{error:'FORBIDDEN'});return true;
 }
 const requirements=path.endsWith('/governed-requirements');
 const record=path.endsWith('/record-check');
 if(req.method!==(requirements?'GET':'POST')){
  reply(res,404,{error:'NOT_FOUND'});return true;
 }
 if(record&&(!identity.roles.has('evidence.reviewer')||!evidenceLedger)){
  reply(res,403,{error:'REVIEWER_OR_TELEMETRY_REQUIRED'});return true;
 }
 try{
  let serviceId,environment,candidates;
  if(requirements){
   const names=[...url.searchParams.keys()];
   if(names.length!==2||names.some(k=>!['serviceId','environment'].includes(k))){
    reply(res,400,{error:'INVALID_DRIVE_GATE_REQUEST'});return true;
   }
   serviceId=url.searchParams.get('serviceId');
   environment=url.searchParams.get('environment');
  }else{
   const input=await parseBody(req);
   if(!input||typeof input!=='object'||Array.isArray(input)||
      Object.keys(input).length!==3||
      !['serviceId','environment','candidates'].every(k=>Object.hasOwn(input,k))){
    reply(res,400,{error:'INVALID_DRIVE_GATE_REQUEST'});return true;
   }
   ({serviceId,environment,candidates}=input);
  }
  if(typeof serviceId!=='string'||!ID.test(serviceId)||
     typeof environment!=='string'||!ID.test(environment)){
   reply(res,400,{error:'INVALID_DRIVE_GATE_REQUEST'});return true;
  }
  if(!identity.evidenceServices?.has(serviceId+'@'+environment)){
   reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});return true;
  }
  const bound=await store.resolve(serviceId,environment);
  if(requirements){
   reply(res,200,{schema:'qualityrag.drive-governed-requirements/v1',
    policy:{id:bound.policy.id,version:bound.policy.version,sha256:bound.sha256},
    requirements:bound.policy.requirements.map(r=>({id:r.id})),
    admissionStatus:'NOT_EVALUATED',sourceProvenance:'NOT_VERIFIED'});
   return true;
  }
  // US-068: in shared mode candidates are checked against the verified shared baseline only.
  const connection=await driveManager.status(actor);
  const result=driveIndex.cursorCoordinator?
    await driveIndex.checkGovernedCandidatesShared(actor,connection,bound.policy,bound.sha256,candidates):
    driveIndex.checkGovernedCandidates(actor,connection,bound.policy,bound.sha256,candidates);
  // Ledger writes only after all scoped policy and source-index validations.
  const receipt=record?evidenceLedger.recordCandidateCheck(
   serviceId,environment,actor,bound.sha256,result):null;
  reply(res,200,{...result,telemetry:{
   recorded:!!receipt,receiptId:receipt?.id||null,
   chainHash:receipt?.chainHash||null,
   externallyAnchored:false,scope:'REGISTRY_EVENT_ONLY'
  }});
 }catch(e){
  const recognized=new Set(['INVALID_DRIVE_GATE_REQUEST','INVALID_DRIVE_GATE_POLICY',
   'INVALID_DRIVE_GATE_CANDIDATES','INVALID_DRIVE_GATE_CANDIDATE',
   'DRIVE_GATE_DUPLICATE_CANDIDATE']);
  reply(res,400,{error:recognized.has(e?.message)?e.message:'DRIVE_GOVERNED_CHECK_FAILED'});
 }
 return true;
}
