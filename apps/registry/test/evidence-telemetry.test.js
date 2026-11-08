import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {EvidenceLedger,evaluateEvidence} from '../src/evidence-ledger.js';
import {RegistryStore} from '../src/store.js';
import {createHandler} from '../src/server.js';
import {permissionFor} from '../src/oidc.js';

const E=(i,req,org='org_'+('a'.repeat(32)),status='SUPPORTS',ago=60000)=>({
  id:'ev_'+i.toString(16).padStart(32,'0'),requirement_id:req,origin:org,
  source_ref:'src_'+i.toString(16).padStart(32,'0'),status,
  observed_at:new Date(Date.now()-ago).toISOString()
});
const PACK={id:'acceptance',version:'1',requirements:[{id:'independent',min_independent_sources:2}]};

test('gate reproduces origin-deduplication, contradiction, freshness and missingness',()=>{
 const t=new Date().toISOString();
 assert.equal(evaluateEvidence(PACK,[E(1,'independent'),E(2,'independent')],t).verdict,'INCONCLUSIVE');
 assert.equal(evaluateEvidence(PACK,[E(1,'independent'),E(2,'independent','org_'+('b'.repeat(32)))],t).verdict,'ADMIT');
 assert.equal(evaluateEvidence(PACK,[E(1,'independent'),E(2,'independent','org_'+('b'.repeat(32)),'CONTRADICTS')],t).verdict,'REFUSE');
 const freshness={id:'fresh',version:'1',requirements:[{id:'independent',max_age_seconds:1}]};
 const stale=evaluateEvidence(freshness,[E(1,'independent',undefined,'SUPPORTS',120000)],t);
 assert.equal(stale.verdict,'INCONCLUSIVE');
 assert.ok(stale.findings[0].reasons.includes('STALE_EVIDENCE'));
});

