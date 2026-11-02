import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {RegistryStore,hashPolicy} from '../src/store.js';
test('draft -> approve -> bind -> resolve and rejects unapproved versions',()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'qualityrag-'));
 try {
  const s=new RegistryStore(path.join(dir,'state.json'));
  s.register({id:'claims-api',displayName:'Claims API'},'admin');
  const policy={id:'eligibility',version:'1.0.0',requirements:[{id:'rule',min_independent_sources:2}]};
  s.draft(policy,'admin');
  assert.throws(()=>s.bind('claims-api','prod','eligibility','1.0.0','admin'),/UNAPPROVED_POLICY/);
  s.approve('eligibility','1.0.0','admin');
  s.bind('claims-api','prod','eligibility','1.0.0','admin');
  assert.deepEqual(s.resolve('claims-api','prod').policy,policy);
  assert.equal(s.resolve('claims-api','prod').sha256,hashPolicy(policy));
  assert.throws(()=>s.draft(policy,'admin'),/VERSION_EXISTS/);
  assert.equal(new RegistryStore(path.join(dir,'state.json')).resolve('claims-api','prod').status,'APPROVED');
 } finally {rmSync(dir,{recursive:true,force:true})}
});
