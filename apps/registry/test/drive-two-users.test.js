import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {randomBytes} from 'node:crypto';
import {GoogleDriveConnections} from '../src/google-drive-connections.js';

// Two identities use ONE platform OAuth client but keep separate authorizations.
test('independent OIDC subjects connect, retain, and revoke only their own Drive credentials',async()=>{
 const root=mkdtempSync(path.join(os.tmpdir(),'qualityrag-two-drive-users-'));
 const alice='https://issuer.example#alice',bob='https://issuer.example#bob';
 const requests=[];
 const response=(data,status=200)=>({ok:status>=200&&status<300,status,
   text:async()=>JSON.stringify(data)});
 const fetchImpl=async(url,options={})=>{
   const address=String(url);
   requests.push({url:address,body:String(options.body||'')});
   if(address==='https://oauth2.googleapis.com/token'){
     const params=new URLSearchParams(options.body);
     if(params.get('grant_type')==='authorization_code'){
       const who=params.get('code')==='alice-code'?'alice':
         params.get('code')==='bob-code'?'bob':null;
       assert.ok(who,'unexpected authorization code');
       return response({access_token:'access-'+who+'-abcdefghijklmnop',
         refresh_token:'refresh-'+who+'-abcdefghijklmnop',
         expires_in:3600,scope:'https://www.googleapis.com/auth/drive.readonly'});
     }
     assert.fail('unexpected refresh flow');
   }
   if(address.startsWith('https://www.googleapis.com/drive/v3/about')){
     const authorization=options.headers.Authorization;
     const who=authorization.includes('access-alice-')?'alice':
       authorization.includes('access-bob-')?'bob':null;
     assert.ok(who,'unexpected bearer credential');
     return response({user:{email:who+'@example.test',displayName:who}});
   }
   if(address==='https://oauth2.googleapis.com/revoke')return response({});
   assert.fail('unexpected external request '+address);
 };
 try{
   const manager=new GoogleDriveConnections({
     file:path.join(root,'secrets.json'),
     encryptionKey:randomBytes(32).toString('base64'),
     clientId:'test-client-id.apps.googleusercontent.com',
     clientSecret:'test-secret-only-123',
     redirectUri:'http://127.0.0.1:5055/v1/drives/google/callback',
     studioOrigin:'http://127.0.0.1:5173',fetchImpl
   });
   const a=manager.start(alice),b=manager.start(bob);
   const state=x=>new URL(x.authorizationUrl).searchParams.get('state');
   assert.notEqual(state(a),state(b));
   await manager.callback({state:state(a),code:'alice-code'});
   assert.equal(manager.status(alice).email,'alice@example.test');
   assert.equal(manager.status(bob).connected,false);
   await manager.callback({state:state(b),code:'bob-code'});
   assert.equal(manager.status(bob).email,'bob@example.test');
   assert.equal(await manager.getToken(alice),'access-alice-abcdefghijklmnop');
   assert.equal(await manager.getToken(bob),'access-bob-abcdefghijklmnop');
   await assert.rejects(manager.callback({state:state(a),code:'alice-code'}),
     /DRIVE_OAUTH_STATE_INVALID/);
   const result=await manager.disconnect(alice);
   assert.equal(result.connected,false);
   assert.equal(manager.status(alice).connected,false);
   assert.equal(manager.status(bob).connected,true);
   assert.equal(await manager.getToken(bob),'access-bob-abcdefghijklmnop');
   const revoke=requests.find(x=>x.url==='https://oauth2.googleapis.com/revoke');
   assert.ok(revoke);
   assert.equal(new URLSearchParams(revoke.body).get('token'),
     'refresh-alice-abcdefghijklmnop');
   assert.equal(requests.filter(x=>x.url==='https://oauth2.googleapis.com/revoke').length,1);
 }finally{rmSync(root,{recursive:true,force:true})}
});
