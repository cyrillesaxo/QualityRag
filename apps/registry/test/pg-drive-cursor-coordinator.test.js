import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {PgDriveCursorCoordinator} from '../src/pg-drive-cursor-coordinator.js';

// Contract-level queries are inspected; real two-process PG integration remains pending.
const identityKey=randomBytes(32);
const snap={syncedAt:'2026-11-10T12:00:00.000Z',folderId:'f1',account:'a@example.test',
 entries:[{fileId:'f',revision:'r'}]};
const encrypted={v:1,iv:'iv',ct:'ciphertext',tag:'tag'};
test('cursor coordinator stores encrypted envelope without plain owner or token',async()=>{
 const calls=[],pool={query:async(sql,args)=>{
  calls.push({sql,args});return {rowCount:1,rows:[]};
 }};
 const c=new PgDriveCursorCoordinator(pool,{identityKey});
 const {generation,binding}=await c.establish('issuer#alice',snap,encrypted);
 assert.match(generation,/^[a-f0-9]{64}$/);assert.match(binding,/^[a-f0-9]{64}$/);
 assert.equal(calls.length,1);
 assert.equal(calls[0].args.some(v=>String(v).includes('issuer#alice')),false);
 assert.equal(calls[0].args.some(v=>String(v).includes('a@example.test')),false);
 assert.equal(JSON.parse(calls[0].args[3]).ct,'ciphertext');
});
test('CAS requires exact version/generation/binding and stale=false',async()=>{
 const calls=[],pool={query:async(sql,args)=>{calls.push({sql,args});return {rowCount:0,rows:[]}}};
 const c=new PgDriveCursorCoordinator(pool,{identityKey});
 const generation='a'.repeat(64),binding='b'.repeat(64);
 assert.equal(await c.advance({subject:'alice',generation,binding,version:3,encryptedCursor:encrypted}),'CONFLICT');
 assert.match(calls[0].sql,/cursor_version=\$4 AND stale=false/);
 assert.equal(calls[0].args[3],3);
 await assert.rejects(c.advance({subject:'alice',generation,binding,version:-1,encryptedCursor:encrypted}),
   /CURSOR_EXPECTATION_INVALID/);
});
test('confirmed stale is fenced by exact baseline and remains irreversible for same generation',async()=>{
 let count=0;
 const pool={query:async(sql)=>{
  if(sql.includes('UPDATE'))return {rowCount:count++===0?1:0,rows:[]};
  return {rowCount:1,rows:[{generation:'a'.repeat(64),binding_digest:'b'.repeat(64),stale:true}]};
 }};
 const c=new PgDriveCursorCoordinator(pool,{identityKey});
 const input={subject:'alice',generation:'a'.repeat(64),binding:'b'.repeat(64)};
 assert.equal(await c.markStale(input),'STALE');
 assert.equal(await c.markStale(input),'STALE');
});

test('same-generation establishment cannot reset a stale checkpoint',async()=>{
 const pool={query:async()=>({rowCount:0,rows:[]})};
 const c=new PgDriveCursorCoordinator(pool,{identityKey});
 await assert.rejects(c.establish('issuer#alice',snap,encrypted),
   /CURSOR_BASELINE_ALREADY_EXISTS/);
});
