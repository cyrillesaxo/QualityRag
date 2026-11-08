import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import {randomBytes} from 'node:crypto';
import {GoogleDriveConnections} from '../src/google-drive-connections.js';
import {UserDriveIndex} from '../src/user-drive-index.js';
import {RegistryStore} from '../src/store.js';
import {createHandler} from '../src/server.js';
import {permissionFor} from '../src/oidc.js';

const FILES={
 alice:[
  {id:'alice-text',name:'Travel policy.txt',mimeType:'text/plain',parents:['folder-alice']},
  {id:'alice-doc',name:'Exception addendum',mimeType:'application/vnd.google-apps.document',parents:['folder-alice']},
  {id:'alice-pdf',name:'Scan.pdf',mimeType:'application/pdf',parents:['folder-alice']}
 ],
 bob:[{id:'bob-text',name:'Vendor policy.txt',mimeType:'text/plain',parents:['folder-bob']}]
};
const sourceBytes={
 'alice-text':'The policy has a hidden exception for contractors.\nTravel reimbursements need approval.',
 'alice-doc':'All contractors require separate authorization.\nDo not generalize to everyone.',
 'bob-text':'The bob-only vendor rule requires a permit.\nThis is not in Alice files.'
};
let contentMode='normal';
const provider=async(location,options={})=>{
 const url=new URL(location),access=String(options.headers?.Authorization||'');
 const user=access.includes('alice')?'alice':'bob';
 const str=(content,status=200)=>({ok:status>=200&&status<300,status,
   text:async()=>JSON.stringify(content)});
 const bytes=(body,status=200)=>({ok:status>=200&&status<300,status,
   headers:{get:()=>null},
   arrayBuffer:async()=>Buffer.from(body,'utf8')});
 if(url.hostname==='oauth2.googleapis.com'){
  if(url.pathname==='/revoke')return str({});
  const params=new URLSearchParams(options.body);
  const account=params.get('code')?.includes('alice')?'alice':'bob';
  return str({access_token:'access-token-'+account+'-ABCDEFGHIJKLMNOP',
    refresh_token:'refresh-token-'+account+'-ABCDEFGHIJKLMNOP',
    expires_in:3600,scope:'https://www.googleapis.com/auth/drive.readonly'});
 }
 assert.equal(url.hostname,'www.googleapis.com');
 if(url.pathname.endsWith('/about')){
  return str({user:{emailAddress:user+'@example.com',displayName:user}});
 }
 const parts=url.pathname.split('/');
 if(url.pathname==='/drive/v3/files'){
  const q=url.searchParams.get('q')||'';
  if(q.includes("mimeType = 'application/vnd.google-apps.folder'")){
   return str({files:[{id:'folder-'+user,name:'Private '+user,
     mimeType:'application/vnd.google-apps.folder'}]});
  }
  return str({files:FILES[user].map(f=>({...f,modifiedTime:'2026-11-08T12:00:00Z'}))});
 }
 const fileId=parts[4];
 if(['folder-alice','folder-bob','another-folder'].includes(fileId))
   return str({id:fileId,name:fileId,mimeType:'application/vnd.google-apps.folder',trashed:false});
 const item=[...FILES.alice,...FILES.bob].find(f=>f.id===fileId);
 if(!item)return str({error:'not found'},404);
 const own=item.id.startsWith(user+'-');
 if(!own)return str({error:'forbidden'},403);
 if(url.pathname.endsWith('/export')||url.searchParams.get('alt')==='media'){
  if(contentMode==='changed'&&fileId==='alice-text')return bytes('Changed content after syncing.');
  if(contentMode==='oversize'&&fileId==='alice-doc')return bytes('x'.repeat(100_000));
  return bytes(sourceBytes[fileId]||'');
 }
 return str({...item,trashed:false,size:item.mimeType==='text/plain'?'80':undefined});
};

