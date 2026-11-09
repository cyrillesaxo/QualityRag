import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';

const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const identities={
  ownerReader:{subject:'issuer#alice',roles:new Set(['evidence.reader']),
    evidenceServices:new Set(['claims@staging'])},
  ownerReviewer:{subject:'issuer#alice',roles:new Set(['evidence.reviewer']),
    evidenceServices:new Set(['claims@staging'])},
  differentOwner:{subject:'issuer#bob',roles:new Set(['evidence.reader','evidence.reviewer']),
    evidenceServices:new Set(['claims@staging'])},
  wrongService:{subject:'issuer#alice',roles:new Set(['evidence.reader','evidence.reviewer']),
    evidenceServices:new Set(['other@staging'])},
  noRole:{subject:'issuer#alice',roles:new Set(['policy.reader']),
    evidenceServices:new Set(['claims@staging'])}
};
function fixture(enabled=true){
 let revoked=null;
 const calls=[];
 const row={id,serviceId:'claims',environment:'staging',actor:'issuer#alice',
   result:{verdict:'ADMIT'},signedCustody:{signature:'synthetic-custody'},
   signedMeaning:{signature:'synthetic-meaning'}};
 const ledger=enabled?{
   protectedDecisionForOwner(decision,actor){
    calls.push(['owner-lookup',decision,actor]);
    if(decision!==id||actor!==row.actor)throw Error('PROTECTED_DECISION_OWNER_FORBIDDEN');
    return row;
   },
   protectedDecisionRevocation(decision){
    calls.push(['revocation-read',decision]);return revoked;
   },
   exportProtectedDecision(decision,actor){
    calls.push(['export',decision,actor]);
    if(decision!==id||actor!==row.actor)throw Error('PROTECTED_DECISION_OWNER_FORBIDDEN');
    return {schema:'qualityrag.protected-drive-decision-replay/v1',
     id,serviceId:'claims',environment:'staging',
     signedCustody:row.signedCustody,signedMeaning:row.signedMeaning,
     sourceTruthProven:false,externallyAnchored:false};
   },
   revokeProtectedDecision(decision,actor,reason){
    calls.push(['revoke',decision,actor,reason]);
    if(decision!==id||actor!==row.actor)throw Error('PROTECTED_DECISION_OWNER_FORBIDDEN');
    if(revoked)throw Error('PROTECTED_DECISION_ALREADY_REVOKED');
    revoked={at:'2026-11-09T17:00:00.000Z',reason};
    return {schema:'qualityrag.protected-decision-revocation/v1',
     decisionId:id,status:'REVOKED',revokedAt:revoked.at,reason,
     externallyAnchored:false};
   }
 }:null;
 return {ledger,calls,authenticate:async token=>identities[token]||null};
}
async function start(f){
 const store={};
 const server=http.createServer(createHandler(store,null,{authenticate:f.authenticate,
   evidenceLedger:f.ledger}));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 return {server,base:'http://127.0.0.1:'+server.address().port};
}
async function request(base,{action='status',method='GET',token='ownerReader',decision=id,body}={}){
 const res=await fetch(base+'/v1/evidence/protected-decisions/'+decision+'/'+action,{
  method,headers:{...(token?{authorization:'Bearer '+token}:{}),
   'content-type':'application/json'},
  body:body===undefined?undefined:JSON.stringify(body)});
 return {status:res.status,data:await res.json()};
}
test('status is owner-bound, scope-bound, and explicitly not an authorization to release',async()=>{
 const f=fixture(),{server,base}=await start(f);
 try{
  const denied=await request(base,{token:'differentOwner'});
  assert.equal(denied.status,404);
  assert.equal(denied.data.error,'PROTECTED_DECISION_NOT_FOUND');
  assert.equal((await request(base,{token:'wrongService'})).status,404);
  assert.equal((await request(base,{token:'noRole'})).status,403);
  assert.equal((await request(base,{token:null})).status,401);
  const ok=await request(base);
  assert.equal(ok.status,200);
  assert.equal(ok.data.status,'HUMAN_REVIEWED_ADMISSION');
  assert.equal(ok.data.releasePermittedByStatus,false);
  assert.equal(ok.data.sourceRevalidatedForThisRequest,false);
  assert.equal(ok.data.externallyAnchored,false);
  assert.equal(f.calls.filter(x=>x[0]==='revoke').length,0);
 }finally{await new Promise(done=>server.close(done))}
});
test('export is owner-only and historical, including after revocation',async()=>{
 const f=fixture(),{server,base}=await start(f);
 try{
  assert.equal((await request(base,{action:'export',token:'differentOwner'})).status,404);
  let exported=await request(base,{action:'export'});
  assert.equal(exported.status,200);
  assert.equal(exported.data.currentSourceVerified,false);
  assert.equal(exported.data.releasePermittedByExport,false);
  assert.equal(exported.data.currentStatus,'HISTORICAL_SIGNED_DECISION');
  await request(base,{action:'revoke',method:'POST',token:'ownerReviewer',
    body:{reason:'OWNER_WITHDRAWN'}});
  exported=await request(base,{action:'export'});
  assert.equal(exported.status,200);
  assert.equal(exported.data.currentStatus,'REVOKED');
  assert.ok(exported.data.revokedAt);
 }finally{await new Promise(done=>server.close(done))}
});
test('reviewer role and strict reason required; duplicate revocation fails without second write',async()=>{
 const f=fixture(),{server,base}=await start(f);
 try{
  assert.equal((await request(base,{action:'revoke',method:'POST',
   token:'ownerReader',body:{reason:'OWNER_WITHDRAWN'}})).status,403);
  assert.equal((await request(base,{action:'revoke',method:'POST',
   token:'wrongService',body:{reason:'OWNER_WITHDRAWN'}})).status,404);
  assert.equal((await request(base,{action:'revoke',method:'POST',
   token:'ownerReviewer',body:{reason:'OWNER_WITHDRAWN',subject:'issuer#bob'}})).status,400);
  assert.equal((await request(base,{action:'revoke',method:'POST',
   token:'ownerReviewer',body:{reason:'INVALID'}})).status,400);
  assert.equal(f.calls.filter(x=>x[0]==='revoke').length,0);
  const accepted=await request(base,{action:'revoke',method:'POST',
   token:'ownerReviewer',body:{reason:'REVIEW_DISPUTED'}});
  assert.equal(accepted.status,200);
  assert.equal(accepted.data.status,'REVOKED');
  assert.equal(accepted.data.releasePermitted,false);
  const repeated=await request(base,{action:'revoke',method:'POST',
   token:'ownerReviewer',body:{reason:'REVIEW_DISPUTED'}});
  assert.equal(repeated.status,409);
  assert.equal(repeated.data.error,'PROTECTED_DECISION_ALREADY_REVOKED');
  assert.equal(f.calls.filter(x=>x[0]==='revoke').length,2);
  const status=await request(base);
  assert.equal(status.data.status,'REVOKED');
  assert.equal(status.data.reason,'REVIEW_DISPUTED');
 }finally{await new Promise(done=>server.close(done))}
});
test('disabled ledger and malformed/method requests cannot mutate or leak',async()=>{
 const off=fixture(false),s=await start(off);
 try{
  assert.equal((await request(s.base)).status,404);
  assert.deepEqual(off.calls,[]);
 }finally{await new Promise(done=>s.server.close(done))}
 const f=fixture(),{server,base}=await start(f);
 try{
  assert.equal((await request(base,{action:'status',method:'POST',body:{}})).status,404);
  assert.equal((await request(base,{action:'revoke',method:'GET',token:'ownerReviewer'})).status,404);
  assert.equal((await request(base,{action:'status',decision:'not-a-uuid'})).status,403);
  assert.equal(f.calls.filter(x=>x[0]==='revoke').length,0);
 }finally{await new Promise(done=>server.close(done))}
});
