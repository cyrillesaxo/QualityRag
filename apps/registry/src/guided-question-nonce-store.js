import {createHash} from 'node:crypto';
// Use the existing registry PostgreSQL pool. No in-memory fallback.
// Reviewer identity and nonce uniqueness are global across owner scopes.
export function createQuestionNonceStore(pool){
 if(!pool||typeof pool.query!=='function')throw Error('QUESTION_NONCE_STORE_REQUIRED');
 return async function consumeNonce({reviewerId,nonce,expiresAt,expected}={}){
  if(typeof reviewerId!=='string'||! /^[A-Za-z0-9._:-]{1,128}$/.test(reviewerId)||typeof nonce!=='string'||! /^[A-Za-z0-9._:-]{16,128}$/.test(nonce)||!Number.isSafeInteger(expiresAt)||typeof expected?.targetDigest!=='string'||! /^[a-f0-9]{64}$/.test(expected.targetDigest))return false;
  const digest=createHash('sha256').update(JSON.stringify(['qualityrag.guided-question-nonce/v1',reviewerId,nonce])).digest('hex');
  const result=await pool.query(
   'INSERT INTO qr_guided_question_nonces(nonce_digest,target_digest,expires_at) SELECT $1,$2,to_timestamp($3::double precision / 1000) WHERE to_timestamp($3::double precision / 1000)>clock_timestamp() ON CONFLICT (nonce_digest) DO NOTHING RETURNING nonce_digest',
   [digest,expected.targetDigest,expiresAt]);
  return result.rowCount===1;
 };
}
