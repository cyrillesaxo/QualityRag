import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {ProtectedUseClient} from '../dist/protected-use.js';

const decisionId='7fda4180-9229-4b13-8e42-111111111111';
const receiptId='7fda4180-9229-4b13-8e42-222222222222';
const digest=x=>createHash('sha256').update(x,'utf8').digest('hex');
const draft='The approved synthetic source includes an exception.';
function permit(answer,requestId){
 return {schema:'qualityrag.protected-answer-delivery/v1',
   answer,delivery:'BUFFERED_SINGLE_RESPONSE',
   answerSemanticsVerified:false,globalEnforcement:false,externallyAnchored:false,
   receipt:{schema:'qualityrag.protected-decision-use/v1',
     permission:'PERMIT_SIGNED_ASSERTION_USE',decisionId,requestId,
     answerSha256:digest(answer),deliveryMode:'SERVER_BUFFERED_RELEASE',policySha256:'a'.repeat(64),
     checkedAt:new Date().toISOString(),at:new Date().toISOString(),
     receiptId,chainHash:'b'.repeat(64),globalEnforcement:false,
     answerSemanticsVerified:false,independentPublisherVerified:false,
     externallyAnchored:false,scope:'THIS_REGISTRY_CHECK_ONLY'}
 };
}
test('gateway client releases only exact buffered answer after matched registry permit',async()=>{
 const saved=globalThis.fetch;
 const requests=[];
 try{
   globalThis.fetch=async(url,init)=>{
     requests.push({url,init});
     const data=JSON.parse(init.body);
     assert.deepEqual(data,{requestId:'unique-delivery-01',answer:draft});
     return new Response(JSON.stringify(permit(draft,'unique-delivery-01')),{status:200});
   };
   const client=new ProtectedUseClient('https://customer-registry.example.invalid','signed-owner-token');
   const released=await client.deliverViaGateway(decisionId,'unique-delivery-01',draft);
   assert.equal(released.answer,draft);
   assert.equal(released.delivery,'BUFFERED_SINGLE_RESPONSE');
   assert.equal(released.receipt.answerSha256,digest(draft));
   assert.ok(requests[0].url.endsWith(decisionId+'/deliver'));
   assert.equal(requests[0].init.redirect,'error');
   assert.equal(requests[0].init.cache,'no-store');
 }finally{globalThis.fetch=saved}
});
test('gateway client refuses unauthorized release and never returns draft as fallback',async()=>{
 const saved=globalThis.fetch;
 try{
   const client=new ProtectedUseClient('http://127.0.0.1:5001','signed-owner-token');
   const original=permit(draft,'unique-delivery-02');
   const variants=[
     [403,{error:'PROTECTED_OWNER_EXCLUDED_SOURCE'}],
     [409,{error:'PROTECTED_USE_POLICY_CHANGED'}],
     [200,{...original,answer:'different response'}],
     [200,{...original,receipt:{...original.receipt,answerSha256:'0'.repeat(64)}}],
     [200,{...original,receipt:{...original.receipt,decisionId:receiptId}}],
     [200,{...original,answerSemanticsVerified:true}],
     [200,{...original,receipt:{...original.receipt,scope:'GLOBAL_AND_UNVERIFIED'}}],
     [200,{...original,delivery:'LEGACY_UNPROTECTED'}]
   ];
   for(const [status,value] of variants){
     globalThis.fetch=async()=>new Response(JSON.stringify(value),{status});
     await assert.rejects(
       client.deliverViaGateway(decisionId,'unique-delivery-02',draft),
       /Protected gateway denied delivery/);
   }
   await assert.rejects(client.deliverViaGateway(decisionId,'bad id',draft),
     /Invalid protected gateway/);
   await assert.rejects(client.deliverViaGateway(decisionId,'unique-delivery-03',
     'x'.repeat(16385)),/Invalid protected gateway/);
   await assert.rejects(client.deliverViaGateway(decisionId,'unique-delivery-03',
     'nul\0char'),/Invalid protected gateway/);
 }finally{globalThis.fetch=saved}
});
