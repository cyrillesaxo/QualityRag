// Read-only, owner-scoped reconciliation of a protected-use requestId.
// "NOT_RECORDED" is a snapshot, NEVER permission to retry an in-flight use.
const ROUTE=/^\/v1\/evidence\/protected-decisions\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/use-status$/i;
const REQUEST=/^delivery-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function reply(res,code,value){
 res.writeHead(code,{'content-type':'application/json; charset=utf-8',
  'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(value));
}
export async function handleProtectedUseReconciliation(req,res,{
 pathname,searchParams,actor,identity,authenticate,evidenceLedger
}){
 const match=pathname.match(ROUTE);
 if(!match)return false;
 if(req.method!=='GET'){reply(res,404,{error:'NOT_FOUND'});return true}
 if(!authenticate||!evidenceLedger){
   reply(res,404,{error:'PROTECTED_RECONCILIATION_DISABLED'});return true;
 }
 const requestIds=searchParams?.getAll('requestId')||[];
 if(requestIds.length!==1||!REQUEST.test(requestIds[0])||
    !identity?.roles?.has('evidence.reader')){
   reply(res,404,{error:'PROTECTED_USE_NOT_FOUND'});return true;
 }
 try{
   const decision=evidenceLedger.protectedDecisionForOwner(match[1],actor);
   if(!identity.evidenceServices?.has(decision.serviceId+'@'+decision.environment)){
     reply(res,404,{error:'PROTECTED_USE_NOT_FOUND'});return true;
   }
   const data=evidenceLedger.protectedUseStatusForOwner(decision.id,actor,requestIds[0]);
   reply(res,200,data);
 }catch{
   // Neither a foreign decision nor foreign use can be enumerated.
   reply(res,404,{error:'PROTECTED_USE_NOT_FOUND'});
 }
 return true;
}
