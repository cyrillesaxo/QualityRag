import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes,createHash} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {UserDriveIndex} from '../src/user-drive-index.js';
import {PgDriveCursorCoordinator} from '../src/pg-drive-cursor-coordinator.js';

const owner='issuer#alice';
const hash=x=>createHash('sha256').update(x).digest('hex');
function fixture(){
 const dir=mkdtempSync(join(tmpdir(),'qr-cas-integration-'));
 const encryptionKey=randomBytes(32).toString('base64');
 const identityKey=randomBytes(32);
 const rows=new Map();
 // This fake models SQL CAS atomically; real PostgreSQL cross-process proof is pending.
 const pool={query:async(sql,args)=>{
  const key=args[0],existing=rows.get(key);
  if(sql.includes('INSERT INTO')){
   if(existing)return {rowCount:0,rows:[]};
   const next={generation:args[1],binding_digest:args[2],
     cursor_version:0,encrypted_cursor:JSON.parse(args[3]),
     encrypted_snapshot:JSON.parse(args[4]),stale:false};
   rows.set(key,next);return {rowCount:1,rows:[{cursor_version:0}]};
  }
  if(sql.includes('SELECT'))return {rowCount:existing?1:0,rows:existing?[{...existing}]:[]};
  if(sql.includes('UPDATE')&&sql.includes('generation=$5')){
   if(!existing||existing.generation!==args[1]||
      existing.binding_digest!==args[2]||
      existing.cursor_version!==args[3])return {rowCount:0,rows:[]};
   existing.generation=args[4];existing.binding_digest=args[5];
   existing.encrypted_cursor=JSON.parse(args[6]);
   existing.encrypted_snapshot=JSON.parse(args[7]);existing.stale=false;
   existing.cursor_version++;
   return {rowCount:1,rows:[{cursor_version:existing.cursor_version}]};
  }
  if(sql.includes('UPDATE')&&sql.includes('stale=true')){
   if(!existing||existing.generation!==args[1]||existing.binding_digest!==args[2]||
     existing.stale)return {rowCount:0,rows:[]};
   existing.stale=true;existing.cursor_version++;return {rowCount:1,rows:[{}]};
  }
  if(sql.includes('UPDATE')){
   if(!existing||existing.generation!==args[1]||existing.binding_digest!==args[2]||
      existing.stale||existing.cursor_version!==args[3])
     return {rowCount:0,rows:[]};
   existing.encrypted_cursor=JSON.parse(args[4]);existing.cursor_version++;
   return {rowCount:1,rows:[{}]};
  }
  throw Error('UNEXPECTED_QUERY');
 }};
 const coordinator=new PgDriveCursorCoordinator(pool,{identityKey});
 const idx=new UserDriveIndex({dir,encryptionKey,cursorCoordinator:coordinator,
   now:()=>Date.parse('2026-11-10T12:05:00Z')});
 const body='Policy holds except for selected cases.';
 const connection={connected:true,email:'alice@example.test',folderId:'selected'};
 const entry={fileId:'file-1',revision:hash(body),mimeType:'text/plain',
   sourceId:'google_drive/'+'a'.repeat(32),searchEnabled:true,lines:[body]};
 const snapshot={schema:'qualityrag.user-drive-text-index/v1',
   account:connection.email,folderId:connection.folderId,
   syncedAt:'2026-11-10T12:00:00Z',baselineId:'baseline-1',
   entries:[entry],coverage:'SELECTED_FOLDER_TEXT_FILES',changePageToken:'initial'};
 idx.save(owner,snapshot);
 const connector={
   status:()=>({...connection}),
   selectedFiles:async()=>({folderId:connection.folderId,
     truncated:false,files:[{id:'file-1',mimeType:'text/plain'}]}),
   supportsText:m=>m==='text/plain',
   downloadSelectedText:async()=>Buffer.from(body),
   driveChangePage:async()=>({changes:[],nextPageToken:null,
     newStartPageToken:'next'})
 };
 return {idx,coordinator,connector,snapshot,cleanup:()=>rmSync(dir,{recursive:true,force:true})};
}
test('PG cursor mode refuses to infer MATCHED when no shared checkpoint exists',async()=>{
 const f=fixture();
 try{
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});
test('PG cursor mode advances through CAS without overwriting local index cursor',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,
    f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  const result=await f.idx.inspectSelectedFolderDrift(owner,f.connector);
  assert.equal(result.state,'MATCHED_AT_CHECK_TIME');
  assert.equal(f.idx.load(owner).changePageToken,'initial');
  const cp=await f.coordinator.read(owner);
  assert.equal(f.idx.decode(owner,cp.encrypted_cursor).cursor,'next');
 }finally{f.cleanup()}
});
test('PG cursor mode records selected-file change as durable STALE',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,
    f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.connector.driveChangePage=async()=>({
   changes:[{fileId:'file-1',removed:false,metadataAvailable:true,
     parents:['selected']}],nextPageToken:null,newStartPageToken:'next'
  });
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'CHANGED');
  assert.equal((await f.coordinator.read(owner)).stale,true);
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});
test('concurrent conditional advancement rejects stale cursor version',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  const cp=await f.coordinator.read(owner);
  const params={subject:owner,generation:cp.generation,binding:cp.binding_digest,
    version:cp.cursor_version,encryptedCursor:f.idx.encode(owner,{cursor:'next'})};
  assert.equal(await f.coordinator.advance(params),'ADVANCED');
  assert.equal(await f.coordinator.advance(params),'CONFLICT');
 }finally{f.cleanup()}
});
test('local baseline mismatch does not override the shared authoritative source',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.idx.save(owner,{...f.snapshot,baselineId:'different-baseline'});
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'MATCHED_AT_CHECK_TIME');
 }finally{f.cleanup()}
});

