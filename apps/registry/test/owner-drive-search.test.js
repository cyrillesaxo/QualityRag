import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';
function fixture(){
 const calls=[],users={
  alice:{subject:'issuer#alice',roles:new Set(['drive.reader'])},
  bob:{subject:'issuer#bob',roles:new Set(['policy.reader'])}
 };
 const driveManager={status(subject){calls.push(['status',subject]);return {
  connected:true,folderId:'folder-a',email:subject+'@example.invalid'};
 }};
 const driveIndex={search(subject,conn,query){
  calls.push(['search',subject,conn.email,query]);
  if(query.trim().length<2)throw Error('INVALID_DRIVE_SEARCH_QUERY');
  return {indexed:true,coverage:'BOUNDED',hits:[{
   source_id:'google_drive/example',matched_text:'synthetic source',quality:'LEXICAL_MATCH_NOT_EVIDENCE_ADMISSION'
  }],assurance:'NOT_EVALUATED_BY_PACKSPEC'};
 }};
 return {calls,driveManager,driveIndex,authenticate:async token=>users[token]||null};
}
async function request(f,token,body){
 const server=http.createServer(createHandler({},null,{
  authenticate:f.authenticate,driveManager:f.driveManager,driveIndex:f.driveIndex}));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
  const r=await fetch('http://127.0.0.1:'+server.address().port+'/v1/drives/google/search',{
   method:'POST',headers:{...(token?{authorization:'Bearer '+token}:{}),
    'content-type':'application/json'},body:JSON.stringify(body)});
  return {status:r.status,data:await r.json()};
 }finally{await new Promise(done=>server.close(done))}
}
test('search uses authenticated subject and bounded original index metadata',async()=>{
 const f=fixture();
 const r=await request(f,'alice',{query:'provider payment'});
 assert.equal(r.status,200);
 assert.equal(r.data.assurance,'NOT_EVALUATED_BY_PACKSPEC');
 assert.equal(r.data.hits[0].quality,'LEXICAL_MATCH_NOT_EVIDENCE_ADMISSION');
 assert.deepEqual(f.calls.find(x=>x[0]==='search'),
  ['search','issuer#alice','issuer#alice@example.invalid','provider payment']);
});
test('reader-role and no foreign subject override; no source read on failure',async()=>{
 const f=fixture();
 assert.equal((await request(f,'bob',{query:'provider payment'})).status,403);
 assert.equal((await request(f,null,{query:'provider payment'})).status,401);
 assert.equal((await request(f,'alice',{query:'provider payment',subject:'issuer#bob'})).status,400);
 assert.equal((await request(f,'alice',{query:'x'})).status,400);
 assert.equal(f.calls.filter(x=>x[0]==='search'&&x[3]==='provider payment').length,0);
});
