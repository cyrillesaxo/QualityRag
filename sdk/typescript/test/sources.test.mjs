import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { packSpecSource } from '../dist/sources.js';
const pack = { id:'eu', version:'1', requirements:[{id:'recovery'},{id:'eu-control'}] };

test('internal source snapshots, property validates', async () => {
  const mutable=structuredClone(pack);
  const load=packSpecSource({mode:'internal',internalPack:mutable});
  mutable.id='tampered';
  assert.equal((await load()).id,'eu');
  assert.equal((await packSpecSource({mode:'property',json:JSON.stringify(pack)})()).id,'eu');
  assert.throws(()=>packSpecSource({mode:'property',json:'{}'}));
});
test('file source re-reads and rejects bad values',async()=>{
  let contents=JSON.stringify(pack);
  const load=packSpecSource({mode:'file',path:'/policy.json',readFile:async()=>contents});
  assert.equal((await load()).id,'eu');
  contents='{}';
  await assert.rejects(load);
});
test('studio validates approved digest and fails closed',async()=>{
  const previous=globalThis.crypto;
  Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
  try {
    const digest=createHash('sha256').update(JSON.stringify(pack)).digest('hex');
    const envelope={serviceId:'app',environment:'dev',status:'APPROVED',policy:pack,sha256:digest};
    const load=packSpecSource({mode:'studio',registryUrl:'http://127.0.0.1:5055',registryToken:'token',
      serviceId:'app',environment:'dev',request:async()=>({ok:true,text:async()=>JSON.stringify(envelope)})});
    assert.equal((await load()).id,'eu');
    envelope.sha256='0'.repeat(64);
    await assert.rejects(load,/digest/);
    assert.throws(()=>packSpecSource({mode:'studio',registryUrl:'http://example.com',registryToken:'x',serviceId:'a',environment:'dev'}),/HTTPS/);
  }finally{Object.defineProperty(globalThis,'crypto',{value:previous,configurable:true});}
});
