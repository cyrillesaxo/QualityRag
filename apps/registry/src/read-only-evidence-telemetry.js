// Service-scoped, read-only evidence telemetry. This is NOT a source-truth or
// application-wide enforcement monitor. Requires OIDC and explicit ledger injection.
const ID=/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function reply(res,code,body){
 res.writeHead(code,{'content-type':'application/json; charset=utf-8',
  'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(body));
}
function authorized(identity,scope){
 return identity?.roles instanceof Set&&identity.roles.has('evidence.reader')&&
  identity.evidenceServices instanceof Set&&identity.evidenceServices.has(scope);
}
export async function handleReadOnlyEvidenceTelemetry(req,res,{url,identity,authenticate,
 evidenceLedger,store,protectedDriveServices}){
 const path=url.pathname;
 const base='/v1/evidence/evaluations';
 if(path!=='/v1/evidence/enforcement'&&path!==base&&!path.startsWith(base+'/'))
  return false;
 if(!authenticate||!evidenceLedger){
  reply(res,404,{error:'EVIDENCE_TELEMETRY_DISABLED'});return true;
 }
 try{
  if(path==='/v1/evidence/enforcement'||path===base){
   if(req.method!=='GET'){reply(res,404,{error:'NOT_FOUND'});return true;}
   const serviceId=url.searchParams.get('serviceId'),
    environment=url.searchParams.get('environment');
   if(!ID.test(serviceId||'')||!ID.test(environment||'')||
      [...url.searchParams.keys()].some(k=>!['serviceId','environment'].includes(k))){
    reply(res,400,{error:'INVALID_EVIDENCE_QUERY'});return true;
   }
   if(!authorized(identity,serviceId+'@'+environment)){
    reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});return true;
   }
   const result=evidenceLedger.list(serviceId,environment);
   if(path===base){reply(res,200,result);return true;}
   const bound=await store.resolve(serviceId,environment);
   const protectedService=protectedDriveServices?.has(serviceId+'@'+environment)===true;
   reply(res,200,{
    schema:'qualityrag.drive-protection/v1',serviceId,environment,
    policy:{id:bound.policy.id,version:bound.policy.version,sha256:bound.sha256},
    protected:protectedService,
    mode:protectedService?'BLOCK_UNATTESTED_GENERIC_EVIDENCE':'LEGACY_METADATA_GATE',
    genericEvidenceIngress:protectedService?'BLOCKED':'ALLOWED',
    sourceAdmission:'NOT_VERIFIED_BY_THIS_ENDPOINT',
    globalApplicationEnforcement:false,externallyAnchored:false,
    guardTelemetry:result.guardTelemetry
   });return true;
  }
  const match=path.match(/^\/v1\/evidence\/evaluations\/([0-9a-f-]{36})(?:\/(export|replay))?$/i);
  if(!match||!UUID.test(match[1])||
     (match[2]==='replay'?req.method!=='POST':req.method!=='GET')){
   reply(res,404,{error:'NOT_FOUND'});return true;
  }
  const snapshot=evidenceLedger.snapshot(match[1]);
  if(!authorized(identity,snapshot.serviceId+'@'+snapshot.environment)){
   reply(res,403,{error:'EVIDENCE_SCOPE_FORBIDDEN'});return true;
  }
  const result=match[2]==='export'?evidenceLedger.exportReplay(match[1]):
   match[2]==='replay'?evidenceLedger.replay(match[1]):snapshot;
  reply(res,200,result);
 }catch{
  reply(res,404,{error:'EVIDENCE_NOT_AVAILABLE'});
 }
 return true;
}
