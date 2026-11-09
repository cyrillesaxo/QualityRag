import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomBytes,generateKeyPairSync} from 'node:crypto';
import {createPilotComponents} from '../src/pilot-components.js';

function setup(){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'qr-pilot-compose-'));
 fs.chmodSync(root,0o700);
 const k1=generateKeyPairSync('ed25519'),k2=generateKeyPairSync('ed25519');
 const trustFile=path.join(root,'trust.json');
 fs.writeFileSync(trustFile,JSON.stringify({
  custodian:{keyId:'custodian',publicKeyPem:k1.publicKey.export({type:'spki',format:'pem'})},
  meaningReviewer:{keyId:'meaning',publicKeyPem:k2.publicKey.export({type:'spki',format:'pem'})}
 }),{mode:0o600});
 const env={
  QUALITYRAG_PILOT_MODE:'true',
  QUALITYRAG_PILOT_APPROVED_NETWORK:'true',
  QUALITYRAG_AUTH_MODE:'oidc',QUALITYRAG_BIND_HOST:'127.0.0.1',
  QUALITYRAG_PILOT_DATA_DIR:root,
  QUALITYRAG_PROTECTED_DRIVE_SERVICES:'claims@staging',
  QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE:trustFile,
  QUALITYRAG_DRIVE_ENCRYPTION_KEY:randomBytes(32).toString('base64'),
  QUALITYRAG_DRIVE_INDEX_KEY:randomBytes(32).toString('base64'),
  QUALITYRAG_GOOGLE_CLIENT_ID:'synthetic-client.apps.googleusercontent.com',
  QUALITYRAG_GOOGLE_CLIENT_SECRET:'synthetic-secret-do-not-use',
  QUALITYRAG_GOOGLE_REDIRECT_URI:'http://127.0.0.1:5055/v1/drives/google/callback',
  QUALITYRAG_STUDIO_ORIGIN:'http://127.0.0.1:5173'
 };
 return {root,env,clean(){fs.rmSync(root,{recursive:true,force:true})}};
}
test('pilot is disabled by default without reading credentials',()=>{
 const x=createPilotComponents({});
 assert.equal(x.driveManager,null);
 assert.equal(x.evidenceLedger,null);
 assert.equal(x.protectedDriveServices.size,0);
});
test('pilot fail-closed rejects local tokens, public binding and missing network review',()=>{
 const f=setup();try{
  for(const [changes,reason] of [
   [{QUALITYRAG_AUTH_MODE:'local'},'PILOT_REQUIRES_OIDC'],
   [{QUALITYRAG_BIND_HOST:'0.0.0.0'},'PILOT_REQUIRES_LOOPBACK_BIND'],
   [{QUALITYRAG_PILOT_APPROVED_NETWORK:'false'},'PILOT_NETWORK_APPROVAL_REQUIRED'],
   [{QUALITYRAG_PILOT_DATA_DIR:'/tmp'},'PILOT_DIRECTORY_NOT_PRIVATE'],
   [{QUALITYRAG_PROTECTED_DRIVE_SERVICES:''},'PILOT_REQUIRED_QUALITYRAG_PROTECTED_DRIVE_SERVICES'],
   [{QUALITYRAG_DRIVE_INDEX_KEY:f.env.QUALITYRAG_DRIVE_ENCRYPTION_KEY},'PILOT_KEY_SEPARATION_REQUIRED'],
   [{QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE:'relative.json'},'PILOT_TRUST_PATH_NOT_ABSOLUTE']
  ]){
   assert.throws(()=>createPilotComponents({...f.env,...changes}),new RegExp(reason));
  }
 }finally{f.clean()}
});
test('private configured pilot components retain isolated storage and narrow scope',()=>{
 const f=setup();try{
  const pilot=createPilotComponents(f.env,{fetchImpl:()=>{throw Error('UNEXPECTED_NETWORK')}});
  assert.ok(pilot.driveManager);
  assert.ok(pilot.driveIndex);
  assert.ok(pilot.evidenceLedger);
  assert.equal(pilot.protectedDriveServices.has('claims@staging'),true);
  assert.equal(pilot.driveManager.status('issuer#alice').connected,false);
  assert.equal(pilot.driveIndex.status('issuer#alice',{connected:false}).indexed,false);
  assert.equal(pilot.evidenceLedger.list('claims','staging').observedCount,0);
  assert.equal(pilot.driveManager.file,path.join(f.root,'google-credentials.json'));
 }finally{f.clean()}
});
test('unsafe trust file permissions or symlinks refuse startup',()=>{
 const f=setup();try{
  const trust=f.env.QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE;
  fs.chmodSync(trust,0o644);
  assert.throws(()=>createPilotComponents(f.env),/PILOT_TRUST_FILE_NOT_PRIVATE/);
  fs.chmodSync(trust,0o600);
  const link=path.join(f.root,'symlink.json');
  fs.symlinkSync(trust,link);
  assert.throws(()=>createPilotComponents({...f.env,
   QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE:link}),/PILOT_TRUST_FILE_NOT_PRIVATE/);
 }finally{f.clean()}
});