test('separate encrypted Drive text indexes enforce OIDC user isolation and purge on folder change or disconnect',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-drive-index-'));
 let now=Date.now();
 const encryptionKey=randomBytes(32).toString('base64');
 const connector=new GoogleDriveConnections({
  file:path.join(dir,'drive-tokens.json'),encryptionKey,
  clientId:'local-test-client.apps.googleusercontent.com',clientSecret:'test-secret-12345',
  redirectUri:'http://127.0.0.1:5055/v1/drives/google/callback',
  studioOrigin:'http://127.0.0.1:5173',fetchImpl:provider,now:()=>now
 });
 const index=new UserDriveIndex({dir:path.join(dir,'user-indices'),encryptionKey,now:()=>now});
 for(const user of ['alice','bob']){
   const who='issuer#'+user;
   const state=new URL(connector.start(who).authorizationUrl).searchParams.get('state');
   await connector.callback({state,code:'code-'+user});
   await connector.selectFolder(who,'folder-'+user);
 }
 const roles={
   alice:{subject:'issuer#alice',roles:new Set(['drive.reader','drive.manager'])},
   bob:{subject:'issuer#bob',roles:new Set(['drive.reader','drive.manager'])},
   reader:{subject:'issuer#alice',roles:new Set(['drive.reader'])},
   outsider:{subject:'issuer#outsider',roles:new Set(['policy.reader'])}
 };
 const registry=new RegistryStore(path.join(dir,'registry.json'));
 const server=http.createServer(createHandler(registry,null,{
   authenticate:async token=>roles[token]||null,driveManager:connector,driveIndex:index
 }));
 await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 const base='http://127.0.0.1:'+server.address().port;
 const request=async(method,route,user,data)=>{
   const response=await fetch(base+route,{method,headers:{
     Authorization:'Bearer '+user,'Content-Type':'application/json'},
     body:data===undefined?undefined:JSON.stringify(data)});
   return {status:response.status,body:await response.json()};
 };
 try{
   assert.equal(permissionFor('POST','/v1/drives/google/search'),'drive.reader');
   assert.equal(permissionFor('POST','/v1/drives/google/sync'),'drive.manager');
   assert.equal((await request('POST','/v1/drives/google/sync','reader',{})).status,403);
   assert.equal((await request('POST','/v1/drives/google/search','outsider',{query:'policy'})).status,403);
   const alice=await request('POST','/v1/drives/google/sync','alice',{});
   const bob=await request('POST','/v1/drives/google/sync','bob',{});
   assert.equal(alice.status,200,JSON.stringify(alice.body));
   assert.equal(alice.body.sourceCount,2);
   assert.equal(alice.body.summary.unsupported,1);
   assert.equal(alice.body.coverage,'PARTIAL');
   assert.equal(bob.status,200,JSON.stringify(bob.body));
   assert.equal(bob.body.sourceCount,1);
   const searched=await request('POST','/v1/drives/google/search','alice',{query:'hidden exception'});
   assert.equal(searched.status,200);
   assert.equal(searched.body.hits.length,1);
   assert.equal(searched.body.hits[0].anchor.kind,'text_line');
   assert.equal(searched.body.hits[0].anchor.line_number,1);
   assert.equal(searched.body.assurance,'NOT_EVALUATED_BY_PACKSPEC');
   const bobOnly=await request('POST','/v1/drives/google/search','bob',{query:'vendor rule'});
   assert.equal(bobOnly.body.hits.length,1);
   const cannotGetBob=await request('POST','/v1/drives/google/search','alice',{query:'bob-only vendor rule'});
   assert.equal(cannotGetBob.body.hits.length,0);
   assert.equal((await request('POST','/v1/drives/google/search','alice',{query:'a',subject:'issuer#bob'})).status,400);
   const privateIndex=fs.readFileSync(index.location('issuer#alice'),'utf8');
   assert.ok(!privateIndex.includes('hidden exception'));
   assert.ok(!privateIndex.includes('Travel policy.txt'));
   assert.ok(!privateIndex.includes('alice@example.com'));
   assert.equal(fs.statSync(index.location('issuer#alice')).mode&0o077,0);
   const reloaded=new UserDriveIndex({dir:path.join(dir,'user-indices'),encryptionKey,now:()=>now});
   assert.equal(reloaded.status('issuer#alice',connector.status('issuer#alice')).sourceCount,2);
   assert.equal(reloaded.status('issuer#bob',connector.status('issuer#bob')).sourceCount,1);
   now+=61*60*1000;
   const stale=await request('POST','/v1/drives/google/search','alice',{query:'hidden exception'});
   assert.equal(stale.body.coverage,'STALE');
   assert.equal(stale.body.hits.length,0);
   now-=61*60*1000;
   contentMode='changed';
   const update=await request('POST','/v1/drives/google/sync','alice',{});
   assert.equal(update.status,200);
   const removed=await request('POST','/v1/drives/google/search','alice',{query:'hidden exception'});
   assert.equal(removed.body.hits.length,0);
   contentMode='normal';
   const selection=await request('POST','/v1/drives/google/folder','alice',{folderId:'another-folder'});
   assert.equal(selection.status,200);
   assert.equal(fs.existsSync(index.location('issuer#alice')),false);
   const nothing=await request('POST','/v1/drives/google/search','alice',{query:'travel policy'});
   assert.equal(nothing.body.reason,'NOT_INDEXED');
   assert.equal(fs.existsSync(index.location('issuer#bob')),true);
   const disconnected=await request('POST','/v1/drives/google/disconnect','bob',{});
   assert.equal(disconnected.status,200);
   assert.equal(fs.existsSync(index.location('issuer#bob')),false);
   const bobSearch=await request('POST','/v1/drives/google/search','bob',{query:'vendor'});
   assert.equal(bobSearch.status,200);
   assert.equal(bobSearch.body.reason,'NOT_INDEXED');
 }finally{
   await new Promise(ok=>server.close(ok));
   contentMode='normal';
   fs.rmSync(dir,{recursive:true,force:true});
 }
});

test('selected folder content retrieval checks real Google parent membership and file-type bounds',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-drive-safe-download-'));
 const con=new GoogleDriveConnections({
   file:path.join(dir,'tokens.json'),encryptionKey:randomBytes(32).toString('base64'),
   clientId:'test-id.apps.googleusercontent.com',clientSecret:'test-secret-123456',
   redirectUri:'http://127.0.0.1:5055/v1/drives/google/callback',
   studioOrigin:'http://127.0.0.1:5173',fetchImpl:provider
 });
 const subject='issuer#alice';
 try{
   const state=new URL(con.start(subject).authorizationUrl).searchParams.get('state');
   await con.callback({state,code:'code-alice'});
   await con.selectFolder(subject,'folder-alice');
   const bytes=await con.downloadSelectedText(subject,'alice-text','folder-alice');
   assert.ok(bytes.toString('utf8').includes('hidden exception'));
   await assert.rejects(con.downloadSelectedText(subject,'bob-text','folder-alice'),/DRIVE_AUTHORIZATION_REQUIRED/);
   await assert.rejects(con.downloadSelectedText(subject,'alice-pdf','folder-alice'),/DRIVE_UNSUPPORTED_FILE_TYPE/);
   contentMode='oversize';
   await assert.rejects(con.downloadSelectedText(subject,'alice-doc','folder-alice'),/DRIVE_SOURCE_TOO_LARGE/);
 }finally{contentMode='normal';fs.rmSync(dir,{recursive:true,force:true})}
});
