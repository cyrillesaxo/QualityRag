// Appends scoped human dispositions to the existing immutable evidence ledger.
// Never overwrites the engine verdict or upgrades unsigned source authenticity.
const ROUTE=/^\/v1\/evidence\/evaluations\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/reviews$/i;
const DECISIONS=new Set(['ACCEPTED','DISPUTED']);
const REASONS=new Set(['REPRODUCED','FALSE_BLOCK','PROVENANCE_UNVERIFIED','POLICY_DISAGREEMENT','OTHER']);
function reply(res,code,payload){
 res.writeHead(code,{'content-type':'application/json; charset=utf-8',
  'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(payload));
}
export async function handleEvidenceReview(req,res,{pathname,actor,identity,authenticate,
 evidenceLedger,parseBody}){
 const match=pathname.match(ROUTE);
 if(!match)return false;
 if(req.method!=='POST'){reply(res,404,{error:'NOT_FOUND'});return true}
 if(!authenticate||!evidenceLedger){
  reply(res,404,{error:'EVIDENCE_REVIEW_DISABLED'});return true;
 }
 if(!identity?.roles?.has('evidence.reviewer')){
  reply(res,403,{error:'FORBIDDEN'});return true;
 }
 try{
  const id=match[1];
  const row=evidenceLedger.snapshot(id);
  const scope=row.serviceId+'@'+row.environment;
  if(!identity.evidenceServices?.has(scope)){
   reply(res,404,{error:'EVIDENCE_NOT_FOUND'});return true;
  }
  const input=await parseBody(req);
  if(!input||typeof input!=='object'||Array.isArray(input)||
     !Object.keys(input).every(k=>['decision','reasonCode','note'].includes(k))||
     !DECISIONS.has(input.decision)||!REASONS.has(input.reasonCode)||
     (input.note!==undefined&&(typeof input.note!=='string'||input.note.length>280||
      /[\r\n@<>]/.test(input.note)))){
   reply(res,400,{error:'INVALID_REVIEW'});return true;
  }
  // Ledger enforces separation from original evaluator and replays first.
  const appended=evidenceLedger.review(id,{
   decision:input.decision,reasonCode:input.reasonCode,note:input.note||''
  },actor);
  reply(res,201,{...appended,engineVerdictChanged:false,
    sourceAuthenticityVerified:false,externallyAnchored:false});
 }catch(error){
  if(error?.message==='SELF_REVIEW_FORBIDDEN'){
   reply(res,403,{error:'SELF_REVIEW_FORBIDDEN'});return true;
  }
  if(error?.message==='REPLAY_MISMATCH'){
   reply(res,409,{error:'REPLAY_MISMATCH'});return true;
  }
  if(error?.message==='INVALID_REVIEW'){
   reply(res,400,{error:'INVALID_REVIEW'});return true;
  }
  reply(res,404,{error:'EVIDENCE_NOT_FOUND'});
 }
 return true;
}
