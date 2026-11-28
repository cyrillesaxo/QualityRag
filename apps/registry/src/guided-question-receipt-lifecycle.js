import {createPublicKey,createHash} from 'node:crypto';
const hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=v=>typeof v==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(v);
const valid=e=>e&&[e.ownerBinding,e.policyDigest,e.targetDigest].every(hex)&&[e.service,e.environment].every(id);
const result=state=>({state,eligibleAtCheck:state==='ACTIVE',releasePermitted:false,answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'});
// expected MUST be independently recomputed from current authorized source
// and policy by the trusted host. A historical digest supplied by a client
// cannot establish freshness. This snapshot is not a durable release permit.
export function createQuestionReceiptLifecycle(pool){
 if(!pool||typeof pool.query!=='function')throw Error('QUESTION_RECEIPT_POOL_REQUIRED');
 async function resolveEligibility(receiptDigest,expected){
  if(!hex(receiptDigest)||!valid(expected))return result('UNKNOWN');
  try{
   const r=await pool.query(`SELECT r.verdict,r.policy_digest,r.target_digest,r.grant_version,r.key_digest,
    (r.expires_at<=clock_timestamp()) AS expired,
    (v.receipt_digest IS NOT NULL) AS revoked,
    g.grant_version AS current_version,g.revoked_at AS grant_revoked_at,g.public_key_pem
    FROM qr_guided_question_receipts r
    LEFT JOIN qr_guided_question_receipt_revocations v ON v.receipt_digest=r.receipt_digest
    LEFT JOIN qr_guided_question_reviewer_grants g ON g.reviewer_id=r.reviewer_id AND g.owner_binding=r.owner_binding AND g.service_id=r.service_id AND g.environment=r.environment AND g.policy_digest=r.policy_digest
    WHERE r.receipt_digest=$1 AND r.owner_binding=$2 AND r.service_id=$3 AND r.environment=$4`,
   [receiptDigest,expected.ownerBinding,expected.service,expected.environment]);
   if(r.rowCount!==1)return result('UNKNOWN');
   const row=r.rows[0];
   if(row.revoked===true)return result('REVOKED');
   if(row.revoked!==false||row.expired!==false)return result(row.expired===true?'EXPIRED':'UNKNOWN');
   if(row.verdict!=='ADMIT')return result(row.verdict==='REFUSE'?'REFUSED':'UNKNOWN');
   if(row.policy_digest!==expected.policyDigest)return result('STALE_POLICY');
   if(row.target_digest!==expected.targetDigest)return result('STALE_TARGET');
   if(row.current_version==null||row.grant_revoked_at!==null||String(row.current_version)!==String(row.grant_version))return result('STALE_AUTHORITY');
   const key=createPublicKey(row.public_key_pem);
   if(key.asymmetricKeyType!=='ed25519'||createHash('sha256').update(key.export({type:'spki',format:'der'})).digest('hex')!==row.key_digest)return result('STALE_AUTHORITY');
   return result('ACTIVE');
  }catch{return result('UNKNOWN');}
 }
 // No public endpoint. Actor and owner authorization must be established
 // by the trusted server before calling; this operation does not enroll actors.
 async function revokeReceipt(receiptDigest,scope,actorBinding,reason){
  if(!hex(receiptDigest)||!valid(scope)||!hex(actorBinding)||!['OWNER_WITHDRAWN','REVIEW_DISPUTED','CUSTODY_DISPUTED'].includes(reason))return false;
  const r=await pool.query(`INSERT INTO qr_guided_question_receipt_revocations(receipt_digest,reason,actor_binding)
   SELECT receipt_digest,$7,$8 FROM qr_guided_question_receipts
   WHERE receipt_digest=$1 AND owner_binding=$2 AND service_id=$3 AND environment=$4 AND policy_digest=$5 AND target_digest=$6
   ON CONFLICT(receipt_digest) DO NOTHING RETURNING receipt_digest`,
   [receiptDigest,scope.ownerBinding,scope.service,scope.environment,scope.policyDigest,scope.targetDigest,reason,actorBinding]);
  return r.rowCount===1;
 }
 return {resolveEligibility,revokeReceipt};
}
