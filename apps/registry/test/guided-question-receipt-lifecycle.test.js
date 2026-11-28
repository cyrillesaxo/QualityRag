import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,createHash} from 'node:crypto';
import {createQuestionReceiptLifecycle} from '../src/guided-question-receipt-lifecycle.js';
const {publicKey}=generateKeyPairSync('ed25519');
const expected={ownerBinding:'a'.repeat(64),service:'lexyread',environment:'test',policyDigest:'b'.repeat(64),targetDigest:'c'.repeat(64)};
const receipt='d'.repeat(64);
const row={verdict:'ADMIT',policy_digest:expected.policyDigest,target_digest:expected.targetDigest,grant_version:'7',current_version:'7',grant_revoked_at:null,public_key_pem:publicKey.export({type:'spki',format:'pem'}),key_digest:createHash('sha256').update(publicKey.export({type:'spki',format:'der'})).digest('hex'),expired:false,revoked:false};
function fixture({current=row,fail=false,insert=1}={}){
 const calls=[];
 const pool={query:async(sql,args)=>{calls.push({sql,args});if(fail)throw Error('offline');if(sql.startsWith('INSERT'))return {rowCount:insert};return {rowCount:current?1:0,rows:current?[current]:[]};}};
 return {lifecycle:createQuestionReceiptLifecycle(pool),calls};
}
test('active receipt is point-in-time eligibility, never release or answer verification',async()=>{const {lifecycle,calls}=fixture();const r=await lifecycle.resolveEligibility(receipt,expected);assert.equal(r.state,'ACTIVE');assert.equal(r.eligibleAtCheck,true);assert.equal(r.releasePermitted,false);assert.equal(r.answerStatus,'UNKNOWN');assert.equal(r.learnerStatus,'UNKNOWN');assert.deepEqual(calls[0].args,[receipt,expected.ownerBinding,expected.service,expected.environment]);});
test('expired, revoked, refused, stale policy and target fail closed',async()=>{for(const [patch,state] of [[{expired:true},'EXPIRED'],[{revoked:true},'REVOKED'],[{verdict:'REFUSE'},'REFUSED'],[{policy_digest:'e'.repeat(64)},'STALE_POLICY'],[{target_digest:'e'.repeat(64)},'STALE_TARGET']]){const {lifecycle}=fixture({current:{...row,...patch}});const r=await lifecycle.resolveEligibility(receipt,expected);assert.equal(r.state,state);assert.equal(r.eligibleAtCheck,false);}});
test('revoked grant, version change and key substitution fail closed',async()=>{for(const patch of [{grant_revoked_at:'revoked'},{current_version:'8'},{current_version:null},{key_digest:'e'.repeat(64)}]){const {lifecycle}=fixture({current:{...row,...patch}});assert.equal((await lifecycle.resolveEligibility(receipt,expected)).state,'STALE_AUTHORITY');}});
test('missing receipt, invalid scope and database outage return UNKNOWN',async()=>{for(const opts of [{current:null},{fail:true}])assert.equal((await fixture(opts).lifecycle.resolveEligibility(receipt,expected)).state,'UNKNOWN');const {lifecycle,calls}=fixture();assert.equal((await lifecycle.resolveEligibility(receipt,{...expected,ownerBinding:'bad'})).state,'UNKNOWN');assert.equal(calls.length,0);});
test('revocation binds original receipt scope and preserves first revocation',async()=>{const {lifecycle,calls}=fixture();const actor='f'.repeat(64);assert.equal(await lifecycle.revokeReceipt(receipt,expected,actor,'OWNER_WITHDRAWN'),true);assert.deepEqual(calls[0].args,[receipt,expected.ownerBinding,expected.service,expected.environment,expected.policyDigest,expected.targetDigest,'OWNER_WITHDRAWN',actor]);assert.match(calls[0].sql,/ON CONFLICT\(receipt_digest\) DO NOTHING/);assert.equal(await fixture({insert:0}).lifecycle.revokeReceipt(receipt,expected,actor,'OWNER_WITHDRAWN'),false);assert.equal(await lifecycle.revokeReceipt(receipt,expected,actor,'invalid'),false);assert.equal(calls.length,1);});
