import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHmac,randomUUID} from 'node:crypto';
import {createBalafonsIngestHandler} from '../src/balafons-ingest-http.js';
const secret='x'.repeat(64);
function envelope(owner){const payload=JSON.stringify({schema:'qualityrag.balafons.source/v1',event_id:randomUUID(),tenant_id:'balafons:'+owner,principal_id:owner,source_id:'balafons:'+owner+':s',action:'index',revision:'a'.repeat(64),content:'private',metadata:{title:'Doc'},acl:{owner_id:owner,visibility:'private'},occurred_at:new Date().toISOString()});return {payload,signature:createHmac('sha256',secret).update(payload).digest('hex')}}
async function fixture(){const queued=[],used=new Set();const handler=createBalafonsIngestHandler({secret,resolveOwner:async req=>req.headers['x-test-owner']||null,replayStore:{claim:async e=>{if(used.has(e.eventId))return false;used.add(e.eventId);return true}},enqueue:async e=>queued.push(e)});const server=http.createServer(handler);await new Promise(r=>server.listen(0,'127.0.0.1',r));return {server,queued,url:'http://127.0.0.1:'+server.address().port}}
async function send(url,owner,e){return fetch(url,{method:'POST',headers:{'x-test-owner':owner,'x-qualityrag-signature':e.signature},body:e.payload})}
test('HTTP ingestion is private, replay protected and requires auth',async()=>{const f=await fixture();try{
 const alice=envelope('alice');assert.equal((await send(f.url,'alice',alice)).status,202);assert.equal(f.queued.length,1);
 assert.equal((await send(f.url,'alice',alice)).status,409);
 assert.equal((await send(f.url,'bob',envelope('alice'))).status,403);
 assert.equal((await send(f.url,'',envelope('alice'))).status,401);
 assert.equal((await send(f.url,'bob',envelope('bob'))).status,202);
 assert.equal(f.queued[0].tenant_id,'balafons:alice');assert.equal(f.queued[1].tenant_id,'balafons:bob');
}finally{await new Promise(r=>f.server.close(r))}});
