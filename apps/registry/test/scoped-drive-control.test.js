import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';

async function serve(options){
 const server=http.createServer(createHandler({},null,options));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 return {server,origin:'http://127.0.0.1:'+server.address().port};
}
function fixture(){
 const calls=[];
 const manager={status(subject){calls.push(['status',subject]);return {
  connected:true,folderId:'folder-for-'+subject,email:subject+'@example.invalid'};}};
 const index={
  status(subject,connection){calls.push(['index.status',subject,connection.folderId]);return {enabled:true}},
  visibility(subject,connection){calls.push(['visibility',subject,connection.folderId]);return {sources:[]}},
  controlSource(subject,connection,input){calls.push(['control',subject,connection.folderId,input]);return {updated:true}},
  async sync(subject,managerArg){assert.equal(managerArg,manager);calls.push(['sync',subject]);return {indexed:2}},
  clear(subject){calls.push(['clear',subject]);return {cleared:true}}
 };
 const identities={
  alice:{subject:'issuer#alice',roles:new Set(['drive.reader','drive.manager'])},
  bob:{subject:'issuer#bob',roles:new Set(['drive.reader'])},
  outsider:{subject:'issuer#outsider',roles:new Set(['policy.reader'])}
 };
 return {calls,manager,index,authenticate:async token=>identities[token]||null};
}
async function request(origin,method,route,token,data){
 const res=await fetch(origin+route,{method,headers:{
  ...(token?{Authorization:'Bearer '+token}:{}),'content-type':'application/json'},
  body:data===undefined?undefined:JSON.stringify(data)});
 return {status:res.status,data:await res.json()};
}
test('Drive routes require complete trusted OIDC configuration',async()=>{
 assert.throws(()=>createHandler({},null,{authenticate:async()=>null,driveManager:{}}),
  /DRIVE_REQUIRES_OIDC_AND_INDEX/);
 assert.throws(()=>createHandler({},'local-token',{driveManager:{},driveIndex:{}}),
  /DRIVE_REQUIRES_OIDC_AND_INDEX/);
 const {server,origin}=await serve({authenticate:async()=>({
  subject:'issuer#a',roles:new Set(['drive.reader'])})});
 try{
  const result=await request(origin,'GET','/v1/drives/google/status','anything');
  assert.equal(result.status,404);
  assert.equal(result.data.error,'DRIVE_CONNECT_DISABLED');
 }finally{await new Promise(done=>server.close(done))}
});
test('Drive operations isolate owner subject and role; reject foreign caller-supplied subject',async()=>{
 const f=fixture();const {server,origin}=await serve({
  authenticate:f.authenticate,driveManager:f.manager,driveIndex:f.index});
 try{
  assert.equal((await request(origin,'GET','/v1/drives/google/status')).status,401);
  assert.equal((await request(origin,'GET','/v1/drives/google/status','outsider')).status,403);
  assert.equal((await request(origin,'POST','/v1/drives/google/sync','bob')).status,403);
  assert.equal((await request(origin,'GET','/v1/drives/google/status','bob')).status,200);
  const vis=await request(origin,'GET','/v1/drives/google/visibility','alice');
  assert.equal(vis.status,200);
  const forbidden=await request(origin,'POST','/v1/drives/google/source-control','alice',
   {sourceId:'s',searchable:false,reason:'OUT_OF_SCOPE',subject:'issuer#bob'});
  assert.equal(forbidden.status,400);
  assert.equal(forbidden.data.error,'INVALID_DRIVE_SOURCE_CONTROL');
  const allowed=await request(origin,'POST','/v1/drives/google/source-control','alice',
   {sourceId:'s',searchable:false,reason:'OUT_OF_SCOPE'});
  assert.equal(allowed.status,200);
  assert.equal((await request(origin,'POST','/v1/drives/google/sync','alice')).status,200);
  assert.equal((await request(origin,'POST','/v1/drives/google/clear-index','alice')).status,200);
  assert.equal((await request(origin,'GET','/v1/drives/google/start','alice')).status,404);
  assert.equal((await request(origin,'GET','/v1/contracts/published','alice')).status,403);
  for(const call of f.calls)assert.notEqual(call[1],'issuer#outsider');
  assert.equal(f.calls.filter(x=>x[0]==='control').length,1);
  assert.deepEqual(f.calls.find(x=>x[0]==='control')[3],
   {sourceId:'s',searchable:false,reason:'OUT_OF_SCOPE'});
 }finally{await new Promise(done=>server.close(done))}
});
test('existing shared local token cannot activate Drive routes',async()=>{
 const server=http.createServer(createHandler({},'test-local-token',{
  driveManager:null,driveIndex:null}));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
  const origin='http://127.0.0.1:'+server.address().port;
  const r=await request(origin,'GET','/v1/drives/google/status','test-local-token');
  assert.equal(r.status,404);
 }finally{await new Promise(done=>server.close(done))}
});
