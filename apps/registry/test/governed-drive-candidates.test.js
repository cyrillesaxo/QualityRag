import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {randomBytes} from 'node:crypto';
import {RegistryStore} from '../src/store.js';
import {createHandler} from '../src/server.js';
import {UserDriveIndex} from '../src/user-drive-index.js';
import {EvidenceLedger} from '../src/evidence-ledger.js';
import {permissionFor} from '../src/oidc.js';

test('governed Drive candidates fail closed on owner exclusion, stale revisions, wrong scope and unreviewed semantics',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-drive-governed-'));
 let now=Date.now();
 const index=new UserDriveIndex({dir:path.join(dir,'index'),
   encryptionKey:randomBytes(32).toString('base64'),now:()=>now});
 const subjects={alice:'https://issuer#alice',bob:'https://issuer#bob'};
 const connector={
   status:subject=>({connected:true,email:subject===subjects.alice?'alice@test.local':'bob@test.local',
     folderId:subject===subjects.alice?'folder-alice':'folder-bob'}),
   selectedFiles:async subject=>({truncated:false,files:[{
     id:subject===subjects.alice?'alice-policy':'bob-policy',
     name:subject===subjects.alice?'Claims policy.txt':'Bob confidential policy.txt',
     mimeType:'text/plain'
   }]}),
   supportsText:()=>true,
   downloadSelectedText:async(subject)=>Buffer.from(subject===subjects.alice?
     'Claims require approval.\nAn exception applies to contractors.':
     'Bob only document.\nSeparate private rules.')
 };
 const store=new RegistryStore(path.join(dir,'registry.json'));
 store.register({id:'claims-app',displayName:'Claims assistant'},'setup');
 store.draft({id:'claims-policy',version:'1',requirements:[
   {id:'approval',min_independent_sources:1},
   {id:'exception',min_independent_sources:1}
 ]},'setup');
 store.approve('claims-policy','1','reviewer');
 store.bind('claims-app','dev','claims-policy','1','publisher');
 const actors={
   alice:{subject:subjects.alice,roles:new Set(['drive.reader','drive.manager','evidence.reader']),
     evidenceServices:new Set(['claims-app@dev'])},
   aliceReviewer:{subject:subjects.alice,
     roles:new Set(['drive.reader','evidence.reader','evidence.reviewer']),
     evidenceServices:new Set(['claims-app@dev'])},
   bob:{subject:subjects.bob,roles:new Set(['drive.reader','drive.manager','evidence.reader']),
     evidenceServices:new Set(['claims-app@dev'])},
   insufficient:{subject:subjects.alice,roles:new Set(['drive.reader']),
     evidenceServices:new Set(['claims-app@dev'])},
   unscoped:{subject:subjects.alice,roles:new Set(['drive.reader','evidence.reader']),
     evidenceServices:new Set(['other-app@dev'])},
   outsider:{subject:subjects.alice,roles:new Set(['evidence.reader']),
     evidenceServices:new Set(['claims-app@dev'])}
 };
 const ledgerPath=path.join(dir,'governed-evidence.jsonl');
 const ledger=new EvidenceLedger(ledgerPath);
 const handler=createHandler(store,null,{
   authenticate:async token=>actors[token]||null,driveManager:connector,
   driveIndex:index,evidenceLedger:ledger
 });
 const server=http.createServer(handler);
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const root='http://127.0.0.1:'+server.address().port;
 const request=async(method,route,token,body)=>{
   const response=await fetch(root+route,{method,
     headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
     body:body===undefined?undefined:JSON.stringify(body)});
   return {status:response.status,body:await response.json()};
 };
 try{
   assert.equal(permissionFor('POST','/v1/drives/google/governed-check'),'drive.reader');
   assert.equal(permissionFor('POST','/v1/drives/google/record-check'),'drive.reader');
   assert.equal(permissionFor('GET','/v1/drives/google/governed-requirements'),'drive.reader');
   const requirements='/v1/drives/google/governed-requirements?serviceId=claims-app&environment=dev';
   assert.equal((await request('GET',requirements,'insufficient')).status,403);
   assert.equal((await request('GET',requirements,'unscoped')).status,403);
   assert.equal((await request('GET',requirements,'outsider')).status,403);
   const approved=await request('GET',requirements,'alice');
   assert.equal(approved.status,200,JSON.stringify(approved.body));
   assert.deepEqual(approved.body.requirements.map(x=>x.id),['approval','exception']);
   assert.equal(approved.body.policy.id,'claims-policy');
   assert.equal(approved.body.admissionStatus,'NOT_EVALUATED');
   await index.sync(subjects.alice,connector);
   await index.sync(subjects.bob,connector);
   const a=index.search(subjects.alice,connector.status(subjects.alice),'Claims require').hits[0];
   const b=index.search(subjects.bob,connector.status(subjects.bob),'Bob only').hits[0];
   const checkPath='/v1/drives/google/governed-check';
   const input=(candidate)=>({serviceId:'claims-app',environment:'dev',candidates:[candidate]});
   const candidate={sourceId:a.source_id,revision:a.revision,requirementId:'approval',lineNumber:1};
   const good=await request('POST',checkPath,'alice',input(candidate));
   assert.equal(good.status,200,JSON.stringify(good.body));
   assert.equal(good.body.result,'INCONCLUSIVE');
   assert.equal(good.body.policy.version,'1');
   assert.equal(good.body.observations[0].eligibleForReviewedEvidence,true);
   assert.ok(good.body.observations[0].reasons.includes('SEMANTIC_SUPPORT_NOT_VERIFIED'));
   assert.equal(good.body.evaluationAdmitted,false);
   assert.equal(good.body.telemetry.recorded,false);
   assert.equal(good.body.telemetry.receiptId,null);
   const recordPath='/v1/drives/google/record-check';
   assert.equal((await request('POST',recordPath,'alice',input(candidate))).status,403);
   assert.equal((await request('POST',recordPath,'unscoped',input(candidate))).status,403);
   assert.equal(ledger.list('claims-app','dev').summary.governedCandidateChecks,0);
   const signedReview=await request('POST',recordPath,'aliceReviewer',input(candidate));
   assert.equal(signedReview.status,200);
   assert.equal(signedReview.body.telemetry.recorded,true);
   assert.match(signedReview.body.telemetry.receiptId,/^[a-f0-9-]{36}$/);
   assert.equal(good.body.telemetry.externallyAnchored,false);
   assert.equal(good.body.independentProvenanceVerified,false);
   assert.equal((await request('POST',checkPath,'insufficient',input(candidate))).status,403);
   assert.equal((await request('POST',checkPath,'unscoped',input(candidate))).status,403);
   assert.equal((await request('POST',checkPath,'outsider',input(candidate))).status,403);
   assert.equal((await request('POST',checkPath,'alice',input({...candidate,requirementId:'made-up'}))).status,400);
   assert.equal((await request('POST',checkPath,'alice',input({...candidate,
     revision:'0'.repeat(64)}))).body.observations[0].reasons[0],'SOURCE_REVISION_MISMATCH');
   assert.equal((await request('POST',checkPath,'alice',input({...candidate,lineNumber:99})))
     .body.observations[0].reasons[0],'ANCHOR_NOT_IN_EXTRACTED_TEXT');
   const cross=await request('POST',checkPath,'alice',input({
     sourceId:b.source_id,revision:b.revision,requirementId:'approval',lineNumber:1
   }));
   assert.equal(cross.body.result,'INCONCLUSIVE');
   assert.equal(cross.body.observations[0].reasons[0],'SOURCE_NOT_IN_SELECTED_INDEX');
   assert.ok(!JSON.stringify(cross.body).includes('Bob confidential'));
   const reject=await request('POST','/v1/drives/google/source-control','alice',
     {sourceId:a.source_id,searchable:false,reason:'SENSITIVE'});
   assert.equal(reject.status,200);
   const excluded=await request('POST',checkPath,'alice',input(candidate));
   assert.equal(excluded.body.result,'REFUSE');
   assert.equal(excluded.body.counters.ownerExcluded,1);
   assert.equal(excluded.body.telemetry.recorded,false);
   const deniedReview=await request('POST',recordPath,'aliceReviewer',input(candidate));
   assert.equal(deniedReview.status,200);
   assert.equal(deniedReview.body.result,'REFUSE');
   assert.equal(deniedReview.body.telemetry.recorded,true);
   assert.equal(excluded.body.observations[0].reasons[0],'SOURCE_EXCLUDED_BY_OWNER');
   now+=61*60*1000;
   assert.equal((await request('POST',checkPath,'alice',input(candidate)))
     .body.observations[0].reasons[0],'SOURCE_EXCLUDED_BY_OWNER');
   assert.equal((await request('POST',checkPath,'alice',
     input({...candidate,revision:'0'.repeat(64)})))
     .body.observations[0].reasons[0],'SOURCE_EXCLUDED_BY_OWNER');
   now-=61*60*1000;
   // An attacker cannot override exclusion by including arbitrary evidence fields.
   assert.equal((await request('POST',checkPath,'alice',{
     ...input(candidate),override:true})).status,400);
   await index.sync(subjects.alice,connector);
   assert.equal((await request('POST',checkPath,'alice',input(candidate)))
     .body.observations[0].reasons[0],'SOURCE_EXCLUDED_BY_OWNER');
   await request('POST','/v1/drives/google/source-control','alice',
     {sourceId:a.source_id,searchable:true,reason:'OWNER_SELECTION'});
   assert.equal((await request('POST',checkPath,'alice',input(candidate))).body.result,'INCONCLUSIVE');
   now+=61*60*1000;
   const stale=await request('POST',checkPath,'alice',input(candidate));
   assert.equal(stale.body.result,'INCONCLUSIVE');
   assert.equal(stale.body.observations[0].reasons[0],'INDEX_STALE');
   now-=61*60*1000;
   index.clear(subjects.alice);
   const erased=await request('POST',checkPath,'alice',input(candidate));
   assert.equal(erased.body.result,'INCONCLUSIVE');
   assert.equal(erased.body.observations[0].reasons[0],'NO_CURRENT_INDEX');
   const recorded=ledger.list('claims-app','dev');
   assert.equal(recorded.summary.governedCandidateChecks,2);
   assert.equal(recorded.summary.governedCandidateRefusals,1);
   assert.equal(recorded.observedCount,0);
   const bytes=fs.readFileSync(ledgerPath,'utf8');
   assert.ok(!bytes.includes('An exception applies to contractors'));
   assert.ok(!bytes.includes('Bob only document'));
   assert.ok(!bytes.includes(a.source_id));
   assert.ok(!bytes.includes(b.source_id));
   assert.ok(!bytes.includes(a.revision));
   assert.equal(new EvidenceLedger(ledgerPath).list('claims-app','dev')
     .summary.governedCandidateChecks,recorded.summary.governedCandidateChecks);
 }finally{
   await new Promise(resolve=>server.close(resolve));
   fs.rmSync(dir,{recursive:true,force:true});
 }
});
