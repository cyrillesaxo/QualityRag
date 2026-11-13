import test from 'node:test';
import assert from 'node:assert/strict';
import {GoogleDriveConnections} from '../src/google-drive-connections.js';

function connector(reply){
 const c=Object.create(GoogleDriveConnections.prototype);
 c.getToken=async subject=>{
   assert.equal(subject,'issuer#alice');return 'owner-private-access-token';
 };
 c.googleGet=async(token,resource,params)=>{
   assert.equal(token,'owner-private-access-token');
   return reply(resource,params);
 };
 return c;
}
test('US-068 Drive v3 starts an opaque change cursor under the connected subject',async()=>{
 const c=connector((resource,params)=>{
   assert.equal(resource,'/changes/startPageToken');
   assert.equal(params.fields,'startPageToken');
   return {startPageToken:'opaque_cursor-123'};
 });
 assert.equal(await c.driveChangeStartToken('issuer#alice'),'opaque_cursor-123');
});
test('US-068 Drive change polling is paginated and metadata-only',async()=>{
 const c=connector((resource,params)=>{
   assert.equal(resource,'/changes');
   assert.equal(params.pageToken,'opaque_cursor-123');
   assert.equal(params.includeRemoved,'true');
   assert.equal(params.pageSize,'100');
   assert.equal(params.fields.includes('file(id,mimeType,parents,trashed)'),true);
   return {changes:[{
     fileId:'file_1',removed:false,
     file:{id:'file_1',mimeType:'text/plain',parents:['folder-1'],trashed:false}
   }],nextPageToken:'opaque-next'};
 });
 const result=await c.driveChangePage('issuer#alice','opaque_cursor-123');
 assert.equal(result.nextPageToken,'opaque-next');
 assert.equal(result.newStartPageToken,null);
 assert.equal(result.changes[0].parents[0],'folder-1');
 assert.equal('content' in result.changes[0],false);
});
test('US-068 rejects invalid cursor and incomplete or malformed Google changes',async()=>{
 const bad=connector(()=>({changes:[],nextPageToken:'p1',newStartPageToken:'p2'}));
 await assert.rejects(bad.driveChangePage('issuer#alice','invalid space'),
   /INVALID_DRIVE_CHANGE_CURSOR/);
 await assert.rejects(bad.driveChangePage('issuer#alice','cursor-1'),
   /INVALID_DRIVE_CHANGE_RESPONSE/);
 const missing=connector(()=>({changes:[{fileId:'bad id',removed:false}],
   newStartPageToken:'p2'}));
 await assert.rejects(missing.driveChangePage('issuer#alice','cursor-1'),
   /INVALID_DRIVE_CHANGE_RESPONSE/);
});
