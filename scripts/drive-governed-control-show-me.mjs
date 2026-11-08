#!/usr/bin/env node
// A real local registry HTTP execution using synthetic documents and identities.
// This demonstrates owner source-control enforcement, not source truth or compliance.
import assert from 'node:assert/strict';
import http from 'node:http';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
import {RegistryStore} from '../apps/registry/src/store.js';
import {UserDriveIndex} from '../apps/registry/src/user-drive-index.js';
import {EvidenceLedger} from '../apps/registry/src/evidence-ledger.js';
import {createHandler} from '../apps/registry/src/server.js';

const directory=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-governed-drive-demo-'));
const subject='demo-issuer#customer-1';
const serviceId='claims-assistant';
const environment='test';
const connection={connected:true,email:'demo-customer@example.invalid',folderId:'demo-policies'};
const connector={
  status:()=>({...connection}),
  selectedFiles:async()=>({truncated:false,files:[
    {id:'demo-policy-file',name:'Synthetic policy.txt',mimeType:'text/plain'}]}),
  supportsText:()=>true,
  downloadSelectedText:async()=>Buffer.from('The policy has an exception.\nApproval is required.','utf8')
};
const index=new UserDriveIndex({dir:path.join(directory,'index'),
  encryptionKey:randomBytes(32).toString('base64')});
const store=new RegistryStore(path.join(directory,'registry.json'));
store.register({id:serviceId,displayName:'Synthetic claims assistant'},'setup');
store.draft({id:'claims-contract',version:'1',requirements:[
  {id:'governing-exception',min_independent_sources:1}
]},'setup');
store.approve('claims-contract','1','policy-reviewer');
store.bind(serviceId,environment,'claims-contract','1','publisher');

const authenticate=async(token)=>{
  if(token!=='demo-user')return null;
  return {subject,roles:new Set(['drive.reader','drive.manager','evidence.reader']),
    evidenceServices:new Set([serviceId+'@'+environment])};
};
const ledger=new EvidenceLedger(path.join(directory,'evidence.jsonl'));
const server=http.createServer(createHandler(store,null,{
  authenticate,driveManager:connector,driveIndex:index,evidenceLedger:ledger
}));
async function request(method,route,body){
  const response=await fetch('http://127.0.0.1:'+server.address().port+route,{
    method,headers:{Authorization:'Bearer demo-user','Content-Type':'application/json'},
    body:body===undefined?undefined:JSON.stringify(body)
  });
  const value=await response.json();
  assert.equal(response.status,200,JSON.stringify(value));
  return value;
}
try{
  await index.sync(subject,connector);
  const first=await index.search(subject,connection,'policy exception');
  assert.equal(first.hits.length,1);
  const hit=first.hits[0];
  const candidate={sourceId:hit.source_id,revision:hit.revision,
    requirementId:'governing-exception',lineNumber:hit.anchor.line_number};
  await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
  const uri='/v1/drives/google/governed-check';
  const body={serviceId,environment,candidates:[candidate]};
  const requirements=await request('GET',
    '/v1/drives/google/governed-requirements?serviceId='+serviceId+'&environment='+environment);
  assert.equal(requirements.requirements[0].id,'governing-exception');
  const before=await request('POST',uri,body);
  assert.equal(before.result,'INCONCLUSIVE');
  assert.equal(before.counters.eligibleForReview,1);
  assert.equal(before.telemetry.recorded,true);
  await request('POST','/v1/drives/google/source-control',{
    sourceId:hit.source_id,searchable:false,reason:'OUT_OF_SCOPE'});
  const afterExclusion=await request('POST',uri,body);
  assert.equal(afterExclusion.result,'REFUSE');
  assert.equal(afterExclusion.observations[0].reasons[0],'SOURCE_EXCLUDED_BY_OWNER');
  assert.equal(afterExclusion.telemetry.recorded,true);
  await index.sync(subject,connector);
  const afterResync=await request('POST',uri,body);
  assert.equal(afterResync.result,'REFUSE');
  await request('POST','/v1/drives/google/source-control',{
    sourceId:hit.source_id,searchable:true,reason:'OWNER_SELECTION'});
  const afterInclusion=await request('POST',uri,body);
  assert.equal(afterInclusion.result,'INCONCLUSIVE');
  index.clear(subject);
  const afterDeletion=await request('POST',uri,body);
  assert.equal(afterDeletion.result,'INCONCLUSIVE');
  assert.equal(afterDeletion.observations[0].reasons[0],'NO_CURRENT_INDEX');
  const checks=ledger.list(serviceId,environment);
  assert.equal(checks.summary.governedCandidateChecks,5);
  assert.equal(checks.summary.governedCandidateRefusals,2);
  assert.equal(checks.observedCount,0);
  const raw=fs.readFileSync(path.join(directory,'evidence.jsonl'),'utf8');
  assert.equal(raw.includes('The policy has an exception'),false);
  assert.equal(raw.includes(hit.source_id),false);
  console.log(JSON.stringify({
    demonstration:'SYNTHETIC REAL REGISTRY HTTP — PACKSPEC-BOUND SOURCE CONTROL',
    approvedPackSpec:requirements.policy.id+'@'+requirements.policy.version,
    initial:{decision:before.result,reasons:before.observations[0].reasons},
    ownerExcluded:{decision:afterExclusion.result,
      reasons:afterExclusion.observations[0].reasons},
    excludedAfterResync:{decision:afterResync.result},
    ownerIncludedAgain:{decision:afterInclusion.result,
      reasons:afterInclusion.observations[0].reasons},
    indexErased:{decision:afterDeletion.result,
      reasons:afterDeletion.observations[0].reasons},
    observedGuardTelemetry:{candidateChecks:checks.summary.governedCandidateChecks,
      candidateRefusals:checks.summary.governedCandidateRefusals,
      storedPassages:0,externallyAnchored:false},
    boundaries:['candidate gate only, not business-answer evaluation',
      'not semantic support','not independent provenance','mock identity',
      'not universal enforcement in other RAG application integrations']
  },null,2));
}finally{
  if(server.listening)await new Promise(ok=>server.close(ok));
  fs.rmSync(directory,{recursive:true,force:true});
}
