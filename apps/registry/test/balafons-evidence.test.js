import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac,randomUUID} from 'node:crypto';
import {acceptBalafonsEvidence,PgEvidenceReplayStore} from '../src/balafons-evidence.js';
const secret='x'.repeat(64),now=Date.now();
function signed(owner='alice'){
 const e={schema:'qualityrag.balafons.source/v1',event_id:randomUUID(),tenant_id:'balafons:'+owner,principal_id:owner,
 source_id:'balafons:'+owner+':s1',source_sequence:1,action:'index',revision:'a'.repeat(64),content:'hello',metadata:{title:'Test'},acl:{owner_id:owner,visibility:'private'},occurred_at:new Date(now).toISOString()};
 const payload=JSON.stringify(e);return {payload,signature:createHmac('sha256',secret).update(payload).digest('hex')};
}
test('accepts authenticated owner only once',async()=>{
 const used=new Set(),replayStore={claim:async({eventId})=>{if(used.has(eventId))return false;used.add(eventId);return true}};
 const event=signed();const opts={...event,secret,expectedOwnerId:'alice',replayStore,now};
 assert.equal((await acceptBalafonsEvidence(opts)).tenant_id,'balafons:alice');
 await assert.rejects(acceptBalafonsEvidence(opts),/REPLAY/);
});
test('rejects another owner despite valid service signature',async()=>{
 await assert.rejects(acceptBalafonsEvidence({...signed('alice'),secret,expectedOwnerId:'bob',replayStore:{claim:async()=>true},now}),/OWNER_MISMATCH/);
});
test('rejects modified content and missing replay protection',async()=>{
 const event=signed();await assert.rejects(acceptBalafonsEvidence({...event,payload:event.payload.replace('hello','private'),secret,expectedOwnerId:'alice',replayStore:{claim:async()=>true},now}),/SIGNATURE/);
 await assert.rejects(acceptBalafonsEvidence({...event,secret,expectedOwnerId:'alice',now}),/REPLAY_STORE_REQUIRED/);
});
test('Postgres claim is atomic',async()=>{
 let sql='';const s=new PgEvidenceReplayStore({query:async(q)=>{sql=q;return {rowCount:1}}});
 assert.equal(await s.claim({eventId:randomUUID(),tenantId:'t',principalId:'p',expiresAt:new Date()}),true);
 assert.match(sql,/ON CONFLICT \(event_id\) DO NOTHING/);
});
