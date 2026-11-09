import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';
const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const identities={
 alice:{subject:'issuer#alice',roles:new Set(['evidence.reader']),
  evidenceServices:new Set(['claims@prod'])},
 other:{subject:'issuer#other',roles:new Set(['evidence.reader']),
  evidenceServices:new Set(['other@prod'])},
 writer:{subject:'issuer#writer',roles:new Set(['evidence.ingest']),
  evidenceServices:new Set(['claims@prod'])}
};
function fixture(ledgerEnabled=true){
 const calls=[];
 const entry={id,serviceId:'claims',environment:'prod',result:{verdict:'REFUSE'}};
 const evidenceLedger=ledgerEnabled?{
  list(s,e){calls.push('list:'+s+'@'+e);return {summary:{refuse:1},guardTelemetry:{blockedUnattestedIngress:1},entries:[entry]};},
  snapshot(key){calls.push('snapshot:'+key);if(key!==id)throw Error('EVIDENCE_NOT_FOUND');return entry;},
  exportReplay(key){calls.push('export:'+key);return {schema:'qualityrag.evidence-replay/v1'};},
  replay(key){calls.push('replay:'+key);return {reproduced:true};}
 }:null;
 return {calls,evidenceLedger,store:{
  async resolve(s,e){calls.push('resolve:'+s+'@'+e);
   return {sha256:'a'.repeat(64),policy:{id:'governance',version:'1'}};}
 },authenticate:async token=>identities[token]||null};
}
async function request(f,method,pathname,token='alice'){
 const protectedMode=Boolean(f.evidenceLedger);
 const server=http.createServer(createHandler(f.store,null,{authenticate:f.authenticate,
  evidenceLedger:f.evidenceLedger,protectedDriveServices:protectedMode?
   new Set(['claims@prod']):new Set(),
  driveManager:protectedMode?{status(){return {connected:false}}}:null,
  driveIndex:protectedMode?{status(){return {indexed:false}}}:null,
  protectedReviewTrust:protectedMode?{custodian:{key:{}},meaningReviewer:{key:{}}}:null}));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
  const response=await fetch('http://127.0.0.1:'+server.address().port+pathname,{
   method,headers:{...(token?{Authorization:'Bearer '+token}:{})}});
  return {status:response.status,data:await response.json()};
 }finally{await new Promise(done=>server.close(done))}
}
test('telemetry requires injected ledger and cannot be enabled by a shared token',async()=>{
 const f=fixture(false);
 const r=await request(f,'GET','/v1/evidence/evaluations?serviceId=claims&environment=prod');
 assert.equal(r.status,404);
 assert.equal(r.data.error,'EVIDENCE_TELEMETRY_DISABLED');
 assert.deepEqual(f.calls,[]);
});
test('list and enforcement protect exact service scope without global monitoring claims',async()=>{
 const f=fixture();
 const path='/v1/evidence/evaluations?serviceId=claims&environment=prod';
 assert.equal((await request(f,'GET',path,null)).status,401);
 assert.equal((await request(f,'GET',path,'writer')).status,403);
 assert.equal((await request(f,'GET',path,'other')).status,403);
 assert.deepEqual(f.calls,[]);
 const result=await request(f,'GET',path);
 assert.equal(result.status,200);
 assert.equal(result.data.summary.refuse,1);
 const enforcement=await request(f,'GET','/v1/evidence/enforcement?serviceId=claims&environment=prod');
 assert.equal(enforcement.status,200);
 assert.equal(enforcement.data.globalApplicationEnforcement,false);
 assert.equal(enforcement.data.externallyAnchored,false);
 assert.equal(enforcement.data.genericEvidenceIngress,'BLOCKED');
 assert.equal(enforcement.data.sourceAdmission,'NOT_VERIFIED_BY_THIS_ENDPOINT');
});
test('record inspection, export and replay are scoped and do not mutate ledger',async()=>{
 const f=fixture(),prefix='/v1/evidence/evaluations/'+id;
 assert.equal((await request(f,'GET',prefix,'other')).status,403);
 assert.deepEqual(f.calls,['snapshot:'+id]);
 assert.equal((await request(f,'GET',prefix)).status,200);
 assert.equal((await request(f,'GET',prefix+'/export')).status,200);
 const replay=await request(f,'POST',prefix+'/replay');
 assert.equal(replay.status,200);
 assert.equal(replay.data.reproduced,true);
 assert.equal((await request(f,'POST',prefix+'/reviews')).status,404);
 assert.equal((await request(f,'POST','/v1/evidence/evaluations?serviceId=claims&environment=prod')).status,404);
 assert.equal((await request(f,'GET','/v1/evidence/evaluations/invalid')).status,404);
 assert.equal(f.calls.some(c=>c.startsWith('ingest')),false);
});
test('malformed scopes are rejected before ledger operations',async()=>{
 const f=fixture();
 for(const path of ['/v1/evidence/evaluations?serviceId=claims&environment=prod&subject=other',
   '/v1/evidence/evaluations?serviceId=claims','/v1/evidence/enforcement?serviceId=x&environment=bad%20scope']){
  assert.equal((await request(f,'GET',path)).status,400);
 }
 assert.deepEqual(f.calls,[]);
});
