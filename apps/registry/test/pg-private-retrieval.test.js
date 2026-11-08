import test from 'node:test';
import assert from 'node:assert/strict';
import {PgPrivateRetrievalIndex} from '../src/pg-private-retrieval.js';
test('Postgres search binds tenant and principal, never interpolates query',async()=>{
 const calls=[],pool={connect:async()=>({query:async()=>({rowCount:1}),release:()=>{}}),query:async(sql,args)=>{calls.push([sql,args]);return {rows:[]}}};
 const index=new PgPrivateRetrievalIndex(pool);await index.search({tenantId:'balafons:alice',principalId:'alice',query:'secret',limit:5});
 assert.match(calls[0][0],/tenant_id=\$1 AND principal_id=\$2/);assert.match(calls[0][0],/plainto_tsquery/);assert.deepEqual(calls[0][1],['balafons:alice','alice','secret',5]);
 await assert.rejects(index.search({tenantId:'balafons:bob',principalId:'alice',query:'secret'}),/INVALID_SOURCE_SCOPE/);
});
test('upsert replaces previous revision transactionally',async()=>{
 const calls=[],pool={query:async()=>({rows:[]}),connect:async()=>({query:async(sql,args)=>{calls.push([sql,args]);return {rowCount:1}},release:()=>{}})};
 const index=new PgPrivateRetrievalIndex(pool);
 await index.upsert({tenantId:'balafons:alice',principalId:'alice',sourceId:'balafons:alice:s1',revision:'r2',content:'nursing exception contraindication'});
 assert.equal(calls[0][0],'BEGIN');assert.match(calls[1][0],/pg_advisory_xact_lock/);assert.match(calls[2][0],/DELETE FROM qr_source_chunks/);assert.match(calls[3][0],/INSERT INTO qr_source_chunks/);assert.equal(calls.at(-1)[0],'COMMIT');
});
test('delete is owner scoped and transactional',async()=>{
 const calls=[],pool={query:async()=>({rows:[]}),connect:async()=>({query:async(sql)=>{calls.push(sql);return {rowCount:1}},release:()=>{}})};
 assert.equal(await new PgPrivateRetrievalIndex(pool).delete({tenantId:'balafons:alice',principalId:'alice',sourceId:'balafons:alice:s1'}),true);
 assert.match(calls[2],/tenant_id=\$1 AND principal_id=\$2 AND source_id=\$3/);
});
