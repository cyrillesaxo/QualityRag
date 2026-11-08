import test from 'node:test';
import assert from 'node:assert/strict';
import {BalafonsIndexWorker} from '../src/balafons-index-worker.js';
const event={event_id:'evt1',tenant_id:'balafons:alice',principal_id:'alice',source_id:'balafons:alice:doc',action:'index',revision:'r1',content:'Nursing contraindication',metadata:{},acl:{owner_id:'alice',visibility:'private'}};
function fake(rows){const calls=[];const pool={connect:async()=>({query:async(sql,args)=>{calls.push([sql,args]);return sql.startsWith('SELECT *')?{rows}:{rowCount:1}},release:()=>{}})};return {pool,calls}}
test('worker indexes source and completes event in one transaction',async()=>{
 const {pool,calls}=fake([event]);assert.deepEqual(await new BalafonsIndexWorker({pool}).processBatch(),{processed:1});
 assert.equal(calls[0][0],'BEGIN');assert.ok(calls.some(x=>x[0].includes('INSERT INTO qr_source_chunks')));
 assert.ok(calls.some(x=>x[0].includes("state='completed'")));assert.equal(calls.at(-1)[0],'COMMIT');
});
test('worker deletes source on tombstone without reinsertion',async()=>{
 const {pool,calls}=fake([{...event,action:'delete',content:null}]);await new BalafonsIndexWorker({pool}).processBatch();
 assert.ok(calls.some(x=>x[0].startsWith('DELETE FROM qr_source_chunks')));assert.ok(!calls.some(x=>x[0].includes('INSERT INTO qr_source_chunks')));
});
test('worker fails closed and rolls back on cross-tenant event',async()=>{
 const {pool,calls}=fake([{...event,principal_id:'bob'}]);await assert.rejects(new BalafonsIndexWorker({pool}).processBatch(),/INBOX_SCOPE_INVALID/);
 assert.equal(calls.at(-1)[0],'ROLLBACK');assert.ok(!calls.some(x=>x[0].includes('INSERT INTO qr_source_chunks')));
});
