import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign,createHash} from 'node:crypto';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {loadProtectedReviewTrust,reviewCanonical,verifyHumanReviewAttestations,humanReviewDecision} from '../src/protected-admission.js';

const schema='qualityrag.signed-observations/v1';
const sha=s=>createHash('sha256').update(s).digest('hex');
function setup(){
 const dir=mkdtempSync(path.join(os.tmpdir(),'qualityrag-signers-'));
 const keys=[generateKeyPairSync('ed25519'),generateKeyPairSync('ed25519')];
 const file=path.join(dir,'trust.json');
 writeFileSync(file,JSON.stringify({
  custodian:{keyId:'custodian',publicKeyPem:keys[0].publicKey.export({type:'spki',format:'pem'})},
  meaningReviewer:{keyId:'reviewer',publicKeyPem:keys[1].publicKey.export({type:'spki',format:'pem'})}
 }));
 const trust=loadProtectedReviewTrust(file);
 return {dir,keys,trust};
}
function fixture(now,subject){
 const issued=new Date(now-1000).toISOString(),expires=new Date(now+60000).toISOString();
 return {service:'claims',environment:'dev',policy_signature:'UNSIGNED-V0.1-PACK-SHA256:'+sha('policy'),
  nonce:'nonce-strong-0123456789',issued_at:issued,expires_at:expires,
  witnesses:[{sourceId:'google_drive/'+ 'a'.repeat(32),revision:sha('file'),
   requirementId:'governing-rule',lineNumber:1,lineSha256:sha('exact clause'),
   origin:'org_'+'b'.repeat(32),status:'SUPPORTS'}],
  observations:{kind:'qualityrag.protected-drive-human-review/v1',
   owner_binding:sha('qualityrag.review-owner/v1:'+subject),
   folder_id:'folder-1',review_basis:'HUMAN_SEMANTIC_APPROVAL',
   origin_basis:'CUSTODIAN_ATTESTED'}};
}
function envelope(payload,key,keyId){
 const bytes=Buffer.concat([Buffer.from('QUALITYRAG/'+schema+'\0'),reviewCanonical(payload)]);
 return {schema,canonical:'QR-CJSON-1',key_id:keyId,payload,
  signature:sign(null,bytes,key.privateKey).toString('base64url')};
}
test('two distinct trusted signer keys verify the same scoped exact-source manifest',()=>{
 const s=setup();try{
  const now=Date.now(),subject='issuer#owner',payload=fixture(now,subject);
  const cust=envelope(payload,s.keys[0],'custodian'),meaning=envelope(payload,s.keys[1],'reviewer');
  const result=verifyHumanReviewAttestations(cust,meaning,s.trust,{
   serviceId:'claims',environment:'dev',policySha256:sha('policy'),subject,folderId:'folder-1',now});
  assert.deepEqual(result.signerIds,['custodian','reviewer']);
  assert.equal(result.signedPayloadSha256,sha(reviewCanonical(payload)));
  assert.equal(result.payload.witnesses.length,1);
  assert.throws(()=>verifyHumanReviewAttestations(cust,meaning,s.trust,{
   serviceId:'claims',environment:'dev',policySha256:sha('policy'),
   subject:'issuer#other-owner',folderId:'folder-1',now}),/PROTECTED_REVIEW_OWNER_OR_SCOPE_MISMATCH/);
  assert.throws(()=>verifyHumanReviewAttestations(cust,meaning,s.trust,{
   serviceId:'claims',environment:'dev',policySha256:sha('policy'),
   subject,folderId:'folder-other',now}),/PROTECTED_REVIEW_OWNER_OR_SCOPE_MISMATCH/);
 }finally{rmSync(s.dir,{recursive:true,force:true})}
});
test('tampered reviewer signature, policy mismatch, and expired review fail closed',()=>{
 const s=setup();try{
  const now=Date.now(),subject='issuer#owner',payload=fixture(now,subject);
  const a=envelope(payload,s.keys[0],'custodian'),b=envelope(payload,s.keys[1],'reviewer');
  const params={serviceId:'claims',environment:'dev',policySha256:sha('policy'),
   subject,folderId:'folder-1',now};
  assert.throws(()=>verifyHumanReviewAttestations(a,{...b,signature:b.signature.slice(0,40)+(b.signature[40]==='A'?'B':'A')+b.signature.slice(41)},s.trust,params),
   /PROTECTED_INVALID_REVIEW_SIGNATURE/);
  assert.throws(()=>verifyHumanReviewAttestations(a,b,s.trust,{...params,policySha256:sha('other')}),
   /PROTECTED_REVIEW_POLICY_MISMATCH/);
  assert.throws(()=>verifyHumanReviewAttestations(a,b,s.trust,{...params,now:now+120000}),
   /PROTECTED_REVIEW_EXPIRED/);
 }finally{rmSync(s.dir,{recursive:true,force:true})}
});
test('review canonicalization rejects unsupported values and ambiguous presentation',()=>{
 assert.equal(reviewCanonical({b:2,a:1}).toString(),reviewCanonical({a:1,b:2}).toString());
 assert.throws(()=>reviewCanonical({nonascii:'é'}),/PROTECTED_NONCANONICAL_REVIEW/);
 assert.throws(()=>reviewCanonical({unsafe:1.5}),/PROTECTED_NONCANONICAL_REVIEW/);
});
test('signed review never claims original publisher truth or arbitrary independent origins',()=>{
 const pack={id:'test',version:'1',requirements:[{id:'governing-rule',min_independent_sources:2}]};
 assert.throws(()=>humanReviewDecision(pack,sha('policy'),[],new Date().toISOString()),
 /PROTECTED_POLICY_REQUIRES_UNSUPPORTED_PROOF/);
});
