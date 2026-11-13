import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomBytes} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {UserDriveIndex} from '../src/user-drive-index.js';

const sha=x=>createHash('sha256').update(x).digest('hex');
const subject='issuer#alice',body='Policy applies except to excluded providers.';
function fixture(){
 const dir=mkdtempSync(join(tmpdir(),'qualityrag-folder-drift-'));
 const now=Date.parse('2026-11-10T12:00:00.000Z');
 const idx=new UserDriveIndex({
  dir,encryptionKey:randomBytes(32).toString('base64'),
  now:()=>now
 });
 const connection={connected:true,folderId:'folder-private',email:'alice@example.test'};
 const entry={fileId:'file-one',name:'Policy',mimeType:'text/plain',
  revision:sha(body),sourceId:'google_drive/'+'a'.repeat(32),
  searchEnabled:true,lines:[body]};
 idx.save(subject,{
  schema:'qualityrag.user-drive-text-index/v1',account:connection.email,
  folderId:connection.folderId,syncedAt:new Date(now).toISOString(),
  coverage:'SELECTED_FOLDER_TEXT_FILES',changePageToken:'cursor-01',entries:[entry]
 });
 const files=[{id:entry.fileId,mimeType:entry.mimeType}];
 const calls=[];
 const connector={
   status:s=>{assert.equal(s,subject);return {...connection}},
   selectedFiles:async()=>({folderId:connection.folderId,
     files:[...files],truncated:false}),
   supportsText:mime=>mime==='text/plain',
   downloadSelectedText:async(s,id,folder,max)=>{
     calls.push({s,id,folder,max});return Buffer.from(body);
   },
   driveChangePage:async(_s,cursor)=>({
     changes:[],nextPageToken:null,
     newStartPageToken:cursor==='cursor-01'?'cursor-02':'cursor-03'
   })
 };
 return {idx,connector,files,calls,cleanup:()=>rmSync(dir,{recursive:true,force:true})};
}
test('US-068 bounded folder poll compares owner encrypted index without mutation',async()=>{
 const f=fixture();
 try{
   const before=f.idx.load(subject);
   const checked=await f.idx.inspectSelectedFolderDrift(subject,f.connector);
   assert.equal(checked.state,'MATCHED_AT_CHECK_TIME');
   assert.equal(checked.sourceBytesVerified,true);
   assert.equal(checked.selectionCompletenessVerified,true);
   assert.equal(checked.releasePermitted,false);
   assert.equal(f.calls.length,1);
   const after=f.idx.load(subject);
   assert.deepEqual(after.entries,before.entries);
   assert.equal(after.changePageToken,'cursor-02');
   assert.equal(JSON.stringify(checked).includes('file-one'),false);
   assert.equal(JSON.stringify(checked).includes(body),false);
 }finally{f.cleanup()}
});
test('US-068 file addition, removal and changed bytes invalidate folder baseline',async()=>{
 const f=fixture();
 try{
   f.files.push({id:'new-document',mimeType:'text/plain'});
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'CHANGED');
   f.files.splice(1);
   f.files.push({id:'unsupported-file',mimeType:'application/pdf'});
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'CHANGED');
   f.files.pop();
   f.files.splice(0,1);
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'CHANGED');
   f.files.push({id:'file-one',mimeType:'text/plain'});
   f.connector.downloadSelectedText=async()=>Buffer.from('revised policy');
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'CHANGED');
 }finally{f.cleanup()}
});
test('US-068 incomplete, disconnected, wrong-folder and denied inventory are UNKNOWN',async()=>{
 const f=fixture();
 try{
   const original=f.connector.selectedFiles;
   f.connector.selectedFiles=async()=>({...await original(),truncated:true});
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
   f.connector.selectedFiles=async()=>{throw Error('GOOGLE_HTTP_403')};
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
   f.connector.status=()=>({connected:false,folderId:null,email:null});
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});
test('US-068 cannot claim unchanged if index was cleared during provider fetch',async()=>{
 const f=fixture();
 try{
   f.connector.downloadSelectedText=async()=>{
     f.idx.clear(subject);
     return Buffer.from(body);
   };
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});

test('US-068 change cursor detects selected file, selected folder, and newly added child',async()=>{
 const f=fixture();
 try{
   for(const change of [
     {fileId:'file-one',removed:false,parents:['folder-private'],metadataAvailable:true},
     {fileId:'folder-private',removed:false,parents:[],metadataAvailable:true},
     {fileId:'new-file',removed:false,parents:['folder-private'],metadataAvailable:true}
   ]){
     f.connector.driveChangePage=async()=>({
       changes:[change],nextPageToken:null,newStartPageToken:'cursor-02'
     });
     const checked=await f.idx.inspectSelectedFolderDrift(subject,f.connector);
     assert.equal(checked.state,'CHANGED');
     assert.equal(f.idx.load(subject).changePageToken,'cursor-01');
   }
 }finally{f.cleanup()}
});
test('US-068 unknown Drive cursor events, lost token and overflow never advance checkpoint',async()=>{
 const f=fixture();
 try{
   f.connector.driveChangePage=async()=>({changes:[{
     fileId:'unknown-file',removed:true,parents:[],metadataAvailable:false
   }],nextPageToken:null,newStartPageToken:'cursor-02'});
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
   assert.equal(f.idx.load(subject).changePageToken,'cursor-01');
   f.connector.driveChangePage=async()=>({changes:[],nextPageToken:'cursor-02',newStartPageToken:null});
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
   f.connector.driveChangePage=async()=>{throw Error('GOOGLE_410_CURSOR_EXPIRED')};
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
   assert.equal(f.idx.load(subject).changePageToken,'cursor-01');
   const previous=f.idx.load(subject);
   f.idx.save(subject,{...previous,changePageToken:null});
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'UNKNOWN');
 }finally{f.cleanup()}
});
test('US-068 unrelated Drive events paginate and advance encrypted cursor',async()=>{
 const f=fixture();
 try{
   const read=[];
   f.connector.driveChangePage=async(_subject,cursor)=>{
     read.push(cursor);
     return cursor==='cursor-01'?{
       changes:[{fileId:'another-folder-file',removed:false,parents:['other-folder'],metadataAvailable:true}],
       nextPageToken:'cursor-next',newStartPageToken:null
     }:{changes:[],nextPageToken:null,newStartPageToken:'cursor-latest'};
   };
   assert.equal((await f.idx.inspectSelectedFolderDrift(subject,f.connector)).state,'MATCHED_AT_CHECK_TIME');
   assert.deepEqual(read,['cursor-01','cursor-next']);
   assert.equal(f.idx.load(subject).changePageToken,'cursor-latest');
 }finally{f.cleanup()}
});

test('US-068 index sync captures owner change cursor before listing bytes',async()=>{
 const f=fixture();
 try{
   const operations=[];
   const list=f.connector.selectedFiles;
   f.connector.driveChangeStartToken=async()=>{operations.push('cursor');return 'sync-start';};
   f.connector.selectedFiles=async()=>{operations.push('listing');return list();};
   const synced=await f.idx.sync(subject,f.connector);
   assert.equal(synced.indexed,true);
   assert.deepEqual(operations.slice(0,2),['cursor','listing']);
   assert.equal(f.idx.load(subject).changePageToken,'sync-start');
 }finally{f.cleanup()}
});
