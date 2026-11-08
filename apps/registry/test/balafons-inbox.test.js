import test from 'node:test';
import assert from 'node:assert/strict';
import {PgBalafonsEvidenceInbox} from '../src/balafons-inbox.js';
const e={event_id:'00000000-0000-4000-8000-000000000001',tenant_id:'balafons:alice',principal_id:'alice',source_id:'balafons:alice:s',action:'index',revision:'a'.repeat(64),content:'private',metadata:{},acl:{owner_id:'alice',visibility:'private'}};
test('replay and inbox insertion share a transaction',async()=>{
 const calls=[],pool={connect:async()=>({query:async(q)=>{calls.push(q);return {rowCount:1}},release:()=>{}})};
 assert.equal(await new PgBalafonsEvidenceInbox(pool).accept(e),true);
 assert.equal(calls[0],'BEGIN');assert.match(calls[1],/ON CONFLICT\(event_id\) DO NOTHING/);
 assert.match(calls[2],/INSERT INTO qr_balafons_evidence_inbox/);assert.equal(calls[3],'COMMIT');
});
test('rollback on inbox insertion failure',async()=>{
 const calls=[],pool={connect:async()=>({query:async(q)=>{calls.push(q);if(q.includes('INSERT INTO qr_balafons_evidence_inbox'))throw Error('database down');return {rowCount:1}},release:()=>{}})};
 await assert.rejects(new PgBalafonsEvidenceInbox(pool).accept(e),/database down/);assert.equal(calls.at(-1),'ROLLBACK');
});
test('cross-user source cannot be queued',async()=>{
 const inbox=new PgBalafonsEvidenceInbox({connect:async()=>{throw Error('must not connect')}});
 await assert.rejects(inbox.accept({...e,source_id:'balafons:bob:s'}),/INVALID_EVIDENCE_OWNER/);
});
test('claim uses SKIP LOCKED and completion is tenant scoped',async()=>{
 const calls=[],inbox=new PgBalafonsEvidenceInbox({connect:()=>{},query:async(q,args)=>{calls.push([q,args]);return {rows:[],rowCount:1}}});
 await inbox.claimBatch(5);await inbox.complete({eventId:e.event_id,tenantId:e.tenant_id,principalId:e.principal_id});
 assert.match(calls[0][0],/SKIP LOCKED/);assert.deepEqual(calls[0][1],[5]);assert.match(calls[1][0],/tenant_id=\$2 AND principal_id=\$3/);
});
