import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';
const policy={id:'policy',version:'1',requirements:[{id:'obligation'}]};
const SHA='a'.repeat(64);
function fixture(){
 const calls=[],identities={
  reader:{subject:'issuer#alice',roles:new Set(['drive.reader','evidence.reader']),
   evidenceServices:new Set(['claims@dev'])},
  reviewer:{subject:'issuer#alice',roles:new Set(['drive.reader','evidence.reader','evidence.reviewer']),
   evidenceServices:new Set(['claims@dev'])},
  wrong:{subject:'issuer#bob',roles:new Set(['drive.reader','evidence.reader','evidence.reviewer']),
   evidenceServices:new Set(['other@dev'])},
  driveOnly:{subject:'issuer#alice',roles:new Set(['drive.reader']),
   evidenceServices:new Set(['claims@dev'])}
 };
 return {calls,authenticate:async token=>identities[token]||null,
  store:{async resolve(s,e){calls.push(['resolve',s,e]);return {policy,sha256:SHA}}},
  driveManager:{status(actor){calls.push(['status',actor]);return {connected:true,folderId:'folder-a'}}},
  driveIndex:{
   checkGovernedCandidates(actor,connection,p,digest,candidates){
    calls.push(['check',actor,connection.folderId,candidates]);
    assert.equal(p,policy);assert.equal(digest,SHA);
    if(candidates?.[0]?.sourceId==='invalid')throw Error('INVALID_DRIVE_GATE_CANDIDATE');
    return {schema:'qualityrag.drive-governed-candidate-check/v1',result:'INCONCLUSIVE',
     evaluationAdmitted:false,meaningVerified:false,
     independentProvenanceVerified:false,observations:[]};
   }
  },
  evidenceLedger:{recordCandidateCheck(s,e,actor,sha,result){
   calls.push(['record',s,e,actor,sha,result.result]);
   return {id:'receipt-1',chainHash:'synthetic-hash'};
  }}
 }
}
async function send(f,{token='reader',path='/v1/drives/google/governed-requirements?serviceId=claims&environment=dev',method='GET',data}={}){
 const server=http.createServer(createHandler(f.store,null,{
  authenticate:f.authenticate,driveManager:f.driveManager,
  driveIndex:f.driveIndex,evidenceLedger:f.evidenceLedger}));
 await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 try{
  const response=await fetch('http://127.0.0.1:'+server.address().port+path,{
   method,headers:{authorization:'Bearer '+token,'content-type':'application/json'},
   body:data===undefined?undefined:JSON.stringify(data)});
  return {status:response.status,data:await response.json()};
 }finally{await new Promise(ok=>server.close(ok))}
}
const candidate={sourceId:'google_drive/'+'a'.repeat(32),
 revision:SHA,requirementId:'obligation',lineNumber:1};
const args={serviceId:'claims',environment:'dev',candidates:[candidate]};
test('only scoped Drive+evidence reader sees requirements',async()=>{
 const f=fixture();
 let r=await send(f);
 assert.equal(r.status,200);assert.equal(r.data.requirements[0].id,'obligation');
 assert.equal(r.data.admissionStatus,'NOT_EVALUATED');
 assert.equal((await send(f,{token:'wrong'})).status,403);
 assert.equal((await send(f,{token:'driveOnly'})).status,403);
 assert.equal((await send(f,{path:'/v1/drives/google/governed-requirements?serviceId=claims&environment=dev&subject=issuer%23bob'})).status,400);
 assert.equal(f.calls.filter(x=>x[0]==='check'||x[0]==='record').length,0);
});
test('candidate preview remains INCONCLUSIVE and cannot append ledger events',async()=>{
 const f=fixture();
 const r=await send(f,{path:'/v1/drives/google/governed-check',method:'POST',data:args});
 assert.equal(r.status,200);assert.equal(r.data.result,'INCONCLUSIVE');
 assert.equal(r.data.evaluationAdmitted,false);
 assert.equal(r.data.telemetry.recorded,false);
 assert.deepEqual(f.calls.filter(x=>x[0]==='record'),[]);
 assert.deepEqual(f.calls.find(x=>x[0]==='check').slice(1,3),['issuer#alice','folder-a']);
});
test('record challenge needs separate reviewer role and exact scope',async()=>{
 const f=fixture(),path='/v1/drives/google/record-check';
 assert.equal((await send(f,{path,method:'POST',data:args})).status,403);
 assert.equal((await send(f,{token:'wrong',path,method:'POST',data:args})).status,403);
 const r=await send(f,{token:'reviewer',path,method:'POST',data:args});
 assert.equal(r.status,200);
 assert.equal(r.data.telemetry.recorded,true);
 assert.equal(r.data.telemetry.externallyAnchored,false);
 assert.equal(f.calls.filter(x=>x[0]==='record').length,1);
});
test('unknown candidate and caller-supplied owner override never produce ledger record',async()=>{
 const f=fixture(),path='/v1/drives/google/record-check';
 assert.equal((await send(f,{token:'reviewer',path,method:'POST',
  data:{...args,subject:'issuer#bob'}})).status,400);
 assert.equal((await send(f,{token:'reviewer',path,method:'POST',
  data:{...args,candidates:[{...candidate,sourceId:'invalid'}]}})).status,400);
 assert.equal(f.calls.filter(x=>x[0]==='record').length,0);
});
