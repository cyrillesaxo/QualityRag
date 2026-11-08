import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash,generateKeyPairSync,sign as edSign} from 'node:crypto';
import {randomBytes} from 'node:crypto';
import {RegistryStore} from '../src/store.js';
import {EvidenceLedger} from '../src/evidence-ledger.js';
import {UserDriveIndex} from '../src/user-drive-index.js';
import {createHandler} from '../src/server.js';
import {loadProtectedReviewTrust,reviewCanonical,
 verifyHumanReviewAttestations} from '../src/protected-admission.js';
import {permissionFor} from '../src/oidc.js';

const DOMAIN=Buffer.from('QUALITYRAG/qualityrag.signed-observations/v1\0','ascii');
const sha=str=>createHash('sha256').update(str).digest('hex');
const subject='trusted-issuer#owner-alice';
const SOURCE='Owner-approved policy: contractors are excepted.\nAll other reimbursements need approval.';
const witnessOrigin='org_'+'a'.repeat(32);
function pair(){
 const {publicKey,privateKey}=generateKeyPairSync('ed25519');
 return {publicKey,privateKey};
}
const custodial=pair(),meaningReview=pair(),attacker=pair();
function trust(keys={custodial,meaningReview}){
 return {
   custodian:{keyId:'customer-custodian-2026',key:keys.custodial.publicKey},
   meaningReviewer:{keyId:'customer-meaning-reviewer-2026',key:keys.meaningReview.publicKey}
 };
}
function sign(payload,keyId,key){
 return {schema:'qualityrag.signed-observations/v1',
   canonical:'QR-CJSON-1',key_id:keyId,payload,
   signature:edSign(null,Buffer.concat([DOMAIN,reviewCanonical(payload)]),
     key.privateKey).toString('base64url')};
}
function makeAttestations({serviceId='claims',environment='dev',policySha256,
   fileRef,revision,lineText=SOURCE.split('\n')[0],nonce='nonce-'+randomBytes(14).toString('hex'),
   owner=subject,folderId='folder-policy',requirementId='approval',
   expires=Date.now()+5*60_000,status='SUPPORTS',origin=witnessOrigin,
   issued=Date.now()}){
 const payload={
   service:serviceId,environment,
   policy_signature:'UNSIGNED-V0.1-PACK-SHA256:'+policySha256,
   nonce,
   issued_at:new Date(issued).toISOString(),expires_at:new Date(expires).toISOString(),
   witnesses:[{sourceId:fileRef,revision,requirementId,lineNumber:1,
     lineSha256:sha(lineText),origin,status}],
   observations:{kind:'qualityrag.protected-drive-human-review/v1',
     owner_binding:sha('qualityrag.review-owner/v1:'+owner),
     folder_id:folderId,review_basis:'HUMAN_SEMANTIC_APPROVAL',
     origin_basis:'CUSTODIAN_ATTESTED'}
 };
 return {
   custody:sign(payload,'customer-custodian-2026',custodial),
   meaning:sign(payload,'customer-meaning-reviewer-2026',meaningReview)
 };
}
test('approved source: independent role keys, current Google bytes and PackSpec bind admission',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-trusted-approval-'));
 const registry=new RegistryStore(path.join(dir,'registry.json'));
 registry.register({id:'claims',displayName:'Claims pilot'},'setup');
 registry.draft({id:'human-policy',version:'1',requirements:[
   {id:'approval',min_independent_sources:1}
 ]},'setup');
 registry.approve('human-policy','1','distinct-policy-approver');
 registry.bind('claims','dev','human-policy','1','publisher');
 registry.bind('claims','legacy','human-policy','1','publisher');
 const ledgerPath=path.join(dir,'evidence.jsonl');
 const ledger=new EvidenceLedger(ledgerPath);
 const index=new UserDriveIndex({dir:path.join(dir,'index'),
   encryptionKey:randomBytes(32).toString('base64')});
 let content=SOURCE,remoteAccess=true;
 let connected=true,folderId='folder-policy',email='alice@example.test';
 let pendingLive=null;
 const connector={
   status:who=>who===subject?{connected,email,folderId}:{
     connected:true,email:'bob@example.test',folderId:'folder-bob'
   },
   selectedFiles:async()=>({truncated:false,files:[{
     id:'policy-01',name:'Customer policy.txt',mimeType:'text/plain'}]}),
   supportsText:()=>true,
   downloadSelectedText:async()=>{
     if(pendingLive){const gate=pendingLive;pendingLive=null;await gate;}
     if(!remoteAccess)throw Error('DRIVE_AUTHORIZATION_REQUIRED');
     return Buffer.from(content,'utf8');
   }
 };
 const actors={
   owner:{subject,roles:new Set(['drive.reader','drive.manager','evidence.ingest','evidence.reader']),
     evidenceServices:new Set(['claims@dev','claims@legacy'])},
   ownerReviewer:{subject,roles:new Set(['drive.reader','drive.manager',
     'evidence.reader','evidence.reviewer']),evidenceServices:new Set(['claims@dev'])},
   foreignReviewer:{subject:'trusted-issuer#owner-bob',roles:new Set([
     'drive.reader','drive.manager','evidence.reader','evidence.reviewer']),
     evidenceServices:new Set(['claims@dev'])},
   other:{subject:'trusted-issuer#owner-bob',
     roles:new Set(['drive.reader','evidence.ingest','evidence.reader']),
     evidenceServices:new Set(['claims@dev'])},
   missingDrive:{subject,roles:new Set(['evidence.ingest']),
     evidenceServices:new Set(['claims@dev'])},
   missingIngest:{subject,roles:new Set(['drive.reader','evidence.reader']),
     evidenceServices:new Set(['claims@dev'])},
   wrongService:{subject,roles:new Set(['drive.reader','evidence.ingest']),
     evidenceServices:new Set(['claims@legacy'])}
 };
 const handler=createHandler(registry,null,{
   authenticate:async token=>actors[token]||null,
   driveManager:connector,driveIndex:index,evidenceLedger:ledger,
   protectedDriveServices:new Set(['claims@dev']),
   protectedReviewTrust:trust()
 });
 const server=http.createServer(handler);
 await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 const base='http://127.0.0.1:'+server.address().port;
 const request=async(method,route,token,payload)=>{
   const response=await fetch(base+route,{method,headers:{
     Authorization:'Bearer '+token,'Content-Type':'application/json'},
     body:payload===undefined?undefined:JSON.stringify(payload)});
   return {status:response.status,body:await response.json()};
 };
 try{
   assert.equal(permissionFor('POST','/v1/evidence/protected-admit'),'evidence.ingest');
   assert.equal(permissionFor('GET','/v1/evidence/protected-decisions/'+
     'a'.repeat(36)+'/export'),'evidence.reader');
   const keyFile=path.join(dir,'trusted-review-keys.json');
   fs.writeFileSync(keyFile,JSON.stringify({
     custodian:{keyId:'customer-custodian-2026',
       publicKeyPem:custodial.publicKey.export({type:'spki',format:'pem'})},
     meaningReviewer:{keyId:'customer-meaning-reviewer-2026',
       publicKeyPem:meaningReview.publicKey.export({type:'spki',format:'pem'})}
   }));
   assert.equal(loadProtectedReviewTrust(keyFile).custodian.keyId,
     'customer-custodian-2026');
   assert.throws(()=>loadProtectedReviewTrust(
     (fs.writeFileSync(keyFile,JSON.stringify({
       custodian:{keyId:'first',publicKeyPem:custodial.publicKey.export({type:'spki',format:'pem'})},
       meaningReviewer:{keyId:'second',publicKeyPem:custodial.publicKey.export({type:'spki',format:'pem'})}
     })),keyFile)),/PROTECTED_REVIEW_SIGNERS_MUST_DIFFER/);
   await index.sync(subject,connector);
   const view=index.search(subject,connector.status(subject),'Owner-approved policy');
   assert.equal(view.hits.length,1);
   const hit=view.hits[0];
   const bound=registry.resolve('claims','dev');
   let seq=0;
   const att=(changes={})=>makeAttestations({
     policySha256:bound.sha256,fileRef:hit.source_id,
     revision:hit.revision,...changes
   });
   const payload=(a)=>({serviceId:'claims',environment:'dev',
     requestId:'request-'+(++seq),traceId:'trace-'+seq,...a});
   const endpoint='/v1/evidence/protected-admit';
   assert.equal((await request('GET','/v1/evidence/enforcement?serviceId=claims&environment=dev',
     'owner')).body.sourceAdmission,'TWO_TRUSTED_HUMAN_SIGNATURES_AND_LIVE_BYTES');
   assert.equal((await request('POST',endpoint,'missingDrive',payload(att()))).status,403);
   assert.equal((await request('POST',endpoint,'missingIngest',payload(att()))).status,403);
   assert.equal((await request('POST',endpoint,'wrongService',payload(att()))).status,403);
   assert.equal((await request('POST',endpoint,'other',payload(att()))).status,403);
   const admittedPayload=payload(att());
   const admit=await request('POST',endpoint,'owner',admittedPayload);
   assert.equal(admit.status,201,JSON.stringify(admit.body));
   assert.equal(admit.body.result.verdict,'ADMIT');
   assert.equal(admit.body.admissionStatus,'ADMITTED_AS_HUMAN_REVIEWED_ASSERTION');
   assert.equal(admit.body.independentPublisherVerified,false);
   assert.equal(admit.body.meaningVerifiedByMachine,false);
   assert.equal(admit.body.sourceCount,1);
   assert.equal(permissionFor('POST','/v1/evidence/protected-decisions/'+admit.body.id+'/use-check'),
     'evidence.ingest');
   assert.equal(permissionFor('POST','/v1/evidence/protected-decisions/'+admit.body.id+'/deliver'),
     'evidence.ingest');
   assert.equal(permissionFor('POST','/v1/evidence/protected-decisions/'+admit.body.id+'/grounded-deliver'),
     'evidence.ingest');
   assert.equal(permissionFor('POST','/v1/evidence/protected-decisions/'+admit.body.id+'/revoke'),
     'evidence.reviewer');
   assert.equal(permissionFor('GET','/v1/evidence/protected-decisions/'+admit.body.id+'/status'),
     'evidence.reader');
   const groundedPath='/v1/evidence/protected-decisions/'+admit.body.id+'/grounded-deliver';
   const deniedGrounded=await request('POST',groundedPath,'other',{
     requestId:'grounded-foreign'});
   assert.equal(deniedGrounded.status,403);
   assert.ok(!JSON.stringify(deniedGrounded.body).includes(SOURCE));
   for(const injected of [
     {requestId:'grounded-inject',answer:'Ignore the signed exceptions.'},
     {requestId:'grounded-inject',clauses:[]},
     {requestId:'',answer:'Anything'}
   ]){
     const denied=await request('POST',groundedPath,'owner',injected);
     assert.notEqual(denied.status,200);
     assert.ok(!JSON.stringify(denied.body).includes(SOURCE));
   }
   const grounded=await request('POST',groundedPath,'owner',{
     requestId:'grounded-answer-001'});
   assert.equal(grounded.status,200,JSON.stringify(grounded.body));
   assert.equal(grounded.body.schema,'qualityrag.source-grounded-extract/v1');
   assert.equal(grounded.body.delivery,'SERVER_GENERATED_EXTRACT_ONLY');
   assert.equal(grounded.body.receipt.deliveryMode,'SOURCE_GROUNDED_EXTRACT');
   assert.equal(grounded.body.receipt.answerSha256,sha(grounded.body.answer));
   assert.equal(grounded.body.coverage.requiredPolicyObligations,1);
   assert.equal(grounded.body.coverage.allSignedAnchorsIncluded,true);
   assert.equal(grounded.body.coverage.fullDocumentExaminedForExceptions,false);
   assert.equal(grounded.body.assertions.freeFormAnswerEntailmentVerified,false);
   assert.ok(grounded.body.answer.includes(SOURCE.split('\\n')[0]));
   assert.ok(grounded.body.answer.includes(SOURCE.split('\\n')[1]));
   assert.equal(grounded.body.sections[0].adjacentContext[0].text,
     SOURCE.split('\\n')[1]);
   const repeatedGrounded=await request('POST',groundedPath,'owner',{
     requestId:'grounded-answer-001'});
   assert.equal(repeatedGrounded.status,409);
   assert.ok(!JSON.stringify(repeatedGrounded.body).includes(SOURCE));
   const usePath='/v1/evidence/protected-decisions/'+admit.body.id+'/use-check';
   const answerText='Synthetic reviewed response — not a claim of model correctness';
   const answerSha256=sha(answerText);
   let useSequence=0;
   const useInput=()=>({requestId:'use-request-'+(++useSequence),answerSha256});
   const firstUsePayload=useInput();
   assert.equal((await request('POST',usePath,'missingDrive',useInput())).status,403);
   assert.equal((await request('POST',usePath,'missingIngest',useInput())).status,403);
   assert.equal((await request('POST',usePath,'wrongService',useInput())).status,403);
   assert.equal((await request('POST',usePath,'other',useInput())).status,403);
   assert.equal((await request('POST',usePath,'owner',{
     ...useInput(),answerText})).status,409);
   const allowedUse=await request('POST',usePath,'owner',firstUsePayload);
   assert.equal(allowedUse.status,200,JSON.stringify(allowedUse.body));
   assert.equal(allowedUse.body.permission,'PERMIT_SIGNED_ASSERTION_USE');
   assert.equal(allowedUse.body.decisionId,admit.body.id);
   assert.equal(allowedUse.body.answerSha256,answerSha256);
   assert.equal(allowedUse.body.answerSemanticsVerified,false);
   assert.equal((await request('POST',usePath,'owner',firstUsePayload)).status,409);
   const deliverPath='/v1/evidence/protected-decisions/'+admit.body.id+'/deliver';
   const deliveryText='A customer-reviewed synthetic draft with exceptions; not verified semantic truth.';
   const deliveryInput={requestId:'delivery-one',answer:deliveryText};
   for(const badUser of ['other','missingDrive','missingIngest','wrongService']){
     const denied=await request('POST',deliverPath,badUser,{
       requestId:'delivery-denied-'+badUser,answer:deliveryText});
     assert.equal(denied.status,403,badUser+': '+JSON.stringify(denied.body));
     assert.ok(!JSON.stringify(denied.body).includes(deliveryText));
   }
   for(const invalid of [
     {...deliveryInput,override:true},
     {requestId:'no-answer',answer:''},
     {requestId:'too-big',answer:'X'.repeat(16385)},
     {requestId:'injected',answer:deliveryText+String.fromCharCode(0)}
   ]){
     const denied=await request('POST',deliverPath,'owner',invalid);
     assert.notEqual(denied.status,200);
     assert.ok(!JSON.stringify(denied.body).includes(deliveryText));
   }
   const delivered=await request('POST',deliverPath,'owner',deliveryInput);
   assert.equal(delivered.status,200,JSON.stringify(delivered.body));
   assert.equal(delivered.body.schema,'qualityrag.protected-answer-delivery/v1');
   assert.equal(delivered.body.answer,deliveryText);
   assert.equal(delivered.body.receipt.decisionId,admit.body.id);
   assert.equal(delivered.body.receipt.answerSha256,sha(deliveryText));
   assert.equal(delivered.body.receipt.deliveryMode,'SERVER_BUFFERED_RELEASE');
   assert.equal(delivered.body.answerSemanticsVerified,false);
   assert.equal(delivered.body.globalEnforcement,false);
   const repeatedDelivery=await request('POST',deliverPath,'owner',deliveryInput);
   assert.equal(repeatedDelivery.status,409);
   assert.ok(!JSON.stringify(repeatedDelivery.body).includes(deliveryText));
   // A source exclusion during live Google I/O must be observed at the
   // *second* owner-control check, before any use permit is recorded.
   let resumeDownload;
   pendingLive=new Promise(resolve=>{resumeDownload=resolve});
   const racePending=request('POST',usePath,'owner',useInput());
   for(let i=0;i<100&&pendingLive;i++)
     await new Promise(resolve=>setTimeout(resolve,5));
   assert.equal(pendingLive,null,'Google download should be in flight');
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:false,reason:'NEEDS_REVIEW'});
   resumeDownload();
   const racedUse=await racePending;
   assert.equal(racedUse.status,409);
   assert.equal(racedUse.body.error,'PROTECTED_OWNER_CONTEXT_CHANGED');
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:true,reason:'OWNER_SELECTION'});
   let resumeGateway;
   pendingLive=new Promise(resolve=>{resumeGateway=resolve});
   const gatewayRace=request('POST',deliverPath,'owner',{
     requestId:'delivery-race',answer:deliveryText});
   for(let i=0;i<100&&pendingLive;i++)
     await new Promise(resolve=>setTimeout(resolve,5));
   assert.equal(pendingLive,null,'Gateway must enter live download');
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:false,reason:'NEEDS_REVIEW'});
   resumeGateway();
   const afterRace=await gatewayRace;
   assert.equal(afterRace.status,409);
   assert.equal(afterRace.body.error,'PROTECTED_OWNER_CONTEXT_CHANGED');
   assert.ok(!JSON.stringify(afterRace.body).includes(deliveryText));
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:true,reason:'OWNER_SELECTION'});
   const exportUrl='/v1/evidence/protected-decisions/'+admit.body.id+'/export';
   assert.equal((await request('GET',exportUrl,'other')).status,403);
   assert.equal((await request('GET',exportUrl,'missingDrive')).status,403);
   assert.equal((await request('GET',exportUrl,'missingIngest')).status,200);
   const exported=await request('GET',exportUrl,'owner');
   assert.equal(exported.status,200);
   assert.equal(exported.body.schema,'qualityrag.protected-drive-decision-replay/v1');
   assert.equal(exported.body.signedCustody.signature,admittedPayload.custody.signature);
   assert.equal(exported.body.result.verdict,'ADMIT');
   assert.equal(exported.body.sourceTruthProven,false);
   // Python independently verifies the existing QR-CJSON-1 Ed25519 wire
   // format, the exact source bytes and a fresh SDK evaluation.
   const receiptFile=path.join(dir,'protected-receipt.json');
   const sourceFile=path.join(dir,'original-source.txt');
   fs.writeFileSync(receiptFile,JSON.stringify(exported.body));
   fs.writeFileSync(sourceFile,SOURCE);
   fs.writeFileSync(keyFile,JSON.stringify({
     custodian:{keyId:'customer-custodian-2026',
       publicKeyPem:custodial.publicKey.export({type:'spki',format:'pem'})},
     meaningReviewer:{keyId:'customer-meaning-reviewer-2026',
       publicKeyPem:meaningReview.publicKey.export({type:'spki',format:'pem'})}
   }));
   const script=fileURLToPath(new URL('../../../tools/packspec_compiler/verify_protected_drive_receipt.py',import.meta.url));
   const commands=['--receipt',receiptFile,'--trust',keyFile,
     '--owner-subject',subject,'--folder-id',folderId,
     '--source',hit.source_id+'='+sourceFile];
   const pythonReady=spawnSync('python',['--version'],{encoding:'utf8'});
   if(pythonReady.status===0){
     const independent=spawnSync('python',[script,...commands],{encoding:'utf8'});
     assert.equal(independent.status,0,
       independent.stdout+'\\n'+independent.stderr);
     assert.equal(JSON.parse(independent.stdout).independentReplayMatched,true);
     fs.writeFileSync(sourceFile,'Attacker swapped the original source bytes');
     const tampered=spawnSync('python',[script,...commands],{encoding:'utf8'});
     assert.equal(tampered.status,2,tampered.stdout+'\\n'+tampered.stderr);
     fs.writeFileSync(sourceFile,SOURCE);
   }
   assert.equal((await request('POST',endpoint,'owner',admittedPayload)).status,409);
   const modified=structuredClone(att());
   modified.meaning.payload.witnesses[0].status='CONTRADICTS';
   const wrongMeaning=await request('POST',endpoint,'owner',payload(modified));
   assert.equal(wrongMeaning.status,403);
   const forged=structuredClone(att());
   forged.meaning=sign(forged.meaning.payload,'customer-meaning-reviewer-2026',attacker);
   assert.equal((await request('POST',endpoint,'owner',payload(forged))).status,403);
   const signedOtherOwner=att({owner:'trusted-issuer#owner-bob'});
   assert.equal((await request('POST',endpoint,'owner',payload(signedOtherOwner))).status,403);
   const expired=att({issued:Date.now()-11*60_000,expires:Date.now()-5*60_000});
   assert.equal((await request('POST',endpoint,'owner',payload(expired))).status,403);
   const wrongPolicy=att({policySha256:'f'.repeat(64)});
   assert.equal((await request('POST',endpoint,'owner',payload(wrongPolicy))).status,403);
   const reclassified=att({status:'CONTRADICTS'});
   const refusal=await request('POST',endpoint,'owner',payload(reclassified));
   assert.equal(refusal.status,200);
   assert.equal(refusal.body.result.verdict,'REFUSE');
   assert.equal(refusal.body.admissionStatus,'NOT_ADMITTED');
   const refusedUse='/v1/evidence/protected-decisions/'+refusal.body.id+'/use-check';
   const neverAllowed=await request('POST',refusedUse,'owner',useInput());
   assert.equal(neverAllowed.status,409);
   assert.equal(neverAllowed.body.error,'PROTECTED_USE_DECISION_NOT_ADMITTED');
   const refusedDelivery=await request('POST',
     '/v1/evidence/protected-decisions/'+refusal.body.id+'/deliver','owner',{
       requestId:'delivery-refused',answer:deliveryText});
   assert.equal(refusedDelivery.status,409);
   assert.ok(!JSON.stringify(refusedDelivery.body).includes(deliveryText));
   const refusedGrounded=await request('POST',
     '/v1/evidence/protected-decisions/'+refusal.body.id+'/grounded-deliver',
     'owner',{requestId:'grounded-refused'});
   assert.equal(refusedGrounded.status,409);
   assert.ok(!JSON.stringify(refusedGrounded.body).includes(SOURCE));
   // A different accepted claim can be withdrawn by an owner *reviewer*
   // without excluding the entire source from private retrieval.
   const secondAdmit=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(secondAdmit.status,201,JSON.stringify(secondAdmit.body));
   const revokePath='/v1/evidence/protected-decisions/'+secondAdmit.body.id+'/revoke';
   const statusPath='/v1/evidence/protected-decisions/'+secondAdmit.body.id+'/status';
   const revokedUse='/v1/evidence/protected-decisions/'+secondAdmit.body.id+'/use-check';
   const statusBefore=await request('GET',statusPath,'owner');
   assert.equal(statusBefore.status,200);
   assert.equal(statusBefore.body.revoked,false);
   assert.equal(statusBefore.body.currentUseAuthorized,false);
   assert.equal((await request('POST',revokePath,'owner',{
     reason:'REVIEW_DISPUTED'})).status,403);
   assert.equal((await request('POST',revokePath,'foreignReviewer',{
     reason:'REVIEW_DISPUTED'})).status,403);
   assert.equal((await request('POST',revokePath,'ownerReviewer',{
     reason:'arbitrary request'})).status,409);
   const decisionWithdrawal=await request('POST',revokePath,'ownerReviewer',{
     reason:'REVIEW_DISPUTED'});
   assert.equal(decisionWithdrawal.status,200,JSON.stringify(decisionWithdrawal.body));
   assert.equal(decisionWithdrawal.body.status,'REVOKED');
   assert.equal(decisionWithdrawal.body.externallyAnchored,false);
   const statusAfter=await request('GET',statusPath,'owner');
   assert.equal(statusAfter.status,200);
   assert.equal(statusAfter.body.revoked,true);
   assert.equal(statusAfter.body.reason,'REVIEW_DISPUTED');
   const blockedRecalled=await request('POST',revokedUse,'owner',useInput());
   assert.equal(blockedRecalled.status,409);
   assert.equal(blockedRecalled.body.error,'PROTECTED_DECISION_REVOKED');
   const blockedDelivery=await request('POST',
     '/v1/evidence/protected-decisions/'+secondAdmit.body.id+'/deliver','owner',{
       requestId:'delivery-revoked',answer:deliveryText});
   assert.equal(blockedDelivery.status,409);
   assert.ok(!JSON.stringify(blockedDelivery.body).includes(deliveryText));
   const revokedGrounded=await request('POST',
     '/v1/evidence/protected-decisions/'+secondAdmit.body.id+'/grounded-deliver',
     'owner',{requestId:'grounded-revoked'});
   assert.equal(revokedGrounded.status,409);
   assert.ok(!JSON.stringify(revokedGrounded.body).includes(SOURCE));
   assert.equal((await request('POST',revokePath,'ownerReviewer',{
     reason:'OWNER_WITHDRAWN'})).status,409);
   assert.equal((await request('GET',statusPath,'foreignReviewer')).status,403);
   // An explicitly blocked source cannot be admitted even with two real signatures.
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:false,reason:'OUT_OF_SCOPE'});
   const denied=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(denied.status,409,JSON.stringify(denied.body));
   assert.equal(denied.body.error,'PROTECTED_OWNER_EXCLUDED_SOURCE');
   const useExcluded=await request('POST',usePath,'owner',useInput());
   assert.equal(useExcluded.status,409);
   assert.equal(useExcluded.body.error,'PROTECTED_OWNER_EXCLUDED_SOURCE');
   const deliveryExcluded=await request('POST',deliverPath,'owner',{
     requestId:'delivery-excluded',answer:deliveryText});
   assert.equal(deliveryExcluded.status,409);
   assert.ok(!JSON.stringify(deliveryExcluded.body).includes(deliveryText));
   const groundedExcluded=await request('POST',groundedPath,'owner',{
     requestId:'grounded-excluded'});
   assert.equal(groundedExcluded.status,409);
   assert.ok(!JSON.stringify(groundedExcluded.body).includes(SOURCE));
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:true,reason:'OWNER_SELECTION'});
   content=SOURCE+'\nAppended after custodian signature.';
   const changed=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(changed.status,409);
   assert.equal(changed.body.error,'PROTECTED_LIVE_SOURCE_REVISION_MISMATCH');
   const useChanged=await request('POST',usePath,'owner',useInput());
   assert.equal(useChanged.status,409);
   assert.equal(useChanged.body.error,'PROTECTED_LIVE_SOURCE_REVISION_MISMATCH');
   const deliveryChanged=await request('POST',deliverPath,'owner',{
     requestId:'delivery-changed',answer:deliveryText});
   assert.equal(deliveryChanged.status,409);
   assert.ok(!JSON.stringify(deliveryChanged.body).includes(deliveryText));
   const groundedChanged=await request('POST',groundedPath,'owner',{
     requestId:'grounded-changed'});
   assert.equal(groundedChanged.status,409);
   assert.ok(!JSON.stringify(groundedChanged.body).includes(SOURCE));
   content=SOURCE;
   remoteAccess=false;
   const revoked=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(revoked.status,409);
   assert.equal(revoked.body.error,'PROTECTED_LIVE_GOOGLE_VERIFICATION_FAILED');
   assert.equal(fs.existsSync(index.location(subject)),false);
   assert.equal((await request('POST',usePath,'owner',useInput())).status,409);
   remoteAccess=true;
   await index.sync(subject,connector);
   const wrongLine=await request('POST',endpoint,'owner',payload(att({lineText:'NOT THE FILE LINE'})));
   assert.equal(wrongLine.status,409);
   assert.equal(wrongLine.body.error,'PROTECTED_SOURCE_LINE_CHANGED');
   const unknownScope=await request('POST',endpoint,'owner',{
     ...payload(att()),environment:'legacy'
   });
   assert.equal(unknownScope.status,403);
   // A stale local snapshot is never accepted merely because both
   // human signatures still happen to be within their short validity window.
   index.now=()=>Date.now()+61*60*1000;
   const staleAttempt=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(staleAttempt.status,409);
   assert.equal(staleAttempt.body.error,'PROTECTED_SOURCE_INDEX_STALE');
   const staleUse=await request('POST',usePath,'owner',useInput());
   assert.equal(staleUse.status,409);
   assert.equal(staleUse.body.error,'PROTECTED_SOURCE_INDEX_STALE');
   index.now=()=>Date.now();
   // A new approved PackSpec binding invalidates old signed approvals.
   registry.draft({id:'changed-policy',version:'1',requirements:[
     {id:'approval',min_independent_sources:1}
   ]},'separate-author');
   registry.approve('changed-policy','1','separate-policy-approver');
   registry.bind('claims','dev','changed-policy','1','publisher');
   const invalidOldPolicy=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(invalidOldPolicy.status,403);
   assert.equal(invalidOldPolicy.body.error,'PROTECTED_REVIEW_POLICY_MISMATCH');
   const outdatedUse=await request('POST',usePath,'owner',useInput());
   assert.equal(outdatedUse.status,409);
   assert.equal(outdatedUse.body.error,'PROTECTED_USE_POLICY_CHANGED');
   const deliveryOutdated=await request('POST',deliverPath,'owner',{
     requestId:'delivery-outdated',answer:deliveryText});
   assert.equal(deliveryOutdated.status,409);
   assert.ok(!JSON.stringify(deliveryOutdated.body).includes(deliveryText));
   // The current bridge deliberately cannot prove independent intellectual
   // origins or when the original document was actually published.
   registry.draft({id:'multi-source-policy',version:'1',requirements:[
     {id:'approval',min_independent_sources:2}
   ]},'separate-author');
   registry.approve('multi-source-policy','1','separate-policy-approver');
   registry.bind('claims','dev','multi-source-policy','1','publisher');
   const changedPackDigest=registry.resolve('claims','dev').sha256;
   const multi=await request('POST',endpoint,'owner',payload(
     att({policySha256:changedPackDigest})));
   assert.equal(multi.status,409);
   assert.equal(multi.body.error,'PROTECTED_POLICY_REQUIRES_UNSUPPORTED_PROOF');
   registry.draft({id:'source-age-policy',version:'1',requirements:[
     {id:'approval',min_independent_sources:1,max_age_seconds:60}
   ]},'separate-author');
   registry.approve('source-age-policy','1','separate-policy-approver');
   registry.bind('claims','dev','source-age-policy','1','publisher');
   const freshness=await request('POST',endpoint,'owner',payload(
     att({policySha256:registry.resolve('claims','dev').sha256})));
   assert.equal(freshness.status,409);
   assert.equal(freshness.body.error,'PROTECTED_POLICY_REQUIRES_UNSUPPORTED_PROOF');

   const list=ledger.list('claims','dev');
   assert.equal(list.summary.protectedDecisions,3);
   assert.equal(list.summary.protectedAdmitted,2);
   assert.equal(list.summary.protectedRevocations,1);
   assert.equal(list.summary.protectedUses,3);
   assert.equal(list.summary.protectedGroundedReleases,1);
   const auditBytes=fs.readFileSync(ledgerPath,'utf8');
   assert.ok(!auditBytes.includes(answerText));
   assert.ok(!auditBytes.includes(deliveryText));
   assert.ok(!auditBytes.includes(grounded.body.answer));
   assert.ok(!auditBytes.includes(SOURCE.split('\\n')[0]));
   assert.ok(auditBytes.includes(answerSha256));
   assert.equal(list.summary.protectedInconclusive,0);
   assert.equal(list.observedCount,0);
   const persisted=fs.readFileSync(ledgerPath,'utf8');
   assert.equal(persisted.includes('Owner-approved policy: contractors'),false);
   assert.equal(persisted.includes('All other reimbursements need approval'),false);
   assert.equal(new EvidenceLedger(ledgerPath).list('claims','dev').summary.protectedAdmitted,2);
 }finally{
   await new Promise(ok=>server.close(ok));
   fs.rmSync(dir,{recursive:true,force:true});
 }
});

