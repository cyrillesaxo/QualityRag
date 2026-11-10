import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';

const decision='11111111-1111-4111-8111-111111111111';
const requestId='delivery-22222222-2222-4222-8222-222222222222';
const calls=[];
const ledger={
 protectedDecisionForOwner(id,owner){
   calls.push([id,owner]);
   if(id!==decision||owner!=='issuer#alice')throw Error('PROTECTED_DECISION_OWNER_FORBIDDEN');
   return {id,serviceId:'claims',environment:'staging'};
 },
 protectedUseStatusForOwner(id,owner,req){
   assert.equal(id,decision);assert.equal(owner,'issuer#alice');
   assert.equal(req,requestId);
   return {schema:'qualityrag.protected-use-status/v1',decisionId:id,requestId:req,
    state:'RECORDED',useReceiptId:'33333333-3333-4333-8333-333333333333',
    recordedAt:'2026-11-10T10:00:00.000Z',
    answerSha256:'a'.repeat(64),policySha256:'b'.repeat(64),
    deliveryMode:'SOURCE_GROUNDED_EXTRACT',retryAuthorized:false,
    currentSourceRevalidated:false,releasePermitted:false};
 }
};
const authenticate=async token=>token==='reader'?{
 subject:'issuer#alice',roles:new Set(['evidence.reader']),
 evidenceServices:new Set(['claims@staging'])
}:token==='no-role'?{
 subject:'issuer#alice',roles:new Set(['drive.reader']),
 evidenceServices:new Set(['claims@staging'])
}:token==='other-scope'?{
 subject:'issuer#alice',roles:new Set(['evidence.reader']),
 evidenceServices:new Set(['other@staging'])
}:token==='foreign'?{
 subject:'issuer#mallory',roles:new Set(['evidence.reader']),
 evidenceServices:new Set(['claims@staging'])
}:null;

test('US-066 protected-use status is owner-only and read-only',async()=>{
 const server=http.createServer(createHandler({},null,{authenticate,evidenceLedger:ledger}));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port+'/v1/evidence/protected-decisions/'+decision+'/use-status';
 try{
  async function ask(token,url=base+'?requestId='+requestId){
   const r=await fetch(url,{headers:{authorization:'Bearer '+token}});
   return {code:r.status,body:await r.json()};
  }
  const ok=await ask('reader');
  assert.equal(ok.code,200);
  assert.equal(ok.body.state,'RECORDED');
  assert.equal(ok.body.retryAuthorized,false);
  assert.equal(ok.body.releasePermitted,false);
  assert.equal(ok.body.answerSha256,'a'.repeat(64));
  assert.equal((await ask('foreign')).code,404);
  assert.equal((await ask('other-scope')).code,404);
  assert.equal((await ask('no-role')).code,403);
  assert.equal((await ask('reader',base+'?requestId='+requestId+'&requestId='+requestId)).code,404);
  assert.equal((await ask('reader',base+'?requestId=unknown')).code,404);
  assert.deepEqual(calls[0],[decision,'issuer#alice']);
 }finally{await new Promise(resolve=>server.close(resolve))}
});
