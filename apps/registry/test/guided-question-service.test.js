import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign,createHash} from 'node:crypto';
import {createGuidedQuestionService} from '../src/guided-question-service.js';
import {SCHEMA,questionReviewBytes,questionTargetDigest} from '../src/guided-question-review.js';
const {privateKey,publicKey}=generateKeyPairSync('ed25519');
const pem=publicKey.export({type:'spki',format:'pem'});
const selector={service:'lexyread',environment:'test',targetId:'target1'};
const identity={subject:'owner1',roles:new Set(['evidence.ingest','evidence.reader']),evidenceServices:new Set(['lexyread@test'])};
const text='Accept only if ready.';
const target={ownerBinding:'a'.repeat(64),service:'lexyread',environment:'test',policyDigest:'b'.repeat(64),source:{id:'s',revision:'r',text},concept:{id:'c',revision:'v',label:'accept'},goalId:'g',operatorId:'boundary',evidence:{id:'e',obligationId:'o',kind:'boundary',consequence:'Preserve condition',sourceId:'s',revision:'r',conceptId:'c',semanticRevision:'v',start:0,end:text.length,quote:text}};
function signed(){
 const now=Date.now();
 const payload={schema:SCHEMA,ownerBinding:target.ownerBinding,service:target.service,environment:target.environment,policyDigest:target.policyDigest,targetDigest:questionTargetDigest(target),nonce:'fixture-nonce-0001',issuedAt:now-100,expiresAt:now+60000,decision:'ADMIT',reviewerId:'reviewer'};
 return {payload,signature:sign(null,questionReviewBytes(payload),privateKey).toString('base64url')};
}
function fixture({current=target,offline=false}={}){
 const calls=[],resolved=[];
 const grant={public_key_pem:pem,grant_version:'1',revoked_at:null};
 const conn={query:async(sql,args)=>{calls.push({sql,args});return sql.startsWith('SELECT')?{rowCount:1,rows:[grant]}:{rowCount:1};},release(){}};
 const pool={connect:async()=>conn,query:async(sql,args)=>{
 calls.push({sql,args});
 if(sql.includes('LEFT JOIN'))return {rowCount:1,rows:[{verdict:'ADMIT',policy_digest:target.policyDigest,target_digest:questionTargetDigest(target),grant_version:'1',current_version:'1',grant_revoked_at:null,public_key_pem:pem,key_digest:createHash('sha256').update(publicKey.export({type:'spki',format:'der'})).digest('hex'),expired:false,revoked:false}]};
 return {rowCount:1,rows:[grant]};
 }};
 const service=createGuidedQuestionService({pool,resolveAuthorizedTarget:async(i,s,a)=>{resolved.push({i,s,a});if(offline)throw Error('offline');return i.subject==='owner1'?current:null;}});
 return {service,calls,resolved};
}
test('reject missing identity, roles and service scope before resolver or storage',async()=>{
 const {service,calls,resolved}=fixture();
 for(const i of [null,{...identity,roles:new Set()},{...identity,evidenceServices:new Set()}]){
 assert.equal((await service.submit(i,selector,signed())).verdict,'INCONCLUSIVE');
 assert.equal((await service.eligibility(i,selector,'d'.repeat(64))).state,'UNKNOWN');
 }
 assert.equal(calls.length,0);assert.equal(resolved.length,0);
});
test('resolver enforces owner, service, availability and current policy',async()=>{
 for(const opts of [{current:null},{offline:true},{current:{...target,environment:'prod'}},{current:{...target,policyDigest:'c'.repeat(64)}}]){
 const {service,calls}=fixture(opts);assert.equal((await service.submit(identity,selector,signed())).verdict,'INCONCLUSIVE');assert.equal(calls.length,0);
 }
 const {service,calls}=fixture();assert.equal((await service.submit({...identity,subject:'other'},selector,signed())).verdict,'INCONCLUSIVE');assert.equal(calls.length,0);
});
test('valid signed review reaches transactional persistence using resolved target, not extra selector fields',async()=>{
 const {service,calls,resolved}=fixture();const r=await service.submit(identity,{...selector,targetDigest:'f'.repeat(64)},signed());
 assert.equal(r.verdict,'ADMIT');assert.equal(r.answerStatus,'UNKNOWN');assert.deepEqual(resolved[0].s,selector);
 assert.ok(calls.some(c=>c.sql.includes('FOR UPDATE')));assert.ok(calls.some(c=>c.sql.startsWith('INSERT INTO qr_guided_question_receipts')));assert.equal(calls.at(-1).sql,'COMMIT');
});
test('read eligibility is scoped and never grants release',async()=>{
 const {service,resolved}=fixture();const r=await service.eligibility(identity,selector,'d'.repeat(64));assert.equal(r.state,'ACTIVE');assert.equal(r.releasePermitted,false);assert.equal(resolved[0].a,'read');
 assert.equal((await service.eligibility(identity,selector,'bad')).state,'UNKNOWN');assert.equal(resolved.length,1);
});
test('mandatory target resolver cannot be omitted',()=>{assert.throws(()=>createGuidedQuestionService({}),/AUTHORIZED_TARGET_RESOLVER_REQUIRED/);});
