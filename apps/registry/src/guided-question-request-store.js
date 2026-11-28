// Internal metadata store. Call only after independently resolving current
// owner, policy, target and actor access. This store grants no authority.
import {createHash} from 'node:crypto';
const hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=v=>typeof v==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(v);
const valid=(s,targetId)=>s&&[s.ownerBinding,s.policyDigest,s.targetDigest].every(hex)&&[s.service,s.environment,targetId].every(id);
const params=(s,targetId)=>[s.ownerBinding,s.service,s.environment,s.policyDigest,s.targetDigest,targetId];
export function createGuidedQuestionRequestStore(pool){
 if(typeof pool?.query!=='function')throw Error('REQUEST_STORE_REQUIRED');
 async function enqueue(scope,targetId){
  if(!valid(scope,targetId))return null;
  const values=params(scope,targetId);
  const requestId=createHash('sha256').update(JSON.stringify(['qualityrag.guided-question-request/v1',...values])).digest('hex');
  // Conflict is idempotent; no rewrite of immutable creation metadata.
  await pool.query('INSERT INTO qr_guided_question_requests(request_id,owner_binding,service_id,environment,policy_digest,target_digest,target_id) VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING',[requestId,...values]);
  const r=await pool.query('SELECT request_id,created_at FROM qr_guided_question_requests WHERE request_id=$1 AND owner_binding=$2 AND service_id=$3 AND environment=$4 AND policy_digest=$5 AND target_digest=$6 AND target_id=$7',[requestId,...values]);
  if(r.rowCount!==1)return null;
  return {schema:'qualityrag.guided-question-request/v1',requestId,createdAt:r.rows[0].created_at,state:'REGISTERED',releasePermitted:false,answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'};
 }
 async function latestReceipt(scope,targetId){
  if(!valid(scope,targetId))return null;
  const r=await pool.query(`SELECT r.receipt_digest,r.verdict FROM qr_guided_question_requests q
   JOIN qr_guided_question_receipts r ON r.owner_binding=q.owner_binding AND r.service_id=q.service_id AND r.environment=q.environment AND r.policy_digest=q.policy_digest AND r.target_digest=q.target_digest
   WHERE q.owner_binding=$1 AND q.service_id=$2 AND q.environment=$3 AND q.policy_digest=$4 AND q.target_digest=$5 AND q.target_id=$6
   ORDER BY r.recorded_at DESC,r.receipt_digest DESC LIMIT 1`,params(scope,targetId));
  // Historical candidate only; caller must recheck current eligibility.
  if(r.rowCount!==1||!hex(r.rows[0].receipt_digest))return null;
  return {targetId,receiptDigest:r.rows[0].receipt_digest,historicalVerdict:r.rows[0].verdict,releasePermitted:false};
 }
 return {enqueue,latestReceipt};
}
