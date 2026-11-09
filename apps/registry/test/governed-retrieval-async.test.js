import test from 'node:test';
import assert from 'node:assert/strict';
import {GovernedRetrievalPipeline} from '../src/governed-retrieval.js';
test('awaits asynchronous PostgreSQL retrieval before governance evaluation',async()=>{
 const rows=[{source_id:'balafons:alice:s',revision:'r1',chunk_ordinal:0,start:0,end:5,text:'hello'}];
 const p=new GovernedRetrievalPipeline({index:{search:async()=>rows},evaluate:async({evidence,tenantId,principalId})=>{
  assert.deepEqual(evidence,rows);return {verdict:'ADMIT',tenant_id:tenantId,principal_id:principalId};}});
 const result=await p.ask({tenantId:'balafons:alice',principalId:'alice',query:'hello',packSpec:{id:'p'}});
 assert.equal(result.status,'ADMITTED_EVIDENCE');assert.equal(result.citations.length,1);
});
