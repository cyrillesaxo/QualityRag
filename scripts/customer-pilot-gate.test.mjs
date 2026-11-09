import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const script=path.resolve('scripts/customer-pilot-gate.mjs');
const names=['A1_OWNER_DRIVE_SCOPE','A2_DISTANT_EXCEPTION_DENIAL',
 'A3_INDEPENDENT_SIGNED_REVIEW','A4_CROSS_DOCUMENT_CONFLICT',
 'A5_REVOCATION_AND_MUTATION','A6_TENANT_ISOLATION',
 'A7_TELEMETRY_AND_COVERAGE'];
const digest=x=>createHash('sha256').update(x).digest('hex');
function fixture(){
 const root=mkdtempSync(path.join(os.tmpdir(),'qr-pilot-gate-'));
 const artifact=path.join(root,'proofs');mkdirSync(artifact);
 const scenarios={};
 for(const [i,name] of names.entries()){
  const contents='Synthetic, NOT real customer evidence '+name;
  const relative='proofs/'+(i+1)+'.txt';
  writeFileSync(path.join(root,relative),contents);
  scenarios[name]={status:'PASS',artifact:relative,sha256:digest(contents)};
 }
 const approvals={};
 for(const name of ['securityReview','customerSignoff']){
  const contents='FAKE fixture only '+name;
  const relative='proofs/'+name+'.txt';
  writeFileSync(path.join(root,relative),contents);
  approvals[name]={status:'APPROVED',reviewer:name+'-fixture',
   artifact:relative,sha256:digest(contents)};
 }
 const data={schema:'qualityrag.customer-pilot-evidence/v1',
  pilotId:'synthetic-only',customerOperator:'synthetic-only',
  targetEnvironment:'synthetic-local',
  candidateCommitSha:'a'.repeat(40),
  runStartedAt:'2026-11-09T11:00:00.000Z',
  runCompletedAt:'2026-11-09T12:00:00.000Z',
  scenarios,...approvals};
 const file=path.join(root,'packet.json');
 const save=()=>writeFileSync(file,JSON.stringify(data));
 save();return {root,file,data,save};
}
function run(file){
 const p=spawnSync(process.execPath,[script,file],{encoding:'utf8'});
 return {status:p.status,data:JSON.parse(p.stdout)};
}
test('missing customer evidence fails closed without marking pilot accepted',()=>{
 const f=fixture();try{
  delete f.data.scenarios.A6_TENANT_ISOLATION;f.save();
  const r=run(f.file);
  assert.equal(r.status,2);assert.equal(r.data.pilotAccepted,false);
  assert.ok(r.data.missing.some(x=>x.includes('A6_TENANT_ISOLATION')));
 }finally{rmSync(f.root,{recursive:true,force:true})}
});
test('modified proof bytes and path traversal fail with no acceptance',()=>{
 const f=fixture();try{
  writeFileSync(path.join(f.root,'proofs/1.txt'),'mutated');
  let r=run(f.file);assert.equal(r.status,2);
  assert.ok(r.data.faults.some(x=>x.includes('DIGEST_MISMATCH')));
  f.data.scenarios.A1_OWNER_DRIVE_SCOPE.artifact='../secret';
  f.save();r=run(f.file);assert.equal(r.status,2);
  assert.ok(r.data.faults.some(x=>x.includes('OUTSIDE_PACKET')));
 }finally{rmSync(f.root,{recursive:true,force:true})}
});
test('even a structurally complete synthetic packet NEVER self-approves',()=>{
 const f=fixture();try{
  const r=run(f.file);
  assert.equal(r.status,0,JSON.stringify(r.data));
  assert.equal(r.data.evidencePacketComplete,true);
  assert.equal(r.data.status,'READY_FOR_INDEPENDENT_HUMAN_AUDIT');
  assert.equal(r.data.pilotAccepted,false);
  assert.equal(r.data.customerIdentityVerified,false);
  assert.equal(r.data.independentAuthenticityVerified,false);
 }finally{rmSync(f.root,{recursive:true,force:true})}
});
