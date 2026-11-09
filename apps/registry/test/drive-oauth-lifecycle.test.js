import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHandler} from '../src/server.js';

function fixture(){
 const calls=[],pending=new Map(),record=new Map();
 const subject='issuer#alice';
 const driveManager={
  studioOrigin:'https://studio.example.test',
  status(owner){calls.push(['status',owner]);return {connected:record.has(owner),
    folderId:record.get(owner)?.folderId||null};},
  start(owner){calls.push(['start',owner]);const state='state-'+String(pending.size+1).padStart(40,'x');pending.set(state,owner);
   return {authorizationUrl:'https://accounts.google.com/o/oauth2/v2/auth?state='+state,scope:'drive.readonly'};},
  async callback({state,code,error}){
   calls.push(['callback',state]);const owner=pending.get(state);pending.delete(state);
   if(!owner||code!=='approved-code'||error)throw Error('INVALID_OAUTH_STATE');
   record.set(owner,{folderId:null});return {subject:owner};
  },
  async folders(owner,parent,token){calls.push(['folders',owner,parent,token]);return {folders:[{id:'folder-a'}]};},
  async selectFolder(owner,folderId){calls.push(['selectFolder',owner,folderId]);
   if(!record.has(owner))throw Error('DRIVE_CONNECTION_NOT_FOUND');
   record.get(owner).folderId=folderId;return this.status(owner);},
  async selectedFiles(owner){calls.push(['files',owner]);return {files:[{id:'file-a'}],truncated:false};},
  async disconnect(owner){calls.push(['disconnect',owner]);record.delete(owner);return {connected:false,revoked:true};}
 };
 const driveIndex={
  status(owner){return {ownerHash:'opaque',indexed:false};},
  clear(owner){calls.push(['clear',owner]);return {cleared:true};},
  visibility(owner){return {sources:[]};}
 };
 const identities={
  alice:{subject,roles:new Set(['drive.reader','drive.manager'])},
  bob:{subject:'issuer#bob',roles:new Set(['drive.reader'])},
  outsider:{subject:'issuer#outsider',roles:new Set(['policy.reader'])}
 };
 return {calls,driveManager,driveIndex,authenticate:async token=>identities[token]||null};
}
async function serve(f){
 const server=http.createServer(createHandler({},null,{authenticate:f.authenticate,
  driveManager:f.driveManager,driveIndex:f.driveIndex}));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 return {server,url:'http://127.0.0.1:'+server.address().port};
}
async function req(origin,method,route,token,body){
 const response=await fetch(origin+route,{method,redirect:'manual',headers:{
  ...(token?{authorization:'Bearer '+token}:{}),'content-type':'application/json'},
  body:body===undefined?undefined:JSON.stringify(body)});
 const data=response.status===303?null:await response.json();
 return {status:response.status,location:response.headers.get('location'),data};
}
test('OIDC owner can connect through single-use OAuth state; no bearer on callback',async()=>{
 const f=fixture(),{server,url}=await serve(f);
 try{
  assert.equal((await req(url,'POST','/v1/drives/google/start','bob')).status,403);
  assert.equal((await req(url,'POST','/v1/drives/google/start','outsider')).status,403);
  const start=await req(url,'POST','/v1/drives/google/start','alice');
  assert.equal(start.status,200);
  const state=new URL(start.data.authorizationUrl).searchParams.get('state');
  const first=await req(url,'GET','/v1/drives/google/callback?state='+state+'&code=approved-code');
  assert.equal(first.status,303);
  assert.equal(first.location,'https://studio.example.test/?drive=connected');
  const replay=await req(url,'GET','/v1/drives/google/callback?state='+state+'&code=approved-code');
  assert.equal(replay.status,303);
  assert.equal(replay.location,'https://studio.example.test/?drive=authorization-failed');
  assert.equal((await req(url,'GET','/v1/drives/google/status','alice')).data.connected,true);
  assert.equal((await req(url,'GET','/v1/drives/google/status','bob')).data.connected,false);
  assert.ok(f.calls.some(x=>x[0]==='clear'&&x[1]==='issuer#alice'));
  assert.equal((await req(url,'GET','/v1/drives/google/callback?state='+state+'&code=approved-code&next=https://evil.example')).location,
    'https://studio.example.test/?drive=authorization-failed');
 }finally{await new Promise(done=>server.close(done))}
});
test('owner folder selection, source inventory, disconnect invalidate scoped index',async()=>{
 const f=fixture(),{server,url}=await serve(f);
 try{
  const start=await req(url,'POST','/v1/drives/google/start','alice');
  const state=new URL(start.data.authorizationUrl).searchParams.get('state');
  await req(url,'GET','/v1/drives/google/callback?state='+state+'&code=approved-code');
  assert.equal((await req(url,'GET','/v1/drives/google/folders?parentId=root','alice')).status,200);
  assert.equal((await req(url,'POST','/v1/drives/google/folder','bob',{folderId:'folder-a'})).status,403);
  assert.equal((await req(url,'POST','/v1/drives/google/folder','alice',
    {subject:'issuer#bob',folderId:'folder-a'})).status,400);
  const selected=await req(url,'POST','/v1/drives/google/folder','alice',{folderId:'folder-a'});
  assert.equal(selected.status,200);
  assert.equal(selected.data.folderId,'folder-a');
  assert.equal((await req(url,'GET','/v1/drives/google/files','alice')).status,200);
  assert.equal((await req(url,'POST','/v1/drives/google/disconnect','bob')).status,403);
  assert.equal((await req(url,'POST','/v1/drives/google/disconnect','alice')).status,200);
  assert.equal((await req(url,'GET','/v1/drives/google/status','alice')).data.connected,false);
  assert.equal(f.calls.filter(x=>x[0]==='clear'&&x[1]==='issuer#alice').length,3);
  assert.equal(f.calls.filter(x=>x[0]==='selectFolder').length,1);
 }finally{await new Promise(done=>server.close(done))}
});
test('callback remains unavailable without explicit trusted Drive injection',async()=>{
 const server=http.createServer(createHandler({},'local-token'));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
  const response=await req('http://127.0.0.1:'+server.address().port,
    'GET','/v1/drives/google/callback?state=guess&code=guess');
  assert.equal(response.status,404);
 }finally{await new Promise(done=>server.close(done))}
});
