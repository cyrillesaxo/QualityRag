import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';

const decisionId='11111111-1111-4111-8111-111111111111';
const policy='a'.repeat(64);
const auth=async token=>({
 subject:token==='foreign'?'issuer#other':'issuer#owner',
 roles:new Set(token==='no-drive'?['evidence.reader']:['evidence.reader','drive.reader']),
 evidenceServices:new Set([token==='wrong-scope'?'other@staging':'claims@staging'])
});
function fixture({policySha=policy,revoked=false,folder='folder-one',connected=true}={}){
 const decision={id:decisionId,serviceId:'claims',environment:'staging',
   policySha256:policy,result:{verdict:'ADMIT'},
   signedCustody:{payload:{observations:{folder_id:'folder-one'}}}};
 const ledger={
   protectedDecisionForOwner(id,actor){
     if(id!==decisionId||actor!=='issuer#owner')throw Error('NOT_FOUND');
     return decision;
   },
   protectedDecisionRevocation(){return revoked?{at:'2026-11-10T10:00:00.000Z'}:null}
 };
 const store={resolve:async()=>({sha256:policySha})};
 const driveManager={status:()=>({connected,folderId:folder})};
 return {ledger,store,driveManager};
}
async function check(variant,token='reader'){
 const f=fixture(variant);
 const server=http.createServer(createHandler(f.store,null,{
   authenticate:auth,evidenceLedger:f.ledger,driveManager:f.driveManager,
   // createHandler requires the index whenever Drive is enabled; live witness checks stay off
   // here because no protected review trust is configured.
   driveIndex:{}
 }));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
   const r=await fetch('http://127.0.0.1:'+server.address().port+
     '/v1/evidence/protected-decisions/'+decisionId+'/dependency-status',{
       headers:{authorization:'Bearer '+token}
     });
   return {status:r.status,body:await r.json()};
 }finally{await new Promise(done=>server.close(done))}
}
test('US-068 dependency status reports changed policy, revoked decision and folder drift',async()=>{
 const fresh=await check({});
 assert.equal(fresh.status,200);
 assert.equal(fresh.body.schema,'qualityrag.protected-dependency-status/v1');
 assert.equal(fresh.body.dependencyState,'UNKNOWN');
 assert.equal(fresh.body.policyState,'UNCHANGED');
 assert.equal(fresh.body.driveState,'BOUND');
 assert.equal(fresh.body.sourceBytesRevalidated,false);
 assert.equal(fresh.body.releasePermitted,false);
 const changed=await check({policySha:'b'.repeat(64)});
 assert.equal(changed.body.dependencyState,'STALE');
 assert.equal(changed.body.policyState,'CHANGED');
 assert.equal((await check({revoked:true})).body.revoked,true);
 assert.equal((await check({folder:'other-folder'})).body.driveState,'FOLDER_CHANGED');
 assert.equal((await check({connected:false})).body.driveState,'DISCONNECTED');
});
test('US-068 dependency status denies foreign owner, scope and missing roles',async()=>{
 assert.equal((await check({},'foreign')).status,404);
 assert.equal((await check({},'wrong-scope')).status,404);
 assert.equal((await check({},'no-drive')).status,403);
});
