import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {randomBytes} from 'node:crypto';
import {GoogleDriveConnections} from '../src/google-drive-connections.js';
import {parseProtectedDriveServices} from '../src/protected-drive.js';

function instance(root){
  return new GoogleDriveConnections({
    file:path.join(root,'secrets.json'),
    encryptionKey:randomBytes(32).toString('base64'),
    clientId:'test-client-id.apps.googleusercontent.com',
    clientSecret:'test-secret-only-123',
    redirectUri:'http://127.0.0.1:5055/v1/drives/google/callback',
    studioOrigin:'http://127.0.0.1:5173',
    fetchImpl:()=>{throw Error('NETWORK_UNEXPECTED')}
  });
}
test('Drive OAuth is scoped and PKCE-enabled but does not connect or download on start',()=>{
 const root=mkdtempSync(path.join(os.tmpdir(),'qualityrag-connector-unit-'));
 try{
  const manager=instance(root);
  const subject='https://issuer.example#alice';
  assert.equal(manager.status(subject).connected,false);
  const start=manager.start(subject);
  const url=new URL(start.authorizationUrl);
  assert.equal(url.hostname,'accounts.google.com');
  assert.equal(url.searchParams.get('scope'),'https://www.googleapis.com/auth/drive.readonly');
  assert.equal(url.searchParams.get('code_challenge_method'),'S256');
  assert.ok(url.searchParams.get('code_challenge'));
  assert.ok(url.searchParams.get('state'));
  assert.equal(url.searchParams.has('client_secret'),false);
  assert.equal(manager.status(subject).connected,false);
 }finally{rmSync(root,{recursive:true,force:true})}
});
test('configuration rejects invalid callback and key',()=>{
 const root=mkdtempSync(path.join(os.tmpdir(),'qualityrag-connector-invalid-'));
 try{
  const manager=instance(root);
  const options={
    file:path.join(root,'secrets.json'),
    encryptionKey:manager.key.toString('base64'),
    clientId:'test-client-id.apps.googleusercontent.com',
    clientSecret:'test-secret-only-123',
    redirectUri:'https://example.com/not-callback',
    studioOrigin:'http://127.0.0.1:5173'
  };
  assert.throws(()=>new GoogleDriveConnections(options),/INVALID_DRIVE_REDIRECT/);
  assert.throws(()=>new GoogleDriveConnections({...options,
    redirectUri:'http://127.0.0.1:5055/v1/drives/google/callback',
    encryptionKey:'invalid'}),/INVALID_DRIVE_ENCRYPTION_KEY|DRIVE_ENCRYPTION_KEY_REQUIRED/);
 }finally{rmSync(root,{recursive:true,force:true})}
});
test('protected-service parser rejects ambiguous or duplicate scopes',()=>{
 assert.deepEqual([...parseProtectedDriveServices('alpha@dev,beta@prod')],['alpha@dev','beta@prod']);
 assert.equal(parseProtectedDriveServices('').size,0);
 assert.throws(()=>parseProtectedDriveServices('alpha@dev,alpha@dev'),/DUPLICATE_PROTECTED_DRIVE_SERVICE/);
 assert.throws(()=>parseProtectedDriveServices('invalid'),/INVALID_PROTECTED_DRIVE_SERVICES/);
});
