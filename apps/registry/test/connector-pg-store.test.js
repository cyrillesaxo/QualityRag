import test from 'node:test';
import assert from 'node:assert/strict';
import {PgConnectorStore} from '../src/connector-pg-store.js';
test('state insertion uses parameterized SQL',async()=>{
 const calls=[];const store=new PgConnectorStore({query:async(...args)=>{calls.push(args);return {rowCount:1,rows:[]}}});
 await store.savePending({state_hash:'x'.repeat(43),tenant_id:'t',principal_id:'p',code_verifier:'verifier',expires_at:Date.now()+60000});
 assert.equal(calls[0][1][1],'t');assert.match(calls[0][0],/INSERT INTO qr_connector_oauth_states/);
});
test('state consume is atomic and fails closed on replay',async()=>{
 let count=0;const store=new PgConnectorStore({query:async()=>{count++;return count===1?{rowCount:1,rows:[{state_hash:'hash',tenant_id:'t',principal_id:'p',code_verifier:'v',expires_at:new Date(Date.now()+60000)}]}:{rowCount:0,rows:[]}}});
 const args={stateHash:'hash',tenantId:'t',principalId:'p'};
 assert.equal((await store.consumePending(args)).consumed,true);
 await assert.rejects(store.consumePending(args),/EXPIRED_OR_USED/);
});
test('list returns no ciphertext',async()=>{
 const store=new PgConnectorStore({query:async()=>({rows:[{connection_id:'c',provider:'google',display_name:'Drive',granted_scopes:['read'],status:'connected',encrypted_record:{ciphertext:'secret'}}]})});
 const r=await store.listConnections('t','p');assert.equal(r[0].id,'c');assert.equal(JSON.stringify(r).includes('secret'),false);
});
