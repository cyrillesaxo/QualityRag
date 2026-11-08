import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac,randomUUID} from 'node:crypto';
import {createServer} from 'node:http';
import {createBalafonsIngestHandler} from '../src/balafons-ingest-http.js';
test('atomic inbox accepts verified event without separate replay claim or enqueue',async()=>{
 const secret='s'.repeat(40),event_id=randomUUID(),occurred_at=new Date().toISOString();
 const payload=JSON.stringify({schema:'qualityrag.balafons.source/v1',event_id,occurred_at,tenant_id:'balafons:alice',principal_id:'alice',source_id:'balafons:alice:doc',source_sequence:1,action:'delete',acl:{owner_id:'alice',visibility:'private'}});
 const signature=createHmac('sha256',secret).update(payload).digest('hex');let accepts=0;
 const handler=createBalafonsIngestHandler({secret,resolveOwner:async()=> 'alice',atomicInbox:{accept:async()=>{accepts++;return accepts===1}}});
 const server=createServer(handler);await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port;
 try{const send=()=>fetch(url,{method:'POST',headers:{'x-qualityrag-signature':signature},body:payload});
  assert.equal((await send()).status,202);assert.equal((await send()).status,409);assert.equal(accepts,2);
 }finally{await new Promise(r=>server.close(r))}
});
