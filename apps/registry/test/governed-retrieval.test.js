import test from 'node:test';
import assert from 'node:assert/strict';
import {GovernedRetrievalPipeline} from '../src/governed-retrieval.js';
const evidence=[{source_id:'balafons:alice:doc',revision:'r1',chunk_ordinal:0,start:0,end:10,text:'private'}];
const args={tenantId:'balafons:alice',principalId:'alice',query:'private',packSpec:{id:'required'}};
test('no answer before explicit tenant-matched ADMIT',async()=>{
 let calls=0;const index={search:()=>evidence};const generate=async()=>{calls++;return 'Answer'};
 for(const verdict of ['INCONCLUSIVE','REFUSE','UNKNOWN']){
  const p=new GovernedRetrievalPipeline({index,evaluate:async()=>({verdict,tenant_id:args.tenantId,principal_id:'alice'}),generate});
  const r=await p.ask(args);assert.equal(r.status,'WITHHELD');assert.equal(r.citations.length,0);
 }
 const cross=new GovernedRetrievalPipeline({index,evaluate:async()=>({verdict:'ADMIT',tenant_id:'balafons:bob',principal_id:'bob'}),generate});
 assert.equal((await cross.ask(args)).status,'WITHHELD');assert.equal(calls,0);
 const ok=new GovernedRetrievalPipeline({index,evaluate:async()=>({verdict:'ADMIT',tenant_id:args.tenantId,principal_id:'alice'}),generate});
 const r=await ok.ask(args);assert.equal(r.status,'ANSWER');assert.equal(calls,1);assert.equal(r.citations[0].source_id,evidence[0].source_id);
});
test('missing evaluator and PackSpec fail closed',async()=>{
 assert.throws(()=>new GovernedRetrievalPipeline({index:{search:()=>[]}}),/GOVERNANCE_EVALUATOR_REQUIRED/);
 const p=new GovernedRetrievalPipeline({index:{search:()=>[]},evaluate:async()=>({verdict:'ADMIT'})});
 await assert.rejects(p.ask({...args,packSpec:null}),/PACKSPEC_REQUIRED/);
 assert.equal((await p.ask(args)).status,'WITHHELD');
});
