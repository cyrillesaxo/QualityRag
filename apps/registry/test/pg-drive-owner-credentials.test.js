import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {PgDriveOwnerCredentials} from '../src/pg-drive-owner-credentials.js';

const creds=(email='owner@example.test')=>({
 access_token:'access-secret',refresh_token:'refresh-secret',expires_at:1,
 email,display_name:'Owner',folder_id:'folder1',folder_name:'Selected'
});
function fixture(){
 const calls=[],key=randomBytes(32),enc=randomBytes(32);
 let row=null,revision=0,locked=false;
 const query=async(sql,args=[])=>{
  calls.push({sql,args});
  if(sql.startsWith('SELECT revision')&&!sql.includes('FOR UPDATE'))
   return {rowCount:row?1:0,rows:row?[{...row}]:[]};
  if(sql.includes('INSERT INTO')){
   revision++;row={revision,credential_envelope:JSON.parse(args[1]),
     disconnected:false};
   return {rowCount:1,rows:[{revision}]};
  }
  if(sql.includes('SET LOCAL')||sql==='BEGIN'||sql==='COMMIT'||sql==='ROLLBACK')
   return {rowCount:0,rows:[]};
  if(sql.includes('FOR UPDATE'))return {rowCount:row?1:0,rows:row?[{...row}]:[]};
  if(sql.includes('UPDATE')&&sql.includes('credential_envelope=$2')){
   row.credential_envelope=JSON.parse(args[1]);row.revision++;
   return {rowCount:1,rows:[]};
  }
  if(sql.includes('UPDATE')&&sql.includes('disconnected=true')){
   if(!row||row.disconnected)return {rowCount:0,rows:[]};
   row.disconnected=true;row.credential_envelope=null;row.revision++;
   return {rowCount:1,rows:[{revision:row.revision}]};
  }
  throw Error('UNEXPECTED_QUERY');
 };
 const pool={query,connect:async()=>({
  query,release:()=>{locked=false}
 })};
 const store=new PgDriveOwnerCredentials(pool,{identityKey:key,encryptionKey:enc});
 return {store,calls,getRow:()=>row};
}
test('credentials are encrypted at rest and keyed per owner',async()=>{
 const f=fixture(),other=fixture();
 await f.store.authorize('issuer#alice',creds());
 const stored=f.getRow();
 assert.equal(JSON.stringify(stored).includes('access-secret'),false);
 assert.equal(JSON.stringify(stored).includes('refresh-secret'),false);
 assert.equal(JSON.stringify(f.calls).includes('issuer#alice'),false);
 assert.notEqual(f.store.owner('issuer#alice'),f.store.owner('issuer#bob'));
 assert.equal((await f.store.get('issuer#alice')).value.refresh_token,'refresh-secret');
 assert.equal(await other.store.get('issuer#alice'),null);
});
test('wrong owner cannot decrypt an envelope copied across owner rows',()=>{
 const f=fixture(),envelope=f.store.seal('issuer#alice',creds());
 assert.throws(()=>f.store.open('issuer#bob',envelope),
  /DRIVE_CREDENTIAL_INTEGRITY_FAILURE/);
});
test('refresh uses row lock and rejects account or folder changes',async()=>{
 const f=fixture();
 await f.store.authorize('issuer#alice',creds());
 const good=await f.store.refreshLocked('issuer#alice',old=>({
  ...old,access_token:'rotated',expires_at:120
 }));
 assert.equal(good.value.access_token,'rotated');
 assert.equal((await f.store.get('issuer#alice')).value.access_token,'rotated');
 assert.ok(f.calls.some(x=>x.sql.includes('FOR UPDATE')));
 await assert.rejects(f.store.refreshLocked('issuer#alice',old=>({
  ...old,folder_id:'other'
 })),/DRIVE_REFRESH_BINDING_CHANGED/);
 assert.ok(f.calls.some(x=>x.sql==='ROLLBACK'));
});
test('failed refresh rolls back without writing a new token',async()=>{
 const f=fixture();
 await f.store.authorize('issuer#alice',creds());
 await assert.rejects(f.store.refreshLocked('issuer#alice',async()=>{throw Error('GOOGLE_403')}),
  /GOOGLE_403/);
 assert.equal((await f.store.get('issuer#alice')).value.access_token,'access-secret');
});
test('disconnect removes encrypted material and blocks obsolete refresh',async()=>{
 const f=fixture();
 await f.store.authorize('issuer#alice',creds());
 assert.equal(await f.store.disconnect('issuer#alice'),true);
 assert.equal(f.getRow().credential_envelope,null);
 assert.equal(await f.store.get('issuer#alice'),null);
 await assert.rejects(f.store.refreshLocked('issuer#alice',old=>old),
  /DRIVE_CONNECTION_NOT_FOUND/);
 assert.equal(await f.store.disconnect('issuer#alice'),false);
});
test('explicit reauthorization may replace a disconnected tombstone',async()=>{
 const f=fixture();
 await f.store.authorize('issuer#alice',creds());
 await f.store.disconnect('issuer#alice');
 const version=await f.store.authorize('issuer#alice',creds('new@example.test'));
 assert.ok(version>1);
 assert.equal((await f.store.get('issuer#alice')).value.email,'new@example.test');
});
