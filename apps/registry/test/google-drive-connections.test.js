import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {GoogleDriveConnections} from '../src/google-drive-connections.js';
import {createHandler} from '../src/server.js';
import {RegistryStore} from '../src/store.js';
import {permissionFor} from '../src/oidc.js';

const identity={
  alice:{subject:'https://issuer.example#alice',
    roles:new Set(['drive.reader','drive.manager'])},
  bob:{subject:'https://issuer.example#bob',
    roles:new Set(['drive.reader','drive.manager'])},
  readonly:{subject:'https://issuer.example#alice',
    roles:new Set(['drive.reader'])},
  outsider:{subject:'https://issuer.example#outsider',
    roles:new Set(['policy.reader'])}
};
const issued=[];
const requests=[];
function json(value,status=200){
  return {ok:status>=200&&status<300,status,text:async()=>JSON.stringify(value)};
}
async function providerMock(location,options={}){
  const url=new URL(location),method=options.method||'GET';
  requests.push({url:url.origin+url.pathname,method,auth:options.headers?.Authorization||null});
  if(url.hostname==='oauth2.googleapis.com'&&url.pathname==='/token'){
    const params=new URLSearchParams(options.body);
    if(params.get('grant_type')==='authorization_code'){
      const code=params.get('code');
      if(!['code-alice','code-bob','code-bob-again'].includes(code))return json({error:'invalid_grant'},400);
      const user=code==='code-alice'?'alice':'bob';
      return json({access_token:'access-token-'+user+'-AAAAAAAAAAAAAAAA',
        refresh_token:'refresh-token-'+user+'-BBBBBBBBBBBBBBBB',
        expires_in:3600,scope:'https://www.googleapis.com/auth/drive.readonly'});
    }
    if(params.get('grant_type')==='refresh_token'){
      const user=params.get('refresh_token').includes('alice')?'alice':'bob';
      return json({access_token:'refreshed-access-token-'+user+'-AAAAAA',expires_in:3600});
    }
    return json({},400);
  }
  if(url.hostname==='oauth2.googleapis.com'&&url.pathname==='/revoke')return json({});
  if(url.hostname==='www.googleapis.com'&&url.pathname==='/drive/v3/about'){
    const user=options.headers.Authorization.includes('alice')?'alice':'bob';
    return json({user:{emailAddress:user+'@example.org',displayName:user.toUpperCase()}});
  }
  if(url.hostname==='www.googleapis.com'&&url.pathname==='/drive/v3/files'){
    const user=options.headers.Authorization.includes('alice')?'alice':'bob';
    const q=url.searchParams.get('q');
    if(q?.includes('mimeType'))return json({files:[{
      id:'folder-'+user,name:'Private '+user,
      mimeType:'application/vnd.google-apps.folder'
    }]});
    return json({files:[{id:'document-'+user,name:user+' private test file',
      mimeType:'application/pdf',size:'120',modifiedTime:'2026-11-08T18:40:00Z'}]});
  }
  if(url.hostname==='www.googleapis.com'&&url.pathname.startsWith('/drive/v3/files/')){
    const id=url.pathname.split('/').at(-1);
    return json({id,name:'Folder '+id,mimeType:'application/vnd.google-apps.folder',trashed:false});
  }
  throw Error('Unexpected external destination '+location);
}

