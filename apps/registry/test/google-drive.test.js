import test from 'node:test';
import assert from 'node:assert/strict';
import {inventoryGoogleDrive,googleExportMime} from '../src/google-drive.js';
test('requires authorization',async()=>{await assert.rejects(inventoryGoogleDrive(),/GOOGLE_ACCESS_TOKEN_REQUIRED/)});
test('reads paginated metadata, deduplicates and records source permissions',async()=>{
 let n=0;
 const fetchImpl=async(url,opts)=>{
  assert.equal(new URL(url).hostname,'www.googleapis.com');assert.equal(opts.headers.Authorization,'Bearer test');
  n++;return {ok:true,json:async()=>n===1?{files:[{id:'a',mimeType:'application/pdf',version:'3',permissions:[{id:'u',role:'reader'}]}],nextPageToken:'next'}:{files:[{id:'a',mimeType:'application/pdf'},{id:'b',mimeType:'text/plain'}]}};
 };
 const r=await inventoryGoogleDrive({accessToken:'test',fetchImpl});
 assert.equal(r.complete,true);assert.equal(r.files.length,2);assert.equal(r.files[0].source_id,'google-drive:a');assert.equal(r.files[0].permissions[0].role,'reader');
});
test('fails closed on incomplete search',async()=>{await assert.rejects(inventoryGoogleDrive({accessToken:'test',fetchImpl:async()=>({ok:true,json:async()=>({files:[],incompleteSearch:true})})}),/INCOMPLETE/)});
test('does not claim full coverage after page limit',async()=>{const r=await inventoryGoogleDrive({accessToken:'test',pageLimit:1,fetchImpl:async()=>({ok:true,json:async()=>({files:[],nextPageToken:'more'})})});assert.equal(r.complete,false);assert.equal(r.truncated,true)});
test('native Google documents require export',()=>{assert.equal(googleExportMime('application/vnd.google-apps.document'),'text/plain');assert.equal(googleExportMime('application/pdf'),null)});
