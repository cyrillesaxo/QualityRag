import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {randomBytes} from 'node:crypto';
import {RegistryStore} from '../src/store.js';
import {EvidenceLedger} from '../src/evidence-ledger.js';
import {UserDriveIndex} from '../src/user-drive-index.js';
import {createHandler} from '../src/server.js';
import {permissionFor} from '../src/oidc.js';
import {parseProtectedDriveServices} from '../src/protected-drive.js';

const allowedServices=new Set(['claims-api@dev']);
function validEvidence(){
 return {id:'ev_'+'a'.repeat(32),requirement_id:'governing-rule',
   origin:'org_'+'b'.repeat(32),source_ref:'src_'+'c'.repeat(32),
   status:'SUPPORTS',observed_at:new Date(Date.now()-1000).toISOString()};
}

test('strict service protections require an explicit, valid service/environment configuration',()=>{
 assert.deepEqual([...parseProtectedDriveServices(' claims-api@dev ,claims-api@prod ')],
   ['claims-api@dev','claims-api@prod']);
 assert.equal(parseProtectedDriveServices('').size,0);
 assert.throws(()=>parseProtectedDriveServices('claims-api'),/INVALID_PROTECTED_DRIVE_SERVICES/);
 assert.throws(()=>parseProtectedDriveServices('claims-api@dev,claims-api@dev'),
   /DUPLICATE_PROTECTED_DRIVE_SERVICE/);
 assert.throws(()=>parseProtectedDriveServices('claims-api@dev;other@dev'),
   /INVALID_PROTECTED_DRIVE_SERVICES/);
 assert.equal(permissionFor('GET','/v1/evidence/enforcement'),'evidence.reader');
 assert.throws(()=>createHandler({},'local-token',{
   protectedDriveServices:allowedServices
 }),/PROTECTED_DRIVE_RUNTIME_REQUIREMENTS_UNMET/);
});

