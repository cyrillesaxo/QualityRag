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
   const next={generation:args[1],binding_digest:args[2],
     cursor_version:existing?existing.cursor_version+1:0,
     encrypted_cursor:JSON.parse(args[3]),stale:false};
   if(existing?.generation===args[1])return {rowCount:0,rows:[]};
   rows.set(key,next);return {rowCount:1,rows:[{cursor_version:next.cursor_version}]};
  }
  if(sql.includes('SELECT'))return {rowCount:existing?1:0,rows:existing?[{...existing}]:[]};
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
    f.idx.encode(owner,{cursor:'initial'}));
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
    f.idx.encode(owner,{cursor:'initial'}));
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
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}));
  const cp=await f.coordinator.read(owner);
  const params={subject:owner,generation:cp.generation,binding:cp.binding_digest,
    version:cp.cursor_version,encryptedCursor:f.idx.encode(owner,{cursor:'next'})};
  assert.equal(await f.coordinator.advance(params),'ADVANCED');
  assert.equal(await f.coordinator.advance(params),'CONFLICT');
 }finally{f.cleanup()}
});
test('baseline generation mismatch makes an otherwise fresh selected folder UNKNOWN',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}));
  f.idx.save(owner,{...f.snapshot,baselineId:'different-baseline'});
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});

test('byte drift persists STALE through shared coordinator before CHANGED',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}));
  f.connector.downloadSelectedText=async()=>Buffer.from('Changed document bytes');
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'CHANGED');
  assert.equal((await f.coordinator.read(owner)).stale,true);
 }finally{f.cleanup()}
});
test('folder inventory drift persists STALE without waiting for change pagination',async()=>{
 const f=fixture();
 try{
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}));
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
  await f.coordinator.establish(owner,f.snapshot,f.idx.encode(owner,{cursor:'initial'}));
  f.connector.downloadSelectedText=async()=>Buffer.from('Changed');
  f.coordinator.markStale=async()=>{throw Error('PG_UNAVAILABLE')};
  assert.equal((await f.idx.inspectSelectedFolderDrift(owner,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});