test('per-user Google OAuth connection, encrypted storage, folder scope and disconnect',async()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-personal-drive-'));
  const file=path.join(directory,'drive-credentials.json');
  const params={file,encryptionKey:randomBytes(32).toString('base64'),
    clientId:'test-client-id.apps.googleusercontent.com',
    clientSecret:'fake-test-secret-12345',
    redirectUri:'http://127.0.0.1:5055/v1/drives/google/callback',
    studioOrigin:'http://127.0.0.1:5173',fetchImpl:providerMock};
  const manager=new GoogleDriveConnections(params);
  const registry=new RegistryStore(path.join(directory,'registry.json'));
  const server=http.createServer(createHandler(registry,null,{
    authenticate:async token=>identity[token]||null,driveManager:manager
  }));
  await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
  const host='http://127.0.0.1:'+server.address().port;
  const req=async(method,route,as,payload)=>{
    const res=await fetch(host+route,{method,redirect:'manual',headers:{
      ...(as?{Authorization:'Bearer '+as}:{}),
      'Content-Type':'application/json'
    },body:payload===undefined?undefined:JSON.stringify(payload)});
    let data={};if(res.status!==303)data=await res.json();
    return {status:res.status,data,location:res.headers.get('location')};
  };
  try{
    const aStart=await req('POST','/v1/drives/google/start','alice');
    assert.equal(aStart.status,200,JSON.stringify(aStart.data));
    const authURL=new URL(aStart.data.authorizationUrl);
    assert.equal(authURL.hostname,'accounts.google.com');
    assert.ok(authURL.searchParams.get('code_challenge'));
    assert.equal(authURL.searchParams.get('scope'),'https://www.googleapis.com/auth/drive.readonly');
    assert.equal(authURL.searchParams.has('client_secret'),false);
    assert.equal((await req('GET','/v1/drives/google/status','outsider')).status,403);
    assert.equal((await req('POST','/v1/drives/google/start','readonly')).status,403);
    assert.equal((await req('GET','/v1/drives/google/status')).status,401);

    const aliceState=authURL.searchParams.get('state');
    const callback=await req('GET','/v1/drives/google/callback?state='+aliceState+'&code=code-alice');
    assert.equal(callback.status,303);
    assert.equal(callback.location,'http://127.0.0.1:5173/?drive=connected');
    assert.equal((await req('GET','/v1/drives/google/callback?state='+aliceState+'&code=code-bob')).location,
      'http://127.0.0.1:5173/?drive=authorization-failed');

    const bStart=await req('POST','/v1/drives/google/start','bob');
    const bobState=new URL(bStart.data.authorizationUrl).searchParams.get('state');
    assert.equal((await req('GET','/v1/drives/google/callback?state='+bobState+'&code=code-bob')).status,303);
    const alice=await req('GET','/v1/drives/google/status','alice');
    const bob=await req('GET','/v1/drives/google/status','bob');
    assert.equal(alice.data.email,'alice@example.org');
    assert.equal(bob.data.email,'bob@example.org');
    assert.equal(alice.data.folderId,null);
    assert.equal(bob.data.folderId,null);
    assert.equal(alice.data.ingestionStatus,'NOT_CONFIGURED');

    const afolders=await req('GET','/v1/drives/google/folders?parentId=root','alice');
    const bfolders=await req('GET','/v1/drives/google/folders?parentId=root','bob');
    assert.equal(afolders.data.folders[0].id,'folder-alice');
    assert.equal(bfolders.data.folders[0].id,'folder-bob');
    assert.equal((await req('POST','/v1/drives/google/folder','alice',
      {folderId:'folder-alice',subject:identity.bob.subject})).status,400);
    assert.equal((await req('POST','/v1/drives/google/folder','alice',
      {folderId:'folder-alice'})).status,200);
    assert.equal((await req('GET','/v1/drives/google/status','bob')).data.folderId,null);
    assert.equal((await req('GET','/v1/drives/google/files','bob')).status,409);
    const preview=await req('GET','/v1/drives/google/files','alice');
    assert.equal(preview.status,200);
    assert.equal(preview.data.files[0].name,'alice private test file');
    assert.equal(preview.data.indexed,false);
    assert.equal(JSON.stringify(preview.data).includes('access-token'),false);

    const disk=fs.readFileSync(file,'utf8');
    assert.ok(!disk.includes('access-token'));
    assert.ok(!disk.includes('refresh-token'));
    assert.ok(!disk.includes('alice@example.org'));
    assert.ok(!disk.includes('bob@example.org'));
    assert.ok(!disk.includes(identity.alice.subject));
    assert.equal(fs.statSync(file).mode&0o077,0);

    const reloaded=new GoogleDriveConnections(params);
    assert.equal(reloaded.status(identity.alice.subject).email,'alice@example.org');
    assert.equal(reloaded.status(identity.bob.subject).email,'bob@example.org');
    assert.equal(reloaded.status(identity.alice.subject).folderId,'folder-alice');

    const disconnected=await req('POST','/v1/drives/google/disconnect','alice');
    assert.equal(disconnected.data.revoked,true);
    assert.equal((await req('GET','/v1/drives/google/status','alice')).data.connected,false);
    assert.equal((await req('GET','/v1/drives/google/status','bob')).data.connected,true);
    assert.ok(requests.every(x=>x.url.startsWith('https://')));
  }finally{
    await new Promise(ok=>server.close(ok));
    fs.rmSync(directory,{recursive:true,force:true});
  }
});

test('Google configuration refuses invalid redirect and encryption key',()=>{
  const base={file:'/tmp/local.json',
    encryptionKey:randomBytes(32).toString('base64'),
    clientId:'test-client-id.apps.googleusercontent.com',
    clientSecret:'fake-test-secret-12345',
    redirectUri:'http://127.0.0.1:5055/v1/drives/google/callback',
    studioOrigin:'http://127.0.0.1:5173',fetchImpl:providerMock};
  assert.throws(()=>new GoogleDriveConnections({...base,redirectUri:'http://example.com/v1/drives/google/callback'}),/INVALID_DRIVE_REDIRECT/);
  assert.throws(()=>new GoogleDriveConnections({...base,encryptionKey:'not-a-key'}),/DRIVE_ENCRYPTION_KEY_REQUIRED/);
  assert.equal(permissionFor('POST','/v1/drives/google/start'),'drive.manager');
  assert.equal(permissionFor('GET','/v1/drives/google/status'),'drive.reader');
  assert.equal(permissionFor('POST','/v1/drives/google/folder'),'drive.manager');
  assert.equal(permissionFor('GET','/v1/drives/google/files'),'drive.reader');
});