test('protected services reject forged metadata, record blocked attempts without content and keep other services unchanged',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-protected-drive-'));
 const service='claims-api',environment='dev',otherEnv='test';
 const store=new RegistryStore(path.join(dir,'registry.json'));
 store.register({id:service,displayName:'Claims assistant'},'setup');
 store.draft({id:'claims-governance',version:'1',requirements:[
   {id:'governing-rule',min_independent_sources:1}
 ]},'setup');
 store.approve('claims-governance','1','independent-reviewer');
 store.bind(service,environment,'claims-governance','1','publisher');
 store.bind(service,otherEnv,'claims-governance','1','publisher');
 const ledgerPath=path.join(dir,'evidence.jsonl');
 const ledger=new EvidenceLedger(ledgerPath);
 const index=new UserDriveIndex({dir:path.join(dir,'indices'),
   encryptionKey:randomBytes(32).toString('base64')});
 const actors={
   writer:{subject:'issuer#writer',roles:new Set(['evidence.ingest']),
     evidenceServices:new Set([service+'@'+environment,service+'@'+otherEnv])},
   reader:{subject:'issuer#reader',roles:new Set(['evidence.reader']),
     evidenceServices:new Set([service+'@'+environment,service+'@'+otherEnv])},
   unrelated:{subject:'issuer#unrelated',roles:new Set(['evidence.reader']),
     evidenceServices:new Set(['unknown@dev'])},
   anon:{subject:'issuer#anonymous',roles:new Set(['policy.reader']),
     evidenceServices:new Set([service+'@'+environment])}
 };
 const configured=new Set(allowedServices);
 const authenticator=async token=>actors[token]||null;
 const driveManager={status:()=>({connected:false})};
 const server=http.createServer(createHandler(store,null,{
   authenticate:authenticator,
   driveManager,driveIndex:index,evidenceLedger:ledger,
   protectedDriveServices:configured
 }));
 // Mutating the caller's original Set cannot silently remove enforcement.
 configured.clear();
 await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 const base='http://127.0.0.1:'+server.address().port;
 async function req(method,route,who,payload){
   const response=await fetch(base+route,{method,headers:{
     Authorization:'Bearer '+who,'Content-Type':'application/json'},
     body:payload===undefined?undefined:JSON.stringify(payload)});
   return {status:response.status,body:await response.json()};
 }
 try{
   const protectedUrl='/v1/evidence/enforcement?serviceId=claims-api&environment=dev';
   const status=await req('GET',protectedUrl,'reader');
   assert.equal(status.status,200);
   assert.equal(status.body.protected,true);
   assert.equal(status.body.mode,'BLOCK_UNATTESTED_GENERIC_EVIDENCE');
   assert.equal(status.body.genericEvidenceIngress,'BLOCKED');
   assert.equal(status.body.sourceAdmission,'NOT_ENABLED');
   assert.equal(status.body.guardTelemetry.observedBlockedAttempts,0);
   assert.ok(status.body.guardTelemetry.protectedSince);
   assert.equal(ledger.protectedScopes().has(service+'@'+environment),true);
   const stableLog=ledger.readAll().filter(x=>x.type==='protection');
   assert.equal(stableLog.length,1);
   // Explicit accidental downgrade at restart must fail rather than
   // quietly accepting source metadata with no verified Drive custody.
   assert.throws(()=>createHandler(store,null,{
     authenticate:authenticator,driveManager,driveIndex:index,
     evidenceLedger:new EvidenceLedger(ledgerPath),
     protectedDriveServices:new Set()
   }),/PROTECTED_DRIVE_CONFIGURATION_DOWNGRADE/);
   createHandler(store,null,{
     authenticate:authenticator,driveManager,driveIndex:index,
     evidenceLedger:new EvidenceLedger(ledgerPath),
     protectedDriveServices:new Set([service+'@'+environment])
   });
   assert.equal(ledger.readAll().filter(x=>x.type==='protection').length,1);
   assert.equal((await req('GET',protectedUrl,'writer')).status,403);
   assert.equal((await req('GET',protectedUrl,'unrelated')).status,403);
   assert.equal((await req('GET',protectedUrl,'anon')).status,403);
   const fakeContent='CUSTOMER PRIVATE POLICY FULL SOURCE TEXT — NEVER STORE THIS';
   const incoming={serviceId:service,environment,requestId:'protected-request-01',
     traceId:'protected-trace-01',
     evidence:[{...validEvidence(),source_ref:'src_'+'d'.repeat(32)}]};
   const denied=await req('POST','/v1/evidence/evaluations','writer',incoming);
   assert.equal(denied.status,403);
   assert.equal(denied.body.error,'PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED');
   assert.equal(denied.body.admissionStatus,'BLOCKED');
   assert.ok(!JSON.stringify(denied.body).includes('src_'));
   // Even an independently declared origin cannot unlock a protected service.
   const retry=await req('POST','/v1/evidence/evaluations','writer',{
     ...incoming,requestId:fakeContent,traceId:'another-guess',
     evidence:[{...validEvidence(),status:'SUPPORTS',origin:'org_'+'f'.repeat(32)}],
     override:true
   });
   assert.equal(retry.status,403);
   const blocked=await req('GET',protectedUrl,'reader');
   assert.equal(blocked.body.guardTelemetry.observedBlockedAttempts,2);
   assert.ok(blocked.body.guardTelemetry.lastBlockedAt);
   const listing=await req('GET',
     '/v1/evidence/evaluations?serviceId=claims-api&environment=dev','reader');
   assert.equal(listing.status,200);
   assert.equal(listing.body.observedCount,0);
   assert.equal(listing.body.summary.admit,0);
   assert.equal(listing.body.summary.blockedUnattestedIngress,2);
   const persisted=fs.readFileSync(ledgerPath,'utf8');
   assert.equal(persisted.includes(fakeContent),false);
   assert.equal(persisted.includes('src_'),false);
   assert.equal(persisted.includes('ev_'),false);
   assert.equal(persisted.includes('org_'),false);
   assert.equal(persisted.includes('protected-request-01'),false);
   assert.equal(persisted.includes('protected-trace-01'),false);
   assert.equal(new EvidenceLedger(ledgerPath).list(service,environment).summary.blockedUnattestedIngress,2);
   const unprotected=await req('POST','/v1/evidence/evaluations','writer',{
     ...incoming,environment:otherEnv,requestId:'unprotected-01'
   });
   assert.equal(unprotected.status,201,JSON.stringify(unprotected.body));
   assert.equal(unprotected.body.verdict,'ADMIT');
   const otherStatus=await req('GET',
     '/v1/evidence/enforcement?serviceId=claims-api&environment=test','reader');
   assert.equal(otherStatus.body.protected,false);
   assert.equal(otherStatus.body.genericEvidenceIngress,'ALLOWED');
   assert.equal(otherStatus.body.guardTelemetry.observedBlockedAttempts,0);
 }finally{
   await new Promise(ok=>server.close(ok));
   fs.rmSync(dir,{recursive:true,force:true});
 }
});

test('reviewer-sourced candidate telemetry has an explicit per-actor write limit',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualityrag-challenge-limit-'));
 try{
   const ledger=new EvidenceLedger(path.join(dir,'ledger.jsonl'));
   const check={
     schema:'qualityrag.drive-governed-candidate-check/v1',
     result:'INCONCLUSIVE',evaluationAdmitted:false,
     counters:{submitted:1,ownerExcluded:0,eligibleForReview:1,otherUnresolved:0}
   };
   for(let i=0;i<20;i++)
     assert.ok(ledger.recordCandidateCheck('claims-api','dev','customer-reviewer',
       'a'.repeat(64),check).id);
   assert.throws(()=>ledger.recordCandidateCheck('claims-api','dev','customer-reviewer',
     'a'.repeat(64),check),/DRIVE_CHALLENGE_RATE_LIMITED/);
   const output=ledger.list('claims-api','dev');
   assert.equal(output.summary.governedCandidateChecks,20);
   assert.equal(output.summary.governedCandidateRefusals,0);
   // Independent reviewers have separate counters.
   assert.ok(ledger.recordCandidateCheck('claims-api','dev','second-reviewer',
     'a'.repeat(64),check).id);
   assert.equal(ledger.list('claims-api','dev').summary.governedCandidateChecks,21);
 }finally{fs.rmSync(dir,{recursive:true,force:true})}
});
