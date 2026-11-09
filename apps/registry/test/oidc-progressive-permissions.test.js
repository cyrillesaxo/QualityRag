import test from 'node:test';
import assert from 'node:assert/strict';
import {permissionFor,ROLE} from '../src/oidc.js';

test('retains existing contract and policy governance permissions',()=>{
 const expectations=[
  ['GET','/v1/contracts/published',ROLE.read],
  ['GET','/v1/contracts/resolve/data-contract',ROLE.read],
  ['POST','/v1/contracts/validate',ROLE.author],
  ['POST','/v1/contracts/signed',ROLE.author],
  ['POST','/v1/contracts/signed/data-contract/1/approve',ROLE.approve],
  ['POST','/v1/contracts/signed/data-contract/1/publish',ROLE.publish],
  ['POST','/v1/signed/promotions',ROLE.author],
  ['POST','/v1/bindings',ROLE.publish],
  ['GET','/v1/state',ROLE.read]
 ];
 for(const [method,path,role] of expectations)assert.equal(permissionFor(method,path),role,path);
});
test('Drive folder modification requires drive.manager, not drive.reader',()=>{
 for(const path of ['/v1/drives/google/start','/v1/drives/google/folder','/v1/drives/google/disconnect',
   '/v1/drives/google/source-control','/v1/drives/google/sync','/v1/drives/google/clear-index']){
   assert.equal(permissionFor('POST',path),ROLE.driveManage,path);
 }
 for(const path of ['/v1/drives/google/status','/v1/drives/google/folders','/v1/drives/google/files',
   '/v1/drives/google/index','/v1/drives/google/visibility']){
   assert.equal(permissionFor('GET',path),ROLE.driveRead,path);
 }
});
test('evidence admission and release use narrow roles; revocation requires reviewer',()=>{
 const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',p='/v1/evidence/protected-decisions/'+id;
 assert.equal(permissionFor('POST','/v1/evidence/protected-admit'),ROLE.evidenceIngest);
 for(const action of ['use-check','deliver','grounded-deliver','sufficiency-check','relation-check'])
  assert.equal(permissionFor('POST',p+'/'+action),ROLE.evidenceIngest,action);
 assert.equal(permissionFor('POST',p+'/revoke'),ROLE.evidenceReview);
 assert.equal(permissionFor('GET',p+'/status'),ROLE.evidenceRead);
 assert.equal(permissionFor('GET',p+'/export'),ROLE.evidenceRead);
 assert.equal(permissionFor('POST','/v1/evidence/evaluations'),ROLE.evidenceIngest);
});
test('unknown paths and wrong HTTP methods remain deny-by-default',()=>{
 for(const [method,path] of [['POST','/v1/drives/google/status'],
   ['GET','/v1/drives/google/start'],['DELETE','/v1/drives/google/folder'],
   ['POST','/v1/contracts/published'],['GET','/v1/evidence/protected-admit'],
   ['POST','/v1/evidence/protected-decisions/invalid/revoke'],
   ['POST','/v1/evidence/protected-decisions/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/secret']]){
  assert.equal(permissionFor(method,path),null,method+' '+path);
 }
});
