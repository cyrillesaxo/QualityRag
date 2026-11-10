import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHash,generateKeyPairSync,sign} from 'node:crypto';
import {reviewCanonical,verifyHumanReviewAttestations,humanReviewDecision} from '../src/protected-admission.js';
import {createHandler} from '../src/server.js';
const sha=x=>createHash('sha256').update(x).digest('hex');
const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',subject='issuer#alice';
const schema='qualityrag.signed-observations/v1';
function fixture(opts={}){
 const keys=[generateKeyPairSync('ed25519'),generateKeyPairSync('ed25519')];
 const trust={custodian:{keyId:'custodian',key:keys[0].publicKey},
  meaningReviewer:{keyId:'reviewer',key:keys[1].publicKey}};
 const policy={id:'governance',version:'1',requirements:[{id:'rule'}]};
 const policySha256=sha('bound policy');
 const exact='The provider pays the clinic before the deadline.';
 const witness={sourceId:'google_drive/'+'a'.repeat(32),revision:sha('synthetic provider bytes'),
  requirementId:'rule',lineNumber:1,lineSha256:sha(exact),
  origin:'org_'+'b'.repeat(32),status:'SUPPORTS'};
 const now=Date.now();
 const payload={service:'claims',environment:'prod',
  policy_signature:'UNSIGNED-V0.1-PACK-SHA256:'+policySha256,
  nonce:'independent-signed-review-1234',
  issued_at:new Date(now-1000).toISOString(),
  expires_at:new Date(now+60000).toISOString(),
  witnesses:[witness],
  observations:{kind:'qualityrag.protected-drive-human-review/v1',
   owner_binding:sha('qualityrag.review-owner/v1:'+subject),folder_id:'folder-a',
   review_basis:'HUMAN_SEMANTIC_APPROVAL',origin_basis:'CUSTODIAN_ATTESTED'}};
 const envelope=(k,keyId)=>({schema,canonical:'QR-CJSON-1',key_id:keyId,payload,
  signature:sign(null,Buffer.concat([Buffer.from('QUALITYRAG/'+schema+'\0'),reviewCanonical(payload)]),
   k.privateKey).toString('base64url')});
 const custody=envelope(keys[0],'custodian'),meaning=envelope(keys[1],'reviewer');
 const verified=verifyHumanReviewAttestations(custody,meaning,trust,{
  serviceId:'claims',environment:'prod',policySha256,subject,folderId:'folder-a',now});
 const checkedAt=new Date(now).toISOString();
 const result=humanReviewDecision(policy,policySha256,[witness],checkedAt).result;
 let revoked=Boolean(opts.revoked),writes=0,reads=0;
 const ledger={
  protectedDecisionForOwner(key,owner){
   assert.equal(key,id);assert.equal(owner,subject);return {
    id,serviceId:'claims',environment:'prod',policySha256,
    signedCustody:custody,signedMeaning:meaning,signedPayloadSha256:verified.signedPayloadSha256,
    result};
  },
  protectedDecisionRevocation(){return revoked?{at:checkedAt}:null},
  recordProtectedUse({mode,answerSha256,requestId}){
   if(revoked)throw Error('PROTECTED_DECISION_REVOKED');
   assert.equal(mode,'SOURCE_GROUNDED_EXTRACT');assert.equal(requestId,'fresh-request');
   assert.match(answerSha256,/^[0-9a-f]{64}$/);writes++;return {permission:'PERMIT_SIGNED_ASSERTION_USE'};
  }
 };
 const live={checkedAt,
  verifiedLines:[{requirementId:'rule',sourceId:witness.sourceId,lineNumber:1,
    lineSha256:witness.lineSha256,text:opts.changedLine?'Other bytes':exact,context:[]}],
  constraintScan:{schema:'qualityrag.constraint-signal-scan/v1',
   scope:'LIVE_VERIFIED_SIGNED_SOURCE_FILES_ONLY',sourcesScanned:1,linesScanned:1,
   candidateCount:opts.exception?1:0,candidatesTruncated:false,
   documentWideSemanticCompletenessVerified:false},
  relationshipScan:{candidateCount:opts.conflict?1:0,candidatesTruncated:false}};
 const driveManager={status(){return {connected:true,folderId:'folder-a',email:'alice@example.invalid'}}};
 const driveIndex={async verifyLiveApprovedWitnesses(owner,manager,witnesses,options){
  reads++;assert.equal(owner,subject);assert.equal(manager,driveManager);
  assert.equal(options.includeWitnessLines,true);
  assert.equal(options.includeConstraintScan,true);
  assert.equal(options.includeRelationshipScan,true);
  return live;
 }};
 const identities={
  alice:{subject,roles:new Set(['evidence.ingest','drive.reader']),
   evidenceServices:new Set(['claims@prod'])},
  outsider:{subject:'issuer#mallory',roles:new Set(['evidence.ingest','drive.reader']),
   evidenceServices:new Set(['other@prod'])}
 };
 return {get writes(){return writes},get reads(){return reads},setRevoked(v){revoked=v},
  ledger,driveManager,driveIndex,trust,store:{async resolve(){return {policy,sha256:policySha256}}},
  authenticate:async token=>identities[token]||null};
}
async function request(f,{token='alice',body={requestId:'fresh-request'},method='POST'}={}){
 const options={authenticate:f.authenticate,evidenceLedger:f.ledger,
  driveManager:f.driveManager,driveIndex:f.driveIndex,
  protectedReviewTrust:f.trust,protectedDriveServices:new Set(['claims@prod'])};
 const server=http.createServer(createHandler(f.store,null,options));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
  const r=await fetch('http://127.0.0.1:'+server.address().port+
   '/v1/evidence/protected-decisions/'+id+'/grounded-deliver',{
    method,headers:{authorization:'Bearer '+token,'content-type':'application/json'},
    body:method==='POST'?JSON.stringify(body):undefined});
  return {status:r.status,data:await r.json()};
 }finally{await new Promise(done=>server.close(done))}
}
async function checkLiveDependency(f,{token='alice'}={}){
 const options={authenticate:async supplied=>{
   const resolved=await f.authenticate(supplied);
   if(!resolved)return null;
   return {...resolved,roles:new Set([...resolved.roles,'evidence.reader'])};
 },evidenceLedger:f.ledger,driveManager:f.driveManager,
   driveIndex:f.driveIndex,protectedReviewTrust:f.trust,
   protectedDriveServices:new Set(['claims@prod'])};
 const server=http.createServer(createHandler(f.store,null,options));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
   const r=await fetch('http://127.0.0.1:'+server.address().port+
     '/v1/evidence/protected-decisions/'+id+'/dependency-status',{
       headers:{authorization:'Bearer '+token}
     });
   return {status:r.status,data:await r.json()};
 }finally{await new Promise(done=>server.close(done))}
}
test('US-068 read-only recheck uses signed witness and current Google source verification without recording use',async()=>{
 const f=fixture();
 const r=await checkLiveDependency(f);
 assert.equal(r.status,200,JSON.stringify(r.data));
 assert.equal(r.data.dependencyState,'UNKNOWN');
 assert.equal(r.data.liveSourceState,'MATCHED_AT_CHECK_TIME');
 assert.equal(r.data.sourceBytesRevalidated,true);
 assert.equal(r.data.reviewerKeyValidityRevalidated,false);
 assert.equal(r.data.releasePermitted,false);
 assert.equal(f.reads,1);
 assert.equal(f.writes,0);
});
test('US-068 known source constraint conflicts mark dependency stale without releasing data',async()=>{
 for(const opts of [{exception:true},{conflict:true},{revoked:true}]){
   const f=fixture(opts),r=await checkLiveDependency(f);
   assert.equal(r.status,200,JSON.stringify(r.data));
   assert.equal(r.data.dependencyState,'STALE');
   assert.equal(r.data.releasePermitted,false);
   assert.equal(f.writes,0);
 }
});
test('US-068 remote read failures and missing live verification do not become approvals',async()=>{
 const f=fixture();
 f.driveIndex.verifyLiveApprovedWitnesses=async()=>{
   throw Error('GOOGLE_DRIVE_UNAVAILABLE');
 };
 const r=await checkLiveDependency(f);
 assert.equal(r.status,200,JSON.stringify(r.data));
 assert.equal(r.data.liveSourceState,'UNKNOWN');
 assert.equal(r.data.sourceBytesRevalidated,false);
 assert.equal(r.data.dependencyState,'UNKNOWN');
 assert.equal(f.writes,0);
});
test('a fresh signed and live-verified source releases only exact extract, with caveats',async()=>{
 const f=fixture(),r=await request(f);
 assert.equal(r.status,200,JSON.stringify(r.data));
 assert.equal(r.data.delivery,'SERVER_GENERATED_EXTRACT_ONLY');
 assert.match(r.data.answer,/The provider pays the clinic before the deadline/);
 assert.equal(r.data.answerSemanticsVerified,false);
 assert.equal(r.data.coverage.documentWideCompletenessVerified,undefined);
 assert.equal(r.data.assertions.documentWideCompletenessVerified,false);
 assert.equal(f.writes,1);assert.equal(f.reads,1);
});
test('revoked decision never accesses source bytes or releases',async()=>{
 const f=fixture({revoked:true}),r=await request(f);
 assert.equal(r.status,409);assert.equal(r.data.releasePermitted,false);
 assert.equal(r.data.error,'PROTECTED_DECISION_REVOKED');
 assert.equal(f.reads,0);assert.equal(f.writes,0);
});
test('lexical exception and cross-document conflict deny after fresh provider read',async()=>{
 for(const v of [{exception:true},{conflict:true},{changedLine:true}]){
  const f=fixture(v),r=await request(f);
  assert.equal(r.status,409,JSON.stringify(r.data));
  assert.equal(r.data.releasePermitted,false);
  assert.equal(f.reads,1);assert.equal(f.writes,0);
 }
});
test('wrong owner service and caller-authored answer are not permitted',async()=>{
 const f=fixture();
 assert.equal((await request(f,{token:'outsider'})).status,409);
 assert.equal((await request(f,{body:{requestId:'fresh-request',answer:'invented content'}})).status,400);
 assert.equal((await request(f,{method:'GET'})).status,404);
 assert.equal(f.writes,0);assert.equal(f.reads,0);
});
