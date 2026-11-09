import test from 'node:test';
import assert from 'node:assert/strict';
import {ProtectedUseClient} from '../dist/protected-use.js';
const id='d0df1e40-7342-41be-b5f4-e3f5b62a0001';
const a='google_drive/'+'a'.repeat(32);
const b='google_drive/'+'b'.repeat(32);
function report(){
 return {
   schema:'qualityrag.cross-document-relation-candidates/v1',
   status:'POTENTIAL_CROSS_SOURCE_CONFLICTS',
   candidateCount:1,findingsTruncated:false,bothSignedConflicts:0,
   sourcesScanned:2,linesScanned:8,relationEdgesParsed:2,
   findings:[{
     category:'INVERSE_PAYER_PAYEE',
     left:{sourceId:a,lineNumber:3,signedSupportingWitness:true},
     right:{sourceId:b,lineNumber:1,signedSupportingWitness:false},
     reviewState:'NEEDS_EXPLICIT_CROSS_SOURCE_ADJUDICATION'
   }],
   scope:'LIVE_VERIFIED_INCLUDED_SELECTED_FOLDER_TEXT_FILES',
   sourceTextIncluded:false,actorNamesIncluded:false,
   crossFileSemanticEntailmentVerified:false,
   authoritativenessVerified:false,semanticCompletenessVerified:false,
   supportedPatternCoverageOnly:true,
   decisionId:id,checkedAt:new Date().toISOString(),
   releasePermittedByThisPreview:false,
   nextAction:'CUSTOMER_ADJUDICATE_CROSS_DOCUMENT_RELATION'
 };
}
test('client receives metadata-only relation candidates and explicitly no release permission',async()=>{
 const old=globalThis.fetch;let request;
 try{
   globalThis.fetch=async(url,init)=>{
     request={url,init};
     return new Response(JSON.stringify(report()),{status:200});
   };
   const client=new ProtectedUseClient('https://registry.example.invalid','signed-owner-token');
   const result=await client.checkCrossDocumentRelations(id,'rel-001');
   assert.equal(result.candidateCount,1);
   assert.equal(result.releasePermittedByThisPreview,false);
   assert.equal(result.authoritativenessVerified,false);
   assert.ok(request.url.endsWith(id+'/relation-check'));
   assert.deepEqual(JSON.parse(request.init.body),{requestId:'rel-001'});
   assert.equal(request.init.redirect,'error');
 }finally{globalThis.fetch=old}
});
test('client refuses forged, unbounded, or overstated relationship coverage',async()=>{
 const old=globalThis.fetch;
 try{
   const client=new ProtectedUseClient('https://registry.example.invalid','signed-owner-token');
   for(const [status,mutate] of [
     [403,x=>x],
     [409,x=>x],
     [200,x=>{x.releasePermittedByThisPreview=true;return x}],
     [200,x=>{x.semanticCompletenessVerified=true;return x}],
     [200,x=>{x.actorNamesIncluded=true;return x}],
     [200,x=>{x.findings[0].left.sourceId='leaked-provider-name';return x}],
     [200,x=>{x.candidateCount=0;return x}],
     [200,x=>{x.findingsTruncated=true;return x}],
     [200,x=>{x.decisionId='another-decision';return x}],
     [200,x=>{x.status='NO_SUPPORTED_RELATION_CONFLICTS_FOUND';return x}]
   ]){
     globalThis.fetch=async()=>new Response(JSON.stringify(mutate(report())),{status});
     await assert.rejects(
       client.checkCrossDocumentRelations(id,'rel-002'),
       /Cross-document relation check denied/);
   }
   await assert.rejects(
     client.checkCrossDocumentRelations(id,'invalid identifier with space'),
     /Invalid cross-document relation request/);
 }finally{globalThis.fetch=old}
});