test('role authorization, real HTTP ingestion, replay, review, idempotency and corruption detection',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-evidence-'));
 const file=path.join(dir,'evidence.jsonl');
 const reg=new RegistryStore(path.join(dir,'registry.json'));
 reg.register({id:'claims-api',displayName:'Claims'},'setup');
 reg.draft(PACK,'setup');reg.approve(PACK.id,PACK.version,'approver');
 reg.bind('claims-api','dev',PACK.id,PACK.version,'publisher');
 const ledger=new EvidenceLedger(file);
 const identities={
  ingester:{roles:['evidence.ingest'],services:['claims-api@dev']},
  reader:{roles:['evidence.reader'],services:['claims-api@dev']},
  reviewer:{roles:['evidence.reviewer'],services:['claims-api@dev']},
  super_ingester:{roles:['evidence.ingest','evidence.reviewer'],services:['claims-api@dev']},
  other:{roles:['evidence.reader'],services:['unrelated@prod']}
 };
 const authenticate=async token=>{
  const identity=identities[token];
  return identity?{subject:token,roles:new Set(identity.roles),evidenceServices:new Set(identity.services)}:null;
 };
 const httpServer=http.createServer(createHandler(reg,null,{authenticate,evidenceLedger:ledger}));
 await new Promise(ok=>httpServer.listen(0,'127.0.0.1',ok));
 const base='http://127.0.0.1:'+httpServer.address().port;
 const request=async(method,route,token,payload)=>{
  const r=await fetch(base+route,{method,headers:{
   Authorization:'Bearer '+token,'Content-Type':'application/json'},
   body:payload===undefined?undefined:JSON.stringify(payload)});
  return {status:r.status,body:await r.json()};
 };
 try{
  const data={serviceId:'claims-api',environment:'dev',requestId:'request-001',traceId:'trace-001',
    evidence:[E(1,'independent'),E(2,'independent')]};
  const x=await request('POST','/v1/evidence/evaluations','ingester',data);
  assert.equal(x.status,201,JSON.stringify(x.body));
  assert.equal(x.body.verdict,'INCONCLUSIVE');
  assert.equal(x.body.findings[0].independent_sources,1);
  assert.equal(x.body.declaredOriginsOnly,true);
  assert.equal(x.body.evidence.length,2);
  const query='/v1/evidence/evaluations?serviceId=claims-api&environment=dev';
  assert.equal((await request('GET',query,'ingester')).status,403);
  assert.equal((await request('GET',query,'other')).status,403);
  const read=await request('GET',query,'reader');
  assert.equal(read.status,200);
  assert.equal(read.body.observedCount,1);
  assert.equal(read.body.summary.inconclusive,1);
  assert.equal(read.body.summary.accepted,0);
  assert.equal(read.body.coverage,'UNKNOWN');
  assert.equal((await request('POST','/v1/evidence/evaluations','ingester',data)).body.id,x.body.id);
  assert.equal((await request('POST','/v1/evidence/evaluations','ingester',
    {...data,evidence:[E(1,'independent')] })).status,409);
  assert.equal((await request('POST','/v1/evidence/evaluations','ingester',
    {...data,requestId:'request-new',prompt:'customer secret'})).status,400);
  const exportPath='/v1/evidence/evaluations/'+x.body.id+'/export';
  const packageReply=await request('GET',exportPath,'reader');
  assert.equal(packageReply.status,200,JSON.stringify(packageReply.body));
  assert.equal(packageReply.body.payload.schema,'qualityrag.evidence-replay/v1');
  assert.equal(packageReply.body.payload.policy.id,PACK.id);
  assert.equal(packageReply.body.payload.policy.requirements[0].min_independent_sources,2);
  assert.equal(packageReply.body.payload.expectedResult.verdict,'INCONCLUSIVE');
  assert.equal(packageReply.body.payload.evidence.length,2);
  assert.equal(packageReply.body.integrity.digitallySigned,false);
  assert.equal(packageReply.body.integrity.externallyAnchored,false);
  assert.equal(packageReply.body.integrity.authenticityVerified,false);
  assert.match(packageReply.body.integrity.sha256,/^[a-f0-9]{64}$/);
  assert.equal((await request('GET',exportPath,'other')).status,403);
  assert.equal(permissionFor('GET',exportPath),'evidence.reader');
  const replay=await request('POST','/v1/evidence/evaluations/'+x.body.id+'/replay','reader');
  assert.equal(replay.status,200);
  assert.equal(replay.body.reproduced,true);
  assert.equal(replay.body.verdict,'INCONCLUSIVE');
  assert.equal((await request('POST','/v1/evidence/evaluations/'+x.body.id+'/reviews','reader',
    {decision:'ACCEPTED',reasonCode:'REPRODUCED'})).status,403);
  const review=await request('POST','/v1/evidence/evaluations/'+x.body.id+'/reviews','reviewer',
    {decision:'DISPUTED',reasonCode:'POLICY_DISAGREEMENT',note:'Reviewer disputes the contract mapping'});
  assert.equal(review.status,201,JSON.stringify(review.body));
  assert.equal(review.body.replayReproduced,true);
  const revised=await request('GET','/v1/evidence/evaluations/'+x.body.id,'reader');
  assert.equal(revised.body.reviewHistory[0].decision,'DISPUTED');
  assert.equal(revised.body.verdict,'INCONCLUSIVE'); // adjudication never changes deterministic verdict
  const afterReview=await request('GET',query,'reader');
  assert.equal(afterReview.body.summary.disputed,1);
  assert.equal(afterReview.body.summary.unreviewed,0);
  assert.equal((await request('GET','/v1/evidence/evaluations/'+x.body.id,'other')).status,403);
  const selfData={...data,requestId:'request-super'};
  const self=await request('POST','/v1/evidence/evaluations','super_ingester',selfData);
  assert.equal(self.status,201);
  assert.equal((await request('POST','/v1/evidence/evaluations/'+self.body.id+'/reviews','super_ingester',
    {decision:'ACCEPTED',reasonCode:'REPRODUCED'})).status,403);
  assert.equal(permissionFor('GET','/v1/evidence/evaluations'), 'evidence.reader');
  assert.equal(permissionFor('POST','/v1/evidence/evaluations'), 'evidence.ingest');
  assert.equal(permissionFor('POST','/v1/evidence/evaluations/'+x.body.id+'/reviews'),'evidence.reviewer');
 }finally{
  await new Promise(ok=>httpServer.close(ok));
  const rows=fs.readFileSync(file,'utf8').split('\n').filter(Boolean);
  const tampered=JSON.parse(rows[0]);
  tampered.result.verdict='ADMIT';rows[0]=JSON.stringify(tampered);
  fs.writeFileSync(file,rows.join('\n')+'\n');
  assert.throws(()=>new EvidenceLedger(file),/EVIDENCE_LEDGER_INTEGRITY_FAILURE/);
  fs.rmSync(dir,{recursive:true,force:true});
 }
});
