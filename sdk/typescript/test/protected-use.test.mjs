import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {ProtectedUseClient} from '../dist/protected-use.js';

const decision='123e4567-e89b-42d3-a456-426614174000';
const receiptId='123e4567-e89b-42d3-a456-426614174001';
const sha=text=>createHash('sha256').update(text).digest('hex');

test('protected response SDK rejects unsafe endpoints before any network request',()=>{
 for(const url of ['http://evil.invalid','http://localhost:80',
   'https://guest:password@trusted.invalid','https://trusted.invalid?q=1',
   'https://trusted.invalid/#fragment','https://trusted.invalid\\etc',
   'file:///tmp/config','http://127.0.0.1:0'])
  assert.throws(()=>new ProtectedUseClient(url,'test-owner-token'));
 assert.doesNotThrow(()=>new ProtectedUseClient('https://trust.example.invalid',
   'test-owner-token'));
});

test('protected response SDK hashes answer locally and releases only exact matching permit',async()=>{
 const saved=globalThis.fetch,calls=[];
 const answer='Customer-approved example: inspect the cited exception first.';
 try{
   globalThis.fetch=async(url,opts)=>{
     calls.push([url,opts]);
     const sent=JSON.parse(opts.body);
     assert.equal(sent.answerSha256,sha(answer));
     assert.ok(!opts.body.includes(answer));
     return new Response(JSON.stringify({
       schema:'qualityrag.protected-decision-use/v1',
       permission:'PERMIT_SIGNED_ASSERTION_USE',
       decisionId:decision,requestId:'request-01',
       answerSha256:sent.answerSha256,
       policySha256:'b'.repeat(64),checkedAt:new Date().toISOString(),
       at:new Date().toISOString(),receiptId,chainHash:'c'.repeat(64),
       globalEnforcement:false,answerSemanticsVerified:false,
       independentPublisherVerified:false,externallyAnchored:false,
       scope:'THIS_REGISTRY_CHECK_ONLY'
     }),{status:200});
   };
   const client=new ProtectedUseClient('http://127.0.0.1:5055','test-owner-token');
   const permitted=await client.releaseAnswer(decision,'request-01',answer);
   assert.equal(permitted.answer,answer);
   assert.equal(permitted.receipt.answerSha256,sha(answer));
   assert.equal(calls.length,1);
   assert.equal(calls[0][1].cache,'no-store');
   assert.equal(calls[0][1].redirect,'error');
   assert.ok(calls[0][0].endsWith(decision+'/use-check'));
 }finally{globalThis.fetch=saved}
});

test('protected response SDK refuses errors, forged permits and unrelated answer hashes',async()=>{
 const saved=globalThis.fetch;
 try{
   const client=new ProtectedUseClient('https://trust.example.invalid','test-owner-token');
   for(const [status,body] of [
     [403,{error:'PROTECTED_OWNER_EXCLUDED_SOURCE'}],
     [409,{error:'PROTECTED_USE_POLICY_CHANGED'}],
     [200,{schema:'qualityrag.protected-decision-use/v1',
       permission:'PERMIT_SIGNED_ASSERTION_USE',decisionId:decision,
       requestId:'request-02',answerSha256:'a'.repeat(64),
       policySha256:'b'.repeat(64),receiptId,chainHash:'c'.repeat(64),
       globalEnforcement:false,answerSemanticsVerified:false,
       independentPublisherVerified:false,externallyAnchored:false,
       scope:'THIS_REGISTRY_CHECK_ONLY'}],
     [200,{schema:'qualityrag.protected-decision-use/v1',
       permission:'PERMIT_SIGNED_ASSERTION_USE',decisionId:decision,
       requestId:'request-02',answerSha256:sha('hold'),
       policySha256:'b'.repeat(64),receiptId,chainHash:'c'.repeat(64),
       globalEnforcement:false,answerSemanticsVerified:true,
       independentPublisherVerified:false,externallyAnchored:false,
       scope:'THIS_REGISTRY_CHECK_ONLY'}]
   ]){
     globalThis.fetch=async()=>new Response(JSON.stringify(body),{status});
     await assert.rejects(client.releaseAnswer(decision,'request-02','hold'),
       /Protected evidence use refused/);
   }
   await assert.rejects(client.releaseAnswer(decision,'bad request id','hold'),
     /Invalid protected answer request/);
 }finally{globalThis.fetch=saved}
});
