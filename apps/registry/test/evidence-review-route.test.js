import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';
const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
function make(){
 const calls=[],identities={
  reviewer:{subject:'issuer#reviewer',roles:new Set(['evidence.reviewer']),
    evidenceServices:new Set(['claims@prod'])},
  other:{subject:'issuer#other',roles:new Set(['evidence.reviewer']),
    evidenceServices:new Set(['other@prod'])},
  writer:{subject:'issuer#writer',roles:new Set(['evidence.ingest']),
    evidenceServices:new Set(['claims@prod'])},
  original:{subject:'issuer#original',roles:new Set(['evidence.reviewer']),
    evidenceServices:new Set(['claims@prod'])}
 };
 const ledger={
  snapshot(key){calls.push(['snapshot',key]);
   if(key!==id)throw Error('EVIDENCE_NOT_FOUND');
   return {id,serviceId:'claims',environment:'prod',verdict:'REFUSE'};
  },
  review(key,input,actor){calls.push(['review',key,actor,input]);
   if(actor==='issuer#original')throw Error('SELF_REVIEW_FORBIDDEN');
   return {evaluationId:key,decision:input.decision,reasonCode:input.reasonCode,
    chainHash:'hash-synthetic',replayReproduced:true};
  }
 };
 return {calls,ledger,authenticate:async token=>identities[token]||null};
}
async function request(f,token='reviewer',body={decision:'DISPUTED',reasonCode:'POLICY_DISAGREEMENT',note:''},method='POST'){
 const srv=http.createServer(createHandler({},null,{
  authenticate:f.authenticate,evidenceLedger:f.ledger}));
 await new Promise(ok=>srv.listen(0,'127.0.0.1',ok));
 try{
  const res=await fetch('http://127.0.0.1:'+srv.address().port+
   '/v1/evidence/evaluations/'+id+'/reviews',{
   method,headers:{...(token?{authorization:'Bearer '+token}:{}),
     'content-type':'application/json'},
   body:method==='POST'?JSON.stringify(body):undefined});
  return {status:res.status,data:await res.json()};
 }finally{await new Promise(ok=>srv.close(ok))}
}
test('independent scoped reviewer can append a disposition without changing verdict',async()=>{
 const f=make(),r=await request(f);
 assert.equal(r.status,201);
 assert.equal(r.data.decision,'DISPUTED');
 assert.equal(r.data.engineVerdictChanged,false);
 assert.equal(r.data.sourceAuthenticityVerified,false);
 assert.equal(f.calls.filter(x=>x[0]==='review').length,1);
});
test('wrong service, wrong role and absent bearer never append',async()=>{
 const f=make();
 assert.equal((await request(f,'other')).status,404);
 assert.equal((await request(f,'writer')).status,403);
 assert.equal((await request(f,null)).status,401);
 assert.equal(f.calls.filter(x=>x[0]==='review').length,0);
});
test('self review refused by ledger; invalid body and unknown method never mutate',async()=>{
 const f=make();
 assert.equal((await request(f,'original')).status,403);
 assert.equal((await request(f,'reviewer',{decision:'ACCEPTED',reasonCode:'REPRODUCED',subject:'issuer#other'})).status,400);
 assert.equal((await request(f,'reviewer',{decision:'INVALID',reasonCode:'OTHER'})).status,400);
 assert.equal((await request(f,'reviewer',{decision:'ACCEPTED',reasonCode:'OTHER',note:'bad@example.test'})).status,400);
 assert.equal((await request(f,'reviewer',undefined,'GET')).status,404);
 assert.equal(f.calls.filter(x=>x[0]==='review').length,1);
});
