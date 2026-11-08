import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {ProtectedUseClient} from '../dist/protected-use.js';
const sha=x=>createHash('sha256').update(x,'utf8').digest('hex');
const id='cd5b3ca5-731a-4435-bc59-123456789abc';
const receipt='cd5b3ca5-731a-4435-bc59-987654321abc';
const answer='Source-grounded extract — not a complete policy interpretation.\nRequirement: primary\n  Human-reviewed source line [policy, line 1]: Required approval\nCoverage warning: other exceptions may exist.';
function response(requestId){
 return {
   schema:'qualityrag.source-grounded-extract/v1',answer,
   sections:[{requirementId:'primary',sourceId:'google_drive/'+'a'.repeat(32),
     lineNumber:1,reviewedStatus:'HUMAN_SIGNED_SUPPORTS',
     exactSourceLine:'Required approval',adjacentContext:[]}],
   coverage:{requiredPolicyObligations:1,humanSignedSupports:1,
     allSignedAnchorsIncluded:true,adjacentContextWindowLines:1,
     fullDocumentExaminedForExceptions:false},
   assertions:{exactLinesRevalidated:true,humanReviewedAnchorSemantics:true,
     modelGeneratedParaphrase:false,freeFormAnswerEntailmentVerified:false,
     documentWideCompletenessVerified:false,independentPublisherVerified:false},
   receipt:{schema:'qualityrag.protected-decision-use/v1',
     permission:'PERMIT_SIGNED_ASSERTION_USE',decisionId:id,requestId,
     answerSha256:sha(answer),policySha256:'a'.repeat(64),chainHash:'b'.repeat(64),
     receiptId:receipt,globalEnforcement:false,answerSemanticsVerified:false,
     externallyAnchored:false,scope:'THIS_REGISTRY_CHECK_ONLY',
     deliveryMode:'SOURCE_GROUNDED_EXTRACT'},
   delivery:'SERVER_GENERATED_EXTRACT_ONLY',
   answerSemanticsVerified:false,globalEnforcement:false,externallyAnchored:false
 };
}
test('grounded extraction requests no answer prose and verifies bounded receipts',async()=>{
 const saved=globalThis.fetch;const captures=[];
 try{
   globalThis.fetch=async(url,init)=>{
     captures.push({url,init});
     assert.deepEqual(JSON.parse(init.body),{requestId:'extract-001'});
     return new Response(JSON.stringify(response('extract-001')),{status:200});
   };
   const client=new ProtectedUseClient('https://registry.example.invalid','token-owner');
   const result=await client.extractFromReviewedSources(id,'extract-001');
   assert.equal(result.answer,answer);
   assert.equal(result.sections.length,1);
   assert.equal(result.receipt.deliveryMode,'SOURCE_GROUNDED_EXTRACT');
   assert.ok(captures[0].url.endsWith(id+'/grounded-deliver'));
 }finally{globalThis.fetch=saved}
});
test('grounded extraction rejects fake coverage and altered source response digest',async()=>{
 const saved=globalThis.fetch;
 try{
   const client=new ProtectedUseClient('https://registry.example.invalid','token-owner');
   for(const [status,mutator] of [
     [403,x=>x],
     [409,x=>x],
     [200,x=>{x.answer='fabricated answer';return x}],
     [200,x=>{x.coverage.allSignedAnchorsIncluded=false;return x}],
     [200,x=>{x.coverage.fullDocumentExaminedForExceptions=true;return x}],
     [200,x=>{x.assertions.freeFormAnswerEntailmentVerified=true;return x}],
     [200,x=>{x.receipt.deliveryMode='SERVER_BUFFERED_RELEASE';return x}],
     [200,x=>{x.receipt.decisionId='other';return x}],
     [200,x=>{x.sections=[];return x}]
   ]){
     globalThis.fetch=async()=>new Response(
       JSON.stringify(mutator(response('extract-002'))),{status});
     await assert.rejects(client.extractFromReviewedSources(id,'extract-002'),
       /Grounded extraction denied/);
   }
 }finally{globalThis.fetch=saved}
});
