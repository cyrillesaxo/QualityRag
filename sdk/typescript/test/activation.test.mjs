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
  for(const value of [undefined,NaN,Infinity,()=>true,Symbol('fixture'),1n]){
    await assert.rejects(client.request('status',{extra:value}),/Unsupported JSON value/);
  }
  assert.throws(()=>new ActivationClient('http://127.0.0.1:9',{...token,extra:undefined}),/Unsupported JSON value/);
});

test('activation SDK refuses unsupported routes before sending',async()=>{
  const client=new ActivationClient('http://127.0.0.1:9',token);
  await assert.rejects(client.request('execute-arbitrary',{}),/Unsupported SDK route/);
});
