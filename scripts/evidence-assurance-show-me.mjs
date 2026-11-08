#!/usr/bin/env node
// Actual in-process registry HTTP exercise with synthetic sources and demo-only identities.
// This is NOT a production IdP, verified source provenance, or independent audit.
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtempSync,rmSync,writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {RegistryStore} from '../apps/registry/src/store.js';
import {EvidenceLedger} from '../apps/registry/src/evidence-ledger.js';
import {createHandler} from '../apps/registry/src/server.js';

const dir=mkdtempSync(path.join(os.tmpdir(),'qualityrag-show-me-'));
const registry=new RegistryStore(path.join(dir,'registry.json'));
const ledger=new EvidenceLedger(path.join(dir,'evidence.jsonl'));
registry.register({id:'document-assistant',displayName:'Document assistant'},'demo');
registry.draft({id:'source-independence',version:'1',requirements:[
  {id:'independent-approval',min_independent_sources:2}
]},'demo');
registry.approve('source-independence','1','demo-approver');
registry.bind('document-assistant','test','source-independence','1','demo-publisher');

const demoAuth=async token=>{
 const role={'writer':'evidence.ingest','reader':'evidence.reader','customer':'evidence.reviewer'}[token];
 return role?{subject:'DEMO_ONLY:'+token,roles:new Set([role]),
   evidenceServices:new Set(['document-assistant@test'])}:null;
};
const server=http.createServer(createHandler(registry,null,{
 authenticate:demoAuth,evidenceLedger:ledger
}));
const listen=()=>new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const close=()=>new Promise(resolve=>server.close(resolve));
const opaque=(prefix,i)=>prefix+'_'+i.toString(16).padStart(32,'0');
function witness(i,origin){
 return {id:opaque('ev',i),requirement_id:'independent-approval',
   origin:opaque('org',origin),source_ref:opaque('src',i),
   status:'SUPPORTS',observed_at:new Date(Date.now()-2000).toISOString()};
}
try{
 await listen();
 const host='http://127.0.0.1:'+server.address().port;
 async function request(method,route,actor,data){
   const response=await fetch(host+route,{method,headers:{
     Authorization:'Bearer '+actor,'Content-Type':'application/json'
   },body:data===undefined?undefined:JSON.stringify(data)});
   const result=await response.json();
   assert.ok(response.ok,'Unexpected registry status '+response.status+': '+JSON.stringify(result));
   return result;
 }
 const base={serviceId:'document-assistant',environment:'test',traceId:'trace-challenge-001'};
 const before=await request('POST','/v1/evidence/evaluations','writer',{
   ...base,requestId:'challenge-before',evidence:[witness(1,1),witness(2,1),witness(3,1)]
 });
 const after=await request('POST','/v1/evidence/evaluations','writer',{
   ...base,requestId:'challenge-after',
   evidence:[witness(1,1),witness(2,1),witness(3,1),witness(4,2)]
 });
 const replay=await request('POST','/v1/evidence/evaluations/'+before.id+'/replay','reader');
 const review=await request('POST','/v1/evidence/evaluations/'+before.id+'/reviews','customer',
   {decision:'ACCEPTED',reasonCode:'REPRODUCED',
    note:'Same-source citations do not meet the approved independence requirement'});
 const exportArg=process.argv.indexOf('--export');
 let exportFile=null,exportHash=null;
 if(exportArg>=0){
   if(exportArg!==process.argv.length-2)
     throw Error('Usage: evidence-assurance-show-me.mjs --export OUTPUT_JSON_PATH');
   exportFile=path.resolve(process.argv[exportArg+1]);
   if(exportFile.startsWith(dir+path.sep))throw Error('Export path must outlive the demo directory');
   const pkg=await request('GET','/v1/evidence/evaluations/'+before.id+'/export','reader');
   writeFileSync(exportFile,JSON.stringify(pkg,null,2),{encoding:'utf8',mode:0o600,flag:'wx'});
   exportHash=pkg.integrity.sha256;
 }
 const summary=await request('GET',
   '/v1/evidence/evaluations?serviceId=document-assistant&environment=test','reader');
 assert.equal(before.verdict,'INCONCLUSIVE');
 assert.equal(after.verdict,'ADMIT');
 assert.equal(replay.reproduced,true);
 assert.equal(review.decision,'ACCEPTED');
 assert.equal(summary.observedCount,2);
 assert.equal(summary.summary.accepted,1);
 console.log(JSON.stringify({
   demonstration:'SYNTHETIC, REAL REGISTRY HTTP EXECUTION',
   first_case:{citations:before.evidence.length,independent_origins:before.findings[0].independent_sources,
     verdict:before.verdict,reason:before.findings[0].reasons,receipt:before.chainHash.slice(0,16)+'…'},
   corrected_case:{citations:after.evidence.length,independent_origins:after.findings[0].independent_sources,
     verdict:after.verdict,reason:after.findings[0].reasons},
   pinned_replay:{reproduced:replay.reproduced,evaluator:replay.evaluator},
   independent_demo_reviewer:{decision:review.decision,reason:review.reasonCode},
   observed_summary:summary.summary,
   portable_export:exportFile?{file:exportFile,sha256:exportHash}:null,
   boundaries:['synthetic sources','fake local demo identities','metadata gate only',
      'hash chain not externally anchored','no customer approval or compliance claim']
 },null,2));
}finally{
 if(server.listening)await close();
 rmSync(dir,{recursive:true,force:true});
}
