import {createPublicKey,createHash} from 'node:crypto';
import {createQuestionNonceStore} from './guided-question-nonce-store.js';
const scopeSql='reviewer_id=$1 AND owner_binding=$2 AND service_id=$3 AND environment=$4 AND policy_digest=$5';
const params=(reviewerId,e)=>[reviewerId,e?.ownerBinding,e?.service,e?.environment,e?.policyDigest];
const keyDigest=key=>createHash('sha256').update(key.export({type:'spki',format:'der'})).digest('hex');
function snapshot(row){
 if(!row||row.revoked_at!==null)return null;
 const key=createPublicKey(row.public_key_pem);
 if(key.asymmetricKeyType!=='ed25519')return null;
 return {active:true,authorized:true,key,grantVersion:String(row.grant_version)};
}
// Server-side only. The pool must point to the authoritative registry DB.
// Grant administration must update/revoke the same rows; no deletion/recreation.
export function createQuestionReviewAuthority(pool){
 if(!pool||typeof pool.connect!=='function'||typeof pool.query!=='function')throw Error('QUESTION_AUTHORITY_POOL_REQUIRED');
 async function lookupReviewer(reviewerId,expected){
  const r=await pool.query('SELECT public_key_pem,grant_version,revoked_at FROM qr_guided_question_reviewer_grants WHERE '+scopeSql,params(reviewerId,expected));
  return r.rowCount===1?snapshot(r.rows[0]):null;
 }
 async function consumeNonce(input){
  const {reviewerId,expected,grantVersion,keyDigest:verifiedKey,receiptDigest,verdict}=input||{};
  if(typeof receiptDigest!=='string'||!/^[a-f0-9]{64}$/.test(receiptDigest)||!['ADMIT','REFUSE','INCONCLUSIVE'].includes(verdict))return false;
  if(typeof grantVersion!=='string'||!/^[1-9][0-9]*$/.test(grantVersion)||typeof verifiedKey!=='string'||!/^[a-f0-9]{64}$/.test(verifiedKey))return false;
  const conn=await pool.connect();
  try{
   await conn.query('BEGIN');
   const r=await conn.query('SELECT public_key_pem,grant_version,revoked_at FROM qr_guided_question_reviewer_grants WHERE '+scopeSql+' FOR UPDATE',params(reviewerId,expected));
   const current=r.rowCount===1?snapshot(r.rows[0]):null;
   if(!current||current.grantVersion!==grantVersion||keyDigest(current.key)!==verifiedKey){
    await conn.query('ROLLBACK');return false;
   }
   const consumed=await createQuestionNonceStore(conn)(input);
   if(!consumed){await conn.query('ROLLBACK');return false;}
   const nonceDigest=createHash('sha256').update(JSON.stringify(['qualityrag.guided-question-nonce/v1',reviewerId,input.nonce])).digest('hex');
   const saved=await conn.query('INSERT INTO qr_guided_question_receipts(receipt_digest,nonce_digest,owner_binding,service_id,environment,policy_digest,target_digest,reviewer_id,grant_version,key_digest,verdict,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,to_timestamp($12::double precision / 1000)) RETURNING receipt_digest',[receiptDigest,nonceDigest,expected.ownerBinding,expected.service,expected.environment,expected.policyDigest,expected.targetDigest,reviewerId,grantVersion,verifiedKey,verdict,input.expiresAt]);
   if(saved.rowCount!==1){await conn.query('ROLLBACK');return false;}
   await conn.query('COMMIT');return true;
  }catch(error){
   try{await conn.query('ROLLBACK');}catch{/* original failure remains authoritative */}
   throw error;
  }finally{conn.release();}
 }
 // Historical recovery only: authenticated host supplies current owner scope.
 async function recoverReceipt(receiptDigest,expected){
  if(typeof receiptDigest!=='string'||!/^[a-f0-9]{64}$/.test(receiptDigest)||!expected)return null;
  const r=await pool.query('SELECT receipt_digest,verdict,recorded_at,expires_at FROM qr_guided_question_receipts WHERE receipt_digest=$1 AND owner_binding=$2 AND service_id=$3 AND environment=$4 AND policy_digest=$5 AND target_digest=$6',[receiptDigest,expected.ownerBinding,expected.service,expected.environment,expected.policyDigest,expected.targetDigest]);
  if(r.rowCount!==1)return null;
  const row=r.rows[0];
  return {receiptDigest:row.receipt_digest,historicalVerdict:row.verdict,recordedAt:row.recorded_at,expiresAt:row.expires_at,releasePermitted:false,answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'};
 }
 return {lookupReviewer,consumeNonce,recoverReceipt};
}