test('byte drift persists STALE through shared coordinator before CHANGED',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.connector.downloadSelectedText=async()=>Buffer.from('Changed document bytes');
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'CHANGED');
  assert.equal((await f.coordinator.read(owner)).stale,true);
 }finally{f.cleanup()}
});
test('folder inventory drift persists STALE without waiting for change pagination',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.connector.selectedFiles=async()=>({folderId:'selected',truncated:false,files:[
   {id:'file-1',mimeType:'text/plain'},{id:'file-2',mimeType:'text/plain'}
  ]});
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'CHANGED');
  assert.equal((await f.coordinator.read(owner)).stale,true);
 }finally{f.cleanup()}
});
test('failed durability write degrades confirmed byte change to UNKNOWN',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.connector.downloadSelectedText=async()=>Buffer.from('Changed');
  f.coordinator.markStale=async()=>{throw Error('PG_UNAVAILABLE')};
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});

test('owner resync replaces a stale checkpoint with a new fenced generation',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  const old=await f.coordinator.read(owner);
  await f.coordinator.markStale({subject:owner,generation:old.generation,
    binding:old.binding_digest});
  f.connector.driveChangeStartToken=async()=> 'new-start';
  const result=await f.idx.sync(owner,f.connector);
  assert.equal(result.indexed,true);
  const cp=await f.coordinator.read(owner);
  assert.equal(cp.stale,false);
  assert.notEqual(cp.generation,old.generation);
  assert.equal(f.idx.decode(owner,cp.encrypted_cursor).cursor,'new-start');
  assert.equal(f.idx.load(owner).changePageToken,'new-start');
 }finally{f.cleanup()}
});
test('concurrent checkpoint conflict prevents publishing losing local baseline',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  const original=f.idx.load(owner);
  f.connector.driveChangeStartToken=async()=> 'resync-start';
  f.coordinator.replaceBaseline=async()=> 'CONFLICT';
  await assert.rejects(f.idx.sync(owner,f.connector),/DRIVE_SYNC_CHECKPOINT_CONFLICT/);
  assert.deepEqual(f.idx.load(owner),original);
 }finally{f.cleanup()}
});
test('failed local index publish after checkpoint CAS remains UNKNOWN',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.connector.driveChangeStartToken=async()=> 'resync-start';
  const originalSave=f.idx.save.bind(f.idx);
  f.idx.save=()=>{throw Error('DISK_FAILURE')};
  await assert.rejects(f.idx.sync(owner,f.connector),/DISK_FAILURE/);
  f.idx.save=originalSave;
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'MATCHED_AT_CHECK_TIME');
 }finally{f.cleanup()}
});
test('two workers observing same cursor version cannot both replace baseline',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  const before=await f.coordinator.read(owner);
  const next1={...f.snapshot,baselineId:'generation-2'};
  const next2={...f.snapshot,baselineId:'generation-3'};
  assert.equal(await f.coordinator.replaceBaseline(owner,next1,
    f.idx.encode(owner,{cursor:'next-1'}),before,f.idx.encode(owner,next1)),'REPLACED');
  assert.equal(await f.coordinator.replaceBaseline(owner,next2,
    f.idx.encode(owner,{cursor:'next-2'}),before,f.idx.encode(owner,next2)),'CONFLICT');
  assert.equal((await f.coordinator.read(owner)).generation,
    f.coordinator.generation(owner,next1));
 }finally{f.cleanup()}
});

test('missing local file does not invalidate a matching shared encrypted baseline',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,
    f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.idx.clear(owner);
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,
    'MATCHED_AT_CHECK_TIME');
 }finally{f.cleanup()}
});
test('tampered shared ciphertext fails closed even with a matching local index',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,
    f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  const cp=await f.coordinator.read(owner);
  cp.encrypted_snapshot.ct='tampered';
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});

test('owner clear marks shared source baseline STALE before deleting local file',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,
   f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  const outcome=await f.idx.clearCoordinated(owner);
  assert.equal(outcome.removed,true);
  assert.equal((await f.coordinator.read(owner)).stale,true);
  assert.equal((await f.idx.sharedBound(owner,f.connector.status())),null);
 }finally{f.cleanup()}
});
test('failed shared invalidation does not clear local cache as if successful',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,
   f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  f.coordinator.markStale=async()=>{throw Error('PG_UNAVAILABLE')};
  await assert.rejects(f.idx.clearCoordinated(owner),/PG_UNAVAILABLE/);
  assert.ok(f.idx.load(owner));
 }finally{f.cleanup()}
});
test('shared mode refuses direct local-only owner source-control mutation',async()=>{
 const f=fixture();
 try{
  assert.throws(()=>f.idx.controlSource(owner,f.connector.status(),{
    sourceId:'google_drive/'+'a'.repeat(32),searchable:false,reason:'SENSITIVE'
  }),/DRIVE_SHARED_SOURCE_CONTROL_NOT_IMPLEMENTED/);
 }finally{f.cleanup()}
});
test('shared snapshot remains owner-bound and cannot be read by another subject',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,
   f.idx.encode(owner,{cursor:'initial'}),f.idx.encode(owner,f.snapshot));
  assert.equal(await f.idx.sharedBound('issuer#bob',f.connector.status()),null);
 }finally{f.cleanup()}
});
