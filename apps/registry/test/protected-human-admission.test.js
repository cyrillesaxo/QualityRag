import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {createHash,createKeyPairSync,generateKeyPairSync,sign as edSign} from 'node:crypto';
import {randomBytes} from 'node:crypto';
import {RegistryStore} from '../src/store.js';
import {EvidenceLedger} from '../src/evidence-ledger.js';
import {UserDriveIndex} from '../src/user-drive-index.js';
import {createHandler} from '../src/server.js';
import {loadProtectedReviewTrust,reviewCanonical} from '../src/protected-admission.js';
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
   const exportUrl='/v1/evidence/protected-decisions/'+admit.body.id+'/export';
   assert.equal((await request('GET',exportUrl,'other')).status,403);
   assert.equal((await request('GET',exportUrl,'missingDrive')).status,403);
   assert.equal((await request('GET',exportUrl,'missingIngest')).status,403);
   const exported=await request('GET',exportUrl,'owner');
   assert.equal(exported.status,200);
   assert.equal(exported.body.schema,'qualityrag.protected-drive-decision-replay/v1');
   assert.equal(exported.body.signedCustody.signature,admittedPayload.custody.signature);
   assert.equal(exported.body.result.verdict,'ADMIT');
   assert.equal(exported.body.sourceTruthProven,false);
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
   // An explicitly blocked source cannot be admitted even with two real signatures.
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:false,reason:'OUT_OF_SCOPE'});
   const denied=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(denied.status,409,JSON.stringify(denied.body));
   assert.equal(denied.body.error,'PROTECTED_OWNER_EXCLUDED_SOURCE');
   index.controlSource(subject,connector.status(subject),{
     sourceId:hit.source_id,searchable:true,reason:'OWNER_SELECTION'});
   content=SOURCE+'\nAppended after custodian signature.';
   const changed=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(changed.status,409);
   assert.equal(changed.body.error,'PROTECTED_LIVE_SOURCE_REVISION_MISMATCH');
   content=SOURCE;
   remoteAccess=false;
   const revoked=await request('POST',endpoint,'owner',payload(att()));
   assert.equal(revoked.status,409);
   assert.equal(revoked.body.error,'PROTECTED_LIVE_GOOGLE_VERIFICATION_FAILED');
   assert.equal(fs.existsSync(index.location(subject)),false);
   remoteAccess=true;
   await index.sync(subject,connector);
   const wrongLine=await request('POST',endpoint,'owner',payload(att({lineText:'NOT THE FILE LINE'})));
   assert.equal(wrongLine.status,409);
   assert.equal(wrongLine.body.error,'PROTECTED_SOURCE_LINE_CHANGED');
   const unknownScope=await request('POST',endpoint,'owner',{
     ...payload(att()),environment:'legacy'
   });
   assert.equal(unknownScope.status,403);
   const list=ledger.list('claims','dev');
   assert.equal(list.summary.protectedDecisions,2);
   assert.equal(list.summary.protectedAdmitted,1);
   assert.equal(list.summary.protectedInconclusive,0);
   assert.equal(list.observedCount,0);
   const persisted=fs.readFileSync(ledgerPath,'utf8');
   assert.equal(persisted.includes('Owner-approved policy: contractors'),false);
   assert.equal(persisted.includes('All other reimbursements need approval'),false);
   assert.equal(new EvidenceLedger(ledgerPath).list('claims','dev').summary.protectedAdmitted,1);
 }finally{
   await new Promise(ok=>server.close(ok));
   fs.rmSync(dir,{recursive:true,force:true});
 }
});
