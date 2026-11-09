import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {UserDriveIndex} from '../src/user-drive-index.js';

const key=()=>randomBytes(32).toString('base64');
test('encrypted Drive index resolves different owner subjects to isolated paths',()=>{
  const idx=new UserDriveIndex({dir:'/tmp/qualityrag-isolated-test',encryptionKey:key()});
  const alice=idx.location('issuer#alice');
  const bob=idx.location('issuer#bob');
  assert.notEqual(alice,bob);
  assert.ok(alice.endsWith('.json'));
  assert.equal(alice.includes('alice'),false);
  assert.equal(bob.includes('bob'),false);
});
test('encrypted snapshot does not expose private original text',()=>{
  const idx=new UserDriveIndex({dir:'/tmp/qualityrag-isolated-test',encryptionKey:key()});
  const snapshot={document:'Private synthetic contract clause'};
  const wrapped=idx.encode('issuer#alice',snapshot);
  assert.equal(wrapped.v,1);
  assert.ok(typeof wrapped.ct==='string'&&wrapped.ct.length>0);
  assert.equal(JSON.stringify(wrapped).includes(snapshot.document),false);
});
test('index rejects an invalid encryption key',()=>{
  assert.throws(()=>new UserDriveIndex({dir:'/tmp/demo',encryptionKey:'invalid'}),
    /INVALID_DRIVE_INDEX_KEY/);
});
