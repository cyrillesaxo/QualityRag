#!/usr/bin/env node
// Actual local HTTP proof, synthetic Google provider, ephemeral signer keys.
// Only trust the claim that this demo *exercises the code*. Real customers
// must independently review provenance, contents, keys and the policy.
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash,randomBytes,generateKeyPairSync,sign} from 'node:crypto';
import {RegistryStore} from '../apps/registry/src/store.js';
import {EvidenceLedger} from '../apps/registry/src/evidence-ledger.js';
import {UserDriveIndex} from '../apps/registry/src/user-drive-index.js';
import {createHandler} from '../apps/registry/src/server.js';
import {reviewCanonical} from '../apps/registry/src/protected-admission.js';

const sha=text=>createHash('sha256').update(text).digest('hex');
const domain=Buffer.from('QUALITYRAG/qualityrag.signed-observations/v1\0','ascii');
const root=path.dirname(fileURLToPath(import.meta.url));
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-human-admit-show-me-'));
const owner='demo-issuer#owner-01';
const SOURCE='Required approval is documented in this synthetic company policy.\n';
let contents=SOURCE;
const serviceId='customer-claims',environment='demo';
const connector={
 status:()=>({connected:true,email:'synthetic-owner@example.invalid',folderId:'reviewed-policies'}),
 selectedFiles:async()=>({truncated:false,files:[{
   id:'synthetic-policy-file',name:'Synthetic customer policy.txt',mimeType:'text/plain'}]}),
 supportsText:()=>true,
 downloadSelectedText:async()=>Buffer.from(contents)
};
const pack={id:'customer-approved-contract',version:'1',
 requirements:[{id:'documented-approval',min_independent_sources:1}]};
const registry=new RegistryStore(path.join(dir,'registry.json'));
registry.register({id:serviceId,displayName:'Synthetic customer claims'},'setup');
registry.draft(pack,'policy-author');registry.approve(pack.id,pack.version,'independent-reviewer');
registry.bind(serviceId,environment,pack.id,pack.version,'publisher');
const ledger=new EvidenceLedger(path.join(dir,'evidence.jsonl'));
const index=new UserDriveIndex({dir:path.join(dir,'index'),
 encryptionKey:randomBytes(32).toString('base64')});
