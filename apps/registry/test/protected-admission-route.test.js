import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';

const base={serviceId:'claims',environment:'dev',requestId:'r1',traceId:'t1',
 custody:{secret:'do not leak'},meaning:{}};
const identities={
 owner:{subject:'issuer#alice',roles:new Set(['evidence.ingest','drive.reader']),
  evidenceServices:new Set(['claims@dev'])},
 notDrive:{subject:'issuer#alice',roles:new Set(['evidence.ingest']),
  evidenceServices:new Set(['claims@dev'])},
 otherScope:{subject:'issuer#alice',roles:new Set(['evidence.ingest','drive.reader']),
  evidenceServices:new Set(['other@dev'])}
};
function deps(scope=new Set(['claims@dev'])){
 const calls=[];
 return {calls,
  store:{async resolve(){calls.push('resolve');return {sha256:'a'.repeat(64),
    policy:{requirements:[{id:'rule'}]}};}},
  evidenceLedger:{recordProtectedDecision(){calls.push('record');throw Error('MUST_NOT_WRITE')}},
  driveManager:{status(){calls.push('drive');return {connected:true,folderId:'folder-1',email:'a@example.test'}}},
  driveIndex:{verifyLiveApprovedWitnesses(){calls.push('live');throw Error('MUST_NOT_READ')}},
  protectedReviewTrust:{custodian:{key:{}},meaningReviewer:{key:{}}},
  protectedDriveServices:scope,
  authenticate:async token=>identities[token]||null};
}
async function httpCase(config,method='POST',body=base,token='owner'){
 const server=http.createServer(createHandler(config.store,null,config));
 await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 try{
  const r=await fetch('http://127.0.0.1:'+server.address().port+'/v1/evidence/protected-admit',{
   method,headers:{authorization:'Bearer '+token,'content-type':'application/json'},
   body:method==='POST'?JSON.stringify(body):undefined});
  return {status:r.status,data:await r.json()};
 }finally{await new Promise(ok=>server.close(ok))}
}
test('live protected admission refuses partial dependency configuration at startup',()=>{
 const p=deps();
 assert.throws(()=>createHandler(p.store,null,{authenticate:p.authenticate,
   protectedDriveServices:p.protectedDriveServices}),
  /PROTECTED_ADMISSION_DEPENDENCIES_REQUIRED/);
});
test('roles and exact service scope gate all policy and Drive reads',async()=>{
 const p=deps();
 assert.equal((await httpCase(p,'POST',base,'otherScope')).status,403);
 assert.equal((await httpCase(p,'POST',base,'notDrive')).status,403);
 assert.deepEqual(p.calls,[]);
 const disabled=deps(new Set());
 const r=await httpCase(disabled);
 assert.equal(r.status,403);
 assert.equal(r.data.error,'PROTECTED_ADMISSION_SCOPE_NOT_PROTECTED');
 assert.deepEqual(disabled.calls,[]);
});
test('invalid manifest request cannot reach source index or leave secrets in errors',async()=>{
 const p=deps();
 const invalid=await httpCase(p,'POST',{...base,subject:'issuer#bob'});
 assert.equal(invalid.status,400);
 assert.equal(invalid.data.error,'INVALID_PROTECTED_ADMISSION_REQUEST');
 assert.deepEqual(p.calls,[]);
 assert.equal(JSON.stringify(invalid.data).includes('do not leak'),false);
});
test('invalid signatures fail before Google live-byte reads and ledger admission',async()=>{
 const p=deps();
 const r=await httpCase(p);
 assert.equal(r.status,400);
 assert.equal(r.data.error,'PROTECTED_ADMISSION_FAILED');
 assert.deepEqual(p.calls,['resolve','drive']);
});
test('unknown method and unauthenticated calls remain rejected',async()=>{
 const p=deps();
 const get=await httpCase(p,'GET');
 assert.equal(get.status,404);
 const noScope=await httpCase(p,'POST',base,'absent');
 assert.equal(noScope.status,401);
 assert.deepEqual(p.calls,[]);
});
