import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {PgDriveOAuthPending} from '../src/pg-drive-oauth-pending.js';

const state=randomBytes(32).toString('base64url');
const pending={subject:'issuer#alice',verifier:randomBytes(32).toString('base64url'),
 at:Date.parse('2026-11-11T10:00:00.000Z')};
function fixture(now=()=>Date.parse('2026-11-11T10:00:00.000Z')){
 const rows=new Map(),queries=[];
 const query=async(sql,args=[])=>{
  queries.push({sql,args});
  const key=args[0],record=rows.get(key);
  if(sql.includes('INSERT INTO')){
   if(record)return {rowCount:0,rows:[]};
   rows.set(key,{encrypted_pending:JSON.parse(args[1]),expires_at:args[2]});
   return {rowCount:1,rows:[{state_key:key}]};
  }
  if(sql.includes('DELETE')&&sql.includes('RETURNING')){
   if(!record)return {rowCount:0,rows:[]};
   rows.delete(key);
   return {rowCount:1,rows:[{encrypted_pending:record.encrypted_pending,
     valid:record.expires_at>now()}]};
  }
  if(sql.includes('DELETE'))return {rowCount:0,rows:[]};
  throw Error('UNEXPECTED_QUERY');
 };
 const keys={identityKey:randomBytes(32),encryptionKey:randomBytes(32)};
 const pool={query};
 return {rows,queries,first:new PgDriveOAuthPending(pool,{...keys,now}),
   second:new PgDriveOAuthPending(pool,{...keys,now})};
}
test('PKCE verifier and identity are encrypted in shared pending state',async()=>{
 const f=fixture();
 await f.first.issue(state,pending);
 const row=[...f.rows.values()][0];
 assert.equal(JSON.stringify(row).includes('issuer#alice'),false);
 assert.equal(JSON.stringify(row).includes(pending.verifier),false);
 assert.equal(JSON.stringify(f.queries).includes(state),false);
});
test('another instance can consume a valid state exactly once',async()=>{
 const f=fixture();
 await f.first.issue(state,pending);
 const consumed=await f.second.consume(state);
 assert.deepEqual(consumed,pending);
 await assert.rejects(f.first.consume(state),/DRIVE_OAUTH_STATE_INVALID/);
});
test('expired state is consumed and cannot be retried',async()=>{
 let instant=Date.parse('2026-11-11T10:00:00.000Z');
 const f=fixture(()=>instant);
 await f.first.issue(state,pending);
 instant+=600001;
 await assert.rejects(f.second.consume(state),/DRIVE_OAUTH_STATE_INVALID/);
 assert.equal(f.rows.size,0);
});
test('invalid state is refused without database insertion',async()=>{
 const f=fixture();
 await assert.rejects(f.first.issue('short',pending),/DRIVE_OAUTH_STATE_INVALID/);
 assert.equal(f.rows.size,0);
});
test('wrong encryption key cannot consume another deployments pending state',async()=>{
 const f=fixture();
 await f.first.issue(state,pending);
 const rogue=new PgDriveOAuthPending({query:async(sql,args)=>{
  const item=f.rows.get(args[0]);
  return {rowCount:1,rows:[{encrypted_pending:item.encrypted_pending,valid:true}]};
 }},{identityKey:f.first.key,encryptionKey:randomBytes(32)});
 await assert.rejects(rogue.consume(state),/DRIVE_OAUTH_STATE_INVALID/);
});
