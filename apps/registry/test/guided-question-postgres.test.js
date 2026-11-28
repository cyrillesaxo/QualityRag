// Explicit opt-in; disposable schema, never the default DATABASE_URL.
import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes,generateKeyPairSync,sign} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {createQuestionReviewAuthority} from '../src/guided-question-authority.js';
import {createQuestionReceiptLifecycle} from '../src/guided-question-receipt-lifecycle.js';
import {SCHEMA,questionReviewBytes,verifyQuestionReview} from '../src/guided-question-review.js';
const url=process.env.QR_GUIDED_TEST_DATABASE_URL;
test('real PostgreSQL: migrations, concurrent replay, revocation and rollback',{skip:!url,timeout:30000},async()=>{
 const {Pool}=await import('pg');
 const schema='qr_test_'+randomBytes(12).toString('hex');
 const admin=new Pool({connectionString:url,connectionTimeoutMillis:3000,statement_timeout:10000});
 let pool;
 try{
  await admin.query('CREATE SCHEMA '+schema);
  pool=new Pool({connectionString:url,options:'-c search_path='+schema,connectionTimeoutMillis:3000,statement_timeout:10000,max:6});
  for(const name of ['016_guided_question_nonces.sql','017_guided_question_reviewer_grants.sql','018_guided_question_receipts.sql','019_guided_question_receipt_revocations.sql']){
   await pool.query(await readFile(new URL('../migrations/'+name,import.meta.url),'utf8'));
  }
  const {publicKey,privateKey}=generateKeyPairSync('ed25519');
  const expected={ownerBinding:'a'.repeat(64),service:'lexyread',environment:'test',policyDigest:'b'.repeat(64),targetDigest:'c'.repeat(64)};
  await pool.query('INSERT INTO qr_guided_question_reviewer_grants(reviewer_id,owner_binding,service_id,environment,policy_digest,public_key_pem) VALUES($1,$2,$3,$4,$5,$6)',['reviewer',expected.ownerBinding,expected.service,expected.environment,expected.policyDigest,publicKey.export({type:'spki',format:'pem'})]);
  const authority=createQuestionReviewAuthority(pool), lifecycle=createQuestionReceiptLifecycle(pool);
  const envelope=()=>{const now=Date.now(),payload={schema:SCHEMA,...expected,nonce:randomBytes(18).toString('hex'),issuedAt:now,expiresAt:now+120000,decision:'ADMIT',reviewerId:'reviewer'};return {payload,signature:sign(null,questionReviewBytes(payload),privateKey).toString('base64url')};};
  const run=(e,patch={})=>verifyQuestionReview({envelope:e,expected,lookupReviewer:authority.lookupReviewer,consumeNonce:authority.consumeNonce,...patch});
  const e=envelope(),results=await Promise.all(Array.from({length:5},()=>run(e)));
  const accepted=results.filter(r=>r.verdict==='ADMIT');
  assert.equal(accepted.length,1);
  const receipt=accepted[0].receiptDigest;
  assert.equal((await lifecycle.resolveEligibility(receipt,expected)).state,'ACTIVE');
  assert.equal((await authority.recoverReceipt(receipt,expected)).releasePermitted,false);
  assert.equal((await lifecycle.resolveEligibility(receipt,{...expected,ownerBinding:'f'.repeat(64)})).state,'UNKNOWN');
  // Real constraint failure after nonce insert must roll back the entire transaction.
  await pool.query("ALTER TABLE qr_guided_question_receipts ADD CONSTRAINT test_reject_new CHECK (verdict <> 'ADMIT') NOT VALID");
  const retry=envelope();
  assert.equal((await run(retry)).verdict,'INCONCLUSIVE');
  assert.equal((await pool.query('SELECT count(*)::int AS n FROM qr_guided_question_nonces')).rows[0].n,1);
  await pool.query('ALTER TABLE qr_guided_question_receipts DROP CONSTRAINT test_reject_new');
  assert.equal((await run(retry)).verdict,'ADMIT');
  // Hold a revocation transaction open while admission attempts its row lock.
  const revoker=await pool.connect();
  try{
   await revoker.query('BEGIN');
   await revoker.query("UPDATE qr_guided_question_reviewer_grants SET revoked_at=clock_timestamp() WHERE reviewer_id='reviewer'");
   const race=envelope();
   let started;
   const ready=new Promise(resolve=>{started=resolve;});
   const pending=run(race,{consumeNonce:async input=>{started();return authority.consumeNonce(input);}});
   // A plain lookup sees the last committed grant while revocation is open.
   await Promise.race([ready,pending.then(()=>{throw Error('admission did not reach final gate');})]);
   await revoker.query('COMMIT');
   assert.equal((await pending).verdict,'INCONCLUSIVE');
  }finally{await revoker.query('ROLLBACK');revoker.release();}
  assert.equal((await lifecycle.resolveEligibility(receipt,expected)).state,'STALE_AUTHORITY');
  assert.equal(await lifecycle.revokeReceipt(receipt,expected,'d'.repeat(64),'OWNER_WITHDRAWN'),true);
  assert.equal((await lifecycle.resolveEligibility(receipt,expected)).state,'REVOKED');
  assert.equal((await pool.query('SELECT count(*)::int AS n FROM qr_guided_question_receipts')).rows[0].n,2);
 }finally{
  if(pool)await pool.end();
  try{await admin.query('DROP SCHEMA IF EXISTS '+schema+' CASCADE');}finally{await admin.end();}
 }
});
