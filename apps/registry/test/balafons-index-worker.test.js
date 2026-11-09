import test from 'node:test';
import assert from 'node:assert/strict';
import {BalafonsIndexWorker} from '../src/balafons-index-worker.js';
const event={event_id:'evt1',tenant_id:'balafons:alice',principal_id:'alice',source_id:'balafons:alice:doc',source_sequence:1,action:'index',revision:'r1',content:'Nursing contraindication',metadata:{},acl:{owner_id:'alice',visibility:'private'}};
function fake(rows){const calls=[];const pool={connect:async()=>({query:async(sql,args)=>{calls.push([sql,args]);return sql.startsWith('SELECT *')?{rows}:sql.startsWith('SELECT source_sequence')?{rows:[]}:{rowCount:1}},release:()=>{}})};return {pool,calls}}
test('worker indexes source and completes event in one transaction',async()=>{
 const {pool,calls}=fake([event]);assert.deepEqual(await new BalafonsIndexWorker({pool}).processBatch(),{processed:1});
 assert.equal(calls[0][0],'BEGIN');assert.ok(calls.some(x=>x[0].includes('INSERT INTO qr_source_chunks')));
 assert.ok(calls.some(x=>x[0].includes("state='completed'")));assert.equal(calls.at(-1)[0],'COMMIT');
});
test('worker deletes source on tombstone without reinsertion',async()=>{
 const {pool,calls}=fake([{...event,action:'delete',content:null}]);await new BalafonsIndexWorker({pool}).processBatch();
 assert.ok(calls.some(x=>x[0].startsWith('DELETE FROM qr_source_chunks')));assert.ok(!calls.some(x=>x[0].includes('INSERT INTO qr_source_chunks')));
});
test('worker quarantines cross-tenant event without indexing',async()=>{
 const {pool,calls}=fake([{...event,principal_id:'bob'}]);assert.deepEqual(await new BalafonsIndexWorker({pool}).processBatch(),{processed:0});
 assert.equal(calls.at(-1)[0],'COMMIT');assert.ok(calls.some(x=>x[0].includes("state='failed'")));assert.ok(!calls.some(x=>x[0].includes('INSERT INTO qr_source_chunks')));
});
