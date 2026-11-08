import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {connectorKeyFromBase64,sealConnectorCredential,openConnectorCredential} from '../src/connector-vault.js';
const key=randomBytes(32),base={tenantId:'tenant1',principalId:'user1',provider:'google',connectionId:'connection1'};
test('encryption roundtrip without exposing token',()=>{
 const credential={refresh_token:'sensitive-refresh',scope:'drive.readonly'};
 const record=sealConnectorCredential(key,{...base,credential});
 assert.equal(JSON.stringify(record).includes('sensitive-refresh'),false);
 assert.deepEqual(openConnectorCredential(key,{...base,record}),credential);
 assert.notEqual(sealConnectorCredential(key,{...base,credential}).nonce,record.nonce);
});
test('cross tenant and cross user access fails closed',()=>{
 const record=sealConnectorCredential(key,{...base,credential:{refresh_token:'secret'}});
 for(const override of [{tenantId:'tenant2'},{principalId:'user2'},{connectionId:'connection2'},{provider:'microsoft'}]){
  assert.throws(()=>openConnectorCredential(key,{...base,...override,record}),/CONTEXT_MISMATCH/);
 }
 assert.throws(()=>openConnectorCredential(randomBytes(32),{...base,record}),/DECRYPT_FAILED/);
});
test('tampered ciphertext fails authentication',()=>{
 const record=sealConnectorCredential(key,{...base,credential:{refresh_token:'secret'}});
 const bytes=Buffer.from(record.ciphertext,'base64');bytes[0]^=1;
 assert.throws(()=>openConnectorCredential(key,{...base,record:{...record,ciphertext:bytes.toString('base64')}}),/DECRYPT_FAILED/);
});
test('key validation requires canonical 32-byte base64',()=>{
 assert.deepEqual(connectorKeyFromBase64(key.toString('base64')),key);
 assert.throws(()=>connectorKeyFromBase64('abc'),/INVALID_CONNECTOR_KEY/);
});