const custodyKeys=generateKeyPairSync('ed25519');
const semanticKeys=generateKeyPairSync('ed25519');
const publicTrust={
 custodian:{keyId:'demo-custodian',
   key:custodyKeys.publicKey},
 meaningReviewer:{keyId:'demo-semantic-reviewer',
   key:semanticKeys.publicKey}
};
const server=http.createServer(createHandler(registry,null,{
 authenticate:async t=>t==='demo-owner'?{
   subject:owner,roles:new Set(['drive.reader','drive.manager','evidence.ingest','evidence.reader']),
   evidenceServices:new Set([serviceId+'@'+environment])}:
   t==='demo-owner-reviewer'?{
   subject:owner,roles:new Set(['drive.reader','drive.manager','evidence.reviewer','evidence.reader']),
   evidenceServices:new Set([serviceId+'@'+environment])}:null,
 driveManager:connector,driveIndex:index,evidenceLedger:ledger,
 protectedDriveServices:new Set([serviceId+'@'+environment]),
 protectedReviewTrust:publicTrust
}));
async function request(method,route,payload,token='demo-owner'){
 const response=await fetch('http://127.0.0.1:'+server.address().port+route,{
   method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
   body:payload===undefined?undefined:JSON.stringify(payload)
 });
 return {status:response.status,body:await response.json()};
}
function envelope(payload,role){
 const keys=role==='custodian'?custodyKeys:semanticKeys;
 const keyId=role==='custodian'?'demo-custodian':'demo-semantic-reviewer';
 return {schema:'qualityrag.signed-observations/v1',canonical:'QR-CJSON-1',
   key_id:keyId,payload,signature:sign(null,
     Buffer.concat([domain,reviewCanonical(payload)]),keys.privateKey).toString('base64url')};
}
function signedRequest(hit,nonce){
 const now=Date.now(),digest=registry.resolve(serviceId,environment).sha256;
 const payload={
   service:serviceId,environment,
   policy_signature:'UNSIGNED-V0.1-PACK-SHA256:'+digest,
   nonce,issued_at:new Date(now).toISOString(),expires_at:new Date(now+300_000).toISOString(),
   witnesses:[{sourceId:hit.source_id,revision:hit.revision,
     lineNumber:hit.anchor.line_number,lineSha256:sha(SOURCE.split('\n')[0]),
     requirementId:'documented-approval',origin:'org_'+'f'.repeat(32),status:'SUPPORTS'}],
   observations:{kind:'qualityrag.protected-drive-human-review/v1',
     owner_binding:sha('qualityrag.review-owner/v1:'+owner),
     folder_id:'reviewed-policies',
     review_basis:'HUMAN_SEMANTIC_APPROVAL',origin_basis:'CUSTODIAN_ATTESTED'}
 };
 return {serviceId,environment,requestId:'request-'+nonce,traceId:'trace-'+nonce,
   custody:envelope(payload,'custodian'),meaning:envelope(payload,'meaningReviewer')};
}
try{
 await index.sync(owner,connector);
 const hit=index.search(owner,connector.status(owner),'Required approval').hits[0];
 assert.ok(hit);
 await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 const accepted=await request('POST','/v1/evidence/protected-admit',
   signedRequest(hit,'first-attestation-nonce'));
 assert.equal(accepted.status,201,JSON.stringify(accepted.body));
 assert.equal(accepted.body.result.verdict,'ADMIT');
 const receipt=await request('GET','/v1/evidence/protected-decisions/'+
   accepted.body.id+'/export');
 assert.equal(receipt.status,200);
 const groundedPath='/v1/evidence/protected-decisions/'+accepted.body.id+'/grounded-deliver';
 const ground=await request('POST',groundedPath,{
   requestId:'extract-demo-001'});
 assert.equal(ground.status,200,JSON.stringify(ground.body));
 assert.equal(ground.body.schema,'qualityrag.source-grounded-extract/v1');
 assert.equal(ground.body.delivery,'SERVER_GENERATED_EXTRACT_ONLY');
 assert.equal(ground.body.receipt.deliveryMode,'SOURCE_GROUNDED_EXTRACT');
 assert.equal(ground.body.receipt.answerSha256,sha(ground.body.answer));
 assert.equal(ground.body.coverage.allSignedAnchorsIncluded,true);
 assert.equal(ground.body.coverage.fullDocumentExaminedForExceptions,false);
 assert.ok(ground.body.answer.includes(SOURCE.trim().split('\n')[0]));
 assert.ok(ground.body.answer.includes(SOURCE.trim().split('\n')[1]));
 const usePath='/v1/evidence/protected-decisions/'+accepted.body.id+'/use-check';
 const answer='Synthetic model result guarded by customer-signed evidence.';
 const answerSha256=sha(answer);
 const useInput={requestId:'example-answer-001',answerSha256};
 const allowedUse=await request('POST',usePath,useInput);
 assert.equal(allowedUse.status,200,JSON.stringify(allowedUse.body));
 assert.equal(allowedUse.body.permission,'PERMIT_SIGNED_ASSERTION_USE');
 assert.equal(allowedUse.body.answerSha256,answerSha256);
 const deliverPath='/v1/evidence/protected-decisions/'+accepted.body.id+'/deliver';
 const delivered=await request('POST',deliverPath,{
   requestId:'example-buffered-answer-001',answer
 });
 assert.equal(delivered.status,200,JSON.stringify(delivered.body));
 assert.equal(delivered.body.schema,'qualityrag.protected-answer-delivery/v1');
 assert.equal(delivered.body.answer,answer);
 assert.equal(delivered.body.receipt.deliveryMode,'SERVER_BUFFERED_RELEASE');
 assert.equal(delivered.body.receipt.answerSha256,answerSha256);
 const replayDelivery=await request('POST',deliverPath,{
   requestId:'example-buffered-answer-001',answer
 });
 assert.equal(replayDelivery.status,409);
 assert.ok(!JSON.stringify(replayDelivery.body).includes(answer));
 const doubleUse=await request('POST',usePath,useInput);
 assert.equal(doubleUse.status,409);
 // Withdraw one human interpretation without excluding the source.
 const secondAccepted=await request('POST','/v1/evidence/protected-admit',
   signedRequest(hit,'third-attestation-nonce'));
 assert.equal(secondAccepted.status,201);
 const revocationPath='/v1/evidence/protected-decisions/'+secondAccepted.body.id+'/revoke';
 const withdrawn=await request('POST',revocationPath,
   {reason:'REVIEW_DISPUTED'},'demo-owner-reviewer');
 assert.equal(withdrawn.status,200,JSON.stringify(withdrawn.body));
 const useWithdrawn=await request('POST',
   '/v1/evidence/protected-decisions/'+secondAccepted.body.id+'/use-check',
   {requestId:'example-answer-withdrawn',answerSha256});
 assert.equal(useWithdrawn.status,409);
 assert.equal(useWithdrawn.body.error,'PROTECTED_DECISION_REVOKED');
 const revokedDelivery=await request('POST',
   '/v1/evidence/protected-decisions/'+secondAccepted.body.id+'/deliver',
   {requestId:'example-buffered-answer-revoked',answer});
 assert.equal(revokedDelivery.status,409);
 assert.ok(!JSON.stringify(revokedDelivery.body).includes(answer));
 index.controlSource(owner,connector.status(owner),{
   sourceId:hit.source_id,searchable:false,reason:'OUT_OF_SCOPE'
 });
 const excluded=await request('POST','/v1/evidence/protected-admit',
   signedRequest(hit,'second-attestation-nonce'));
 assert.equal(excluded.status,409);
 assert.equal(excluded.body.error,'PROTECTED_OWNER_EXCLUDED_SOURCE');
 const useAfterExclusion=await request('POST',usePath,
   {requestId:'example-answer-002',answerSha256});
 assert.equal(useAfterExclusion.status,409);
 assert.equal(useAfterExclusion.body.error,'PROTECTED_OWNER_EXCLUDED_SOURCE');
 const groundExcluded=await request('POST',groundedPath,{
   requestId:'extract-demo-excluded'});
 assert.equal(groundExcluded.status,409);
 assert.ok(!JSON.stringify(groundExcluded.body).includes(SOURCE.trim()));
 const deniedDelivery=await request('POST',deliverPath,{
   requestId:'example-buffered-answer-excluded',answer
 });
 assert.equal(deniedDelivery.status,409);
 assert.ok(!JSON.stringify(deniedDelivery.body).includes(answer));
 const persisted=fs.readFileSync(path.join(dir,'evidence.jsonl'),'utf8');
 assert.equal(persisted.includes(SOURCE.trim()),false);
 assert.equal(persisted.includes(answer),false);
 assert.equal(persisted.includes(ground.body.answer),false);

 // Independent Python validation sees the same two signatures, original
 // source bytes and a separately computed PackSpec decision.
 const trustFile=path.join(dir,'trusted-public-keys.json');
 fs.writeFileSync(trustFile,JSON.stringify({
   custodian:{keyId:'demo-custodian',
     publicKeyPem:custodyKeys.publicKey.export({type:'spki',format:'pem'})},
   meaningReviewer:{keyId:'demo-semantic-reviewer',
     publicKeyPem:semanticKeys.publicKey.export({type:'spki',format:'pem'})}
 }));
 const receiptFile=path.join(dir,'receipt.json');
 const sourceFile=path.join(dir,'source.txt');
 fs.writeFileSync(receiptFile,JSON.stringify(receipt.body));
 fs.writeFileSync(sourceFile,SOURCE);
 const verifier=path.join(root,'../tools/packspec_compiler/verify_protected_drive_receipt.py');
 const arguments_=[verifier,'--receipt',receiptFile,'--trust',trustFile,
   '--owner-subject',owner,'--folder-id','reviewed-policies',
   '--source',hit.source_id+'='+sourceFile];
 const checked=spawnSync('python',arguments_,{encoding:'utf8'});
 assert.equal(checked.status,0,checked.stdout+'\n'+checked.stderr);
 const result=JSON.parse(checked.stdout);
 assert.equal(result.independentReplayMatched,true);
 fs.writeFileSync(sourceFile,'Tampered file');
 const attack=spawnSync('python',arguments_,{encoding:'utf8'});
 assert.equal(attack.status,2,attack.stdout+'\n'+attack.stderr);
 console.log(JSON.stringify({
   demonstration:'SYNTHETIC HUMAN-REVIEWED PROTECTED ADMISSION',
   dualRoleSignaturesVerified:true,
   liveGoogleBytesChecked:true,
   signedCustomerAssertion:{http:accepted.status,verdict:accepted.body.verdict},
   ownerExclusion:{http:excluded.status,reason:excluded.body.error},
   sourceGroundedExtract:{http:ground.status,
     signedAnchorsIncluded:ground.body.coverage.allSignedAnchorsIncluded,
     adjacentContextVisible:ground.body.sections[0].adjacentContext.length>0,
     documentWideCompletenessVerified:false,
     afterOwnerExclusion:groundExcluded.body.error,
     originalSourceTextStoredInLedger:false},
   answerUseBeforeExclusion:{http:allowedUse.status,
     permission:allowedUse.body.permission,answerTextUploaded:false},
   answerUseAfterExclusion:{http:useAfterExclusion.status,
     reason:useAfterExclusion.body.error},
   controlledGateway:{deliveryHttp:delivered.status,
     exactAnswerReturned:delivered.body.answer===answer,
     recordedMode:delivered.body.receipt.deliveryMode,
     replayHttp:replayDelivery.status,
     exclusionHttp:deniedDelivery.status,
     revocationHttp:revokedDelivery.status,
     rawAnswerStoredInLedger:false},
   specificDecisionWithdrawal:{status:withdrawn.body.status,
     useAfterWithdrawal:useWithdrawn.body.error,
     sourceStillSearchableWhenWithdrawn:true},
   independentPython:{signatures:result.signatureCount,sourceBytesMatched:true,
     metadataVerdictReproduced:result.reportedVerdict},
   offlineTamperedFile:'REJECTED',
   sourceTextInLedger:false,
   productionReady:false,externallyAttested:false,
   limitations:['mock IdP and Google provider','ephemeral demo signing keys',
     'two distinct keys are not proof of distinct humans',
     'publisher truth and source independence not proved',
     'not a global downstream RAG enforcement mechanism']
 },null,2));
}finally{
 if(server.listening)await new Promise(ok=>server.close(ok));
 fs.rmSync(dir,{recursive:true,force:true});
}