test('customer offline preparation and two independent Python signing commands produce Node-verifiable attestations',()=>{
 const availability=spawnSync('python',['--version'],{encoding:'utf8'});
 if(availability.status!==0)return;
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-review-signer-'));
 const script=fileURLToPath(new URL('../../../tools/packspec_compiler/prepare_protected_drive_review.py',import.meta.url));
 const source=path.join(dir,'reviewed-source.txt');
 const payload=path.join(dir,'review.json');
 const custodianSigned=path.join(dir,'custody.json');
 const meaningSigned=path.join(dir,'meaning.json');
 const transport=path.join(dir,'transport.json');
 const origin='org_'+'a'.repeat(32),id='google_drive/'+'b'.repeat(32);
 const digest='c'.repeat(64),folder='reviewed-folder';
 const custKey=path.join(dir,'private-custodian.pem');
 const meanKey=path.join(dir,'private-meaning.pem');
 fs.writeFileSync(source,'Approved clause for a synthetic policy.\\n');
 fs.writeFileSync(custKey,custodial.privateKey.export({type:'pkcs8',format:'pem'}),{mode:0o600});
 fs.writeFileSync(meanKey,meaningReview.privateKey.export({type:'pkcs8',format:'pem'}),{mode:0o600});
 const run=args=>{
   const r=spawnSync('python',[script,...args],{encoding:'utf8'});
   assert.equal(r.status,0,r.stdout+'\\n'+r.stderr);
 };
 try{
   run(['prepare','--service','claims','--environment','dev',
     '--policy-sha',digest,'--owner-subject',subject,'--folder-id',folder,
     '--source-id',id,'--requirement-id','approval','--origin',origin,
     '--line-number','1','--status','SUPPORTS',
     '--source',source,'--out',payload]);
   run(['sign','--role','custodian','--payload',payload,
     '--private-key',custKey,'--key-id','customer-custodian-2026',
     '--attest-reviewed','--out',custodianSigned]);
   run(['sign','--role','meaningReviewer','--payload',payload,
     '--private-key',meanKey,'--key-id','customer-meaning-reviewer-2026',
     '--attest-reviewed','--out',meaningSigned]);
   run(['build-request','--custody',custodianSigned,'--meaning',meaningSigned,
     '--request-id','request-validated','--trace-id','trace-validated',
     '--out',transport]);
   const client=JSON.parse(fs.readFileSync(transport,'utf8'));
   const verified=verifyHumanReviewAttestations(client.custody,client.meaning,trust(),{
     serviceId:'claims',environment:'dev',policySha256:digest,
     subject,folderId:folder
   });
   assert.equal(verified.payload.witnesses[0].sourceId,id);
   assert.equal(verified.payload.witnesses[0].status,'SUPPORTS');
   assert.equal(verified.signerIds.length,2);
   const unsignedPath=path.join(dir,'unsigned-approval.json');
   const denied=spawnSync('python',[script,'sign','--role','meaningReviewer',
     '--payload',payload,'--private-key',meanKey,
     '--key-id','customer-meaning-reviewer-2026','--out',unsignedPath],
     {encoding:'utf8'});
   assert.equal(denied.status,2);
   assert.equal(fs.existsSync(unsignedPath),false);
 }finally{fs.rmSync(dir,{recursive:true,force:true})}
});
