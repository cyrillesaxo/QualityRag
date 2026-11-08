#!/usr/bin/env node
// Synthetic-only execution of protected-service denial and ledger visibility.
// No customer Drive, no external IdP, no production authorization asserted.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {randomBytes} from 'node:crypto';
import {RegistryStore} from '../apps/registry/src/store.js';
import {EvidenceLedger} from '../apps/registry/src/evidence-ledger.js';
import {UserDriveIndex} from '../apps/registry/src/user-drive-index.js';
import {createHandler} from '../apps/registry/src/server.js';

const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-protected-ingress-demo-'));
const store=new RegistryStore(path.join(dir,'registry.json'));
store.register({id:'claims-api',displayName:'Synthetic claims service'},'demo');
store.draft({id:'claims-contract',version:'1',requirements:[
  {id:'exception',min_independent_sources:1}
]},'demo');
store.approve('claims-contract','1','reviewer');
store.bind('claims-api','protected','claims-contract','1','publisher');
store.bind('claims-api','test','claims-contract','1','publisher');
const ledger=new EvidenceLedger(path.join(dir,'ledger.jsonl'));
const index=new UserDriveIndex({dir:path.join(dir,'index'),
  encryptionKey:randomBytes(32).toString('base64')});
const authenticate=async token=>{
 const permission=token==='writer'?'evidence.ingest':
  token==='reader'?'evidence.reader':null;
 return permission?{subject:'DEMO#'+token,roles:new Set([permission]),
   evidenceServices:new Set(['claims-api@protected','claims-api@test'])}:null;
};
const server=http.createServer(createHandler(store,null,{
 authenticate,driveManager:{status:()=>({connected:false})},driveIndex:index,
 evidenceLedger:ledger,protectedDriveServices:new Set(['claims-api@protected'])
}));
try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 async function req(method,route,actor,data){
  const res=await fetch(base+route,{method,headers:{
   Authorization:'Bearer '+actor,'Content-Type':'application/json'
  },body:data===undefined?undefined:JSON.stringify(data)});
  return {code:res.status,body:await res.json()};
 }
 const evidence=[{
  id:'ev_'+'a'.repeat(32),requirement_id:'exception',
  origin:'org_'+'b'.repeat(32),source_ref:'src_'+'c'.repeat(32),
  status:'SUPPORTS',observed_at:new Date(Date.now()-2000).toISOString()
 }];
 const payload={serviceId:'claims-api',environment:'protected',
  requestId:'demo-blocked-1',traceId:'demo-trace',evidence};
 const denied=await req('POST','/v1/evidence/evaluations','writer',payload);
 assert.equal(denied.code,403);
 assert.equal(denied.body.error,'PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED');
 const status=await req('GET',
  '/v1/evidence/enforcement?serviceId=claims-api&environment=protected','reader');
 assert.equal(status.code,200);
 assert.equal(status.body.protected,true);
 assert.equal(status.body.guardTelemetry.observedBlockedAttempts,1);
 const allowed=await req('POST','/v1/evidence/evaluations','writer',{
  ...payload,environment:'test',requestId:'demo-legacy-1'
 });
 assert.equal(allowed.code,201);
 assert.equal(allowed.body.verdict,'ADMIT');
 const history=new EvidenceLedger(path.join(dir,'ledger.jsonl'))
  .list('claims-api','protected');
 assert.equal(history.observedCount,0);
 assert.equal(history.summary.blockedUnattestedIngress,1);
 console.log(JSON.stringify({
  demonstration:'SYNTHETIC REAL HTTP REGISTRY: EXPLICIT SERVICE INGRESS PROTECTION',
  protectedService:{scope:'claims-api@protected',genericIngress:denied.code,
   decision:denied.body.error,
   observedBlockedAttempts:status.body.guardTelemetry.observedBlockedAttempts,
   recordedAdmissions:history.observedCount},
  legacyService:{scope:'claims-api@test',genericIngress:allowed.code,
   legacyMetadataVerdict:allowed.body.verdict},
  boundaries:['Only configured registry services protected',
   'Blocking is not semantic source validation',
   'Existing records from before protection may remain',
   'The Drive candidate review path still never ADMITs unreviewed evidence',
   'Source authenticity and external app routing are not established']
 },null,2));
}finally{
 if(server.listening)await new Promise(ok=>server.close(ok));
 fs.rmSync(dir,{recursive:true,force:true});
}
