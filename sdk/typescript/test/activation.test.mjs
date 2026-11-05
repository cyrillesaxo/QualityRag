import test from 'node:test';
import assert from 'node:assert/strict';
import {ActivationClient} from '../dist/activation.js';

const token={schema:'fixture',canonical:'fixture',key_id:'fixture',payload:{},signature:'fixture'};

test('activation endpoint rejects userinfo, remote plaintext, query, fragment and control characters',()=>{
  for(const url of ['http://127.0.0.1:80@elsewhere.invalid','https://user:password@example.invalid',
    'https://example.invalid?q=1','https://example.invalid#fragment','http://elsewhere.invalid',
    'https:///','https:///missing-host','http://127.0.0.1:0','https://example.invalid/\npath',
    'https://example.invalid\\path','http://2130706433:8769']){
    assert.throws(()=>new ActivationClient(url,token));
  }
});

test('activation endpoints accept explicit loopback and HTTPS path prefixes',()=>{
  assert.doesNotThrow(()=>new ActivationClient('http://127.0.0.1:8769',token));
  assert.doesNotThrow(()=>new ActivationClient('https://example.invalid/research/',token));
});

test('activation serialization refuses values JSON would silently change',async()=>{
  const client=new ActivationClient('http://127.0.0.1:9',token);
  for(const value of [undefined,NaN,Infinity,()=>true,Symbol('fixture'),1n,Number.MAX_SAFE_INTEGER+1]){
    await assert.rejects(client.request('status',{extra:value}),/Unsupported JSON value/);
  }
  assert.throws(()=>new ActivationClient('http://127.0.0.1:9',{...token,extra:undefined}),/Unsupported JSON value/);
});

test('activation SDK refuses unsupported routes before sending',async()=>{
  const client=new ActivationClient('http://127.0.0.1:9',token);
  await assert.rejects(client.request('execute-arbitrary',{}),/Unsupported SDK route/);
});


test('activation SDK refuses unsafe response integers instead of silently rounding',async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>new Response('{"quantity":9007199254740993}',{status:200});
    const client=new ActivationClient('http://127.0.0.1:9',token);
    await assert.rejects(client.request('status',{}),/Unsupported JSON number/);
  } finally {globalThis.fetch=original;}
});


test('gardener methods use the documented routes and payloads',async()=>{
  const original=globalThis.fetch,calls=[];
  try {
    globalThis.fetch=async(url,init)=>{calls.push([url,JSON.parse(init.body)]);return new Response('{"ok":true}',{status:200});};
    const client=new ActivationClient('http://127.0.0.1:9',token);
    await client.gardenQuery({text:'labeler',open_challenge:true,since:3});
    await client.gardenState();await client.gardenSuggestions();
    await client.gardenEvent({event_id:'e1',operation:'CHALLENGE',branch:'b',source_sha256:'a'.repeat(64),source_ref:'turn:1',statement:'s',parents:[]});
    assert.deepEqual(calls.map(([url])=>url.split('/api/')[1]),['gardener/query','gardener/state','gardener/proposals','gardener/event']);
    assert.deepEqual(calls[0][1],{text:'labeler',open_challenge:true,since:3});
  } finally {globalThis.fetch=original;}
});
