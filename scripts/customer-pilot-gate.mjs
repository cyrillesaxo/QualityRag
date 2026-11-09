#!/usr/bin/env node
// Structural pilot-evidence validator. NEVER authenticates customer identity,
// validates a security report's conclusion, or declares a production pilot accepted.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

const REQUIRED=['A1_OWNER_DRIVE_SCOPE','A2_DISTANT_EXCEPTION_DENIAL',
 'A3_INDEPENDENT_SIGNED_REVIEW','A4_CROSS_DOCUMENT_CONFLICT',
 'A5_REVOCATION_AND_MUTATION','A6_TENANT_ISOLATION',
 'A7_TELEMETRY_AND_COVERAGE'];
function main(file){
 const faults=[],missing=[];
 if(!file){process.stderr.write('Usage: node scripts/customer-pilot-gate.mjs <packet.json>\n');process.exitCode=2;return}
 const base=path.dirname(path.resolve(file));
 let data;
 try{data=JSON.parse(fs.readFileSync(file,'utf8'))}
 catch{data=null;faults.push('PACKET_UNREADABLE')}
 if(!data||typeof data!=='object'||Array.isArray(data))data={};
 if(data.schema!=='qualityrag.customer-pilot-evidence/v1')faults.push('SCHEMA_INVALID');
 for(const key of ['pilotId','customerOperator','targetEnvironment','candidateCommitSha','runStartedAt','runCompletedAt']){
  if(typeof data[key]!=='string'||!data[key].trim())missing.push(key);
 }
 if(!/^[0-9a-f]{40}$/.test(data.candidateCommitSha||''))faults.push('CANDIDATE_COMMIT_INVALID');
 if(!Number.isFinite(Date.parse(data.runStartedAt))||
    !Number.isFinite(Date.parse(data.runCompletedAt))||
    Date.parse(data.runCompletedAt)<Date.parse(data.runStartedAt))
  faults.push('RUN_INTERVAL_INVALID');
 function checkArtifact(record,where){
  if(!record||typeof record!=='object'||record.status!=='PASS'){
   missing.push(where+':PASS');return;
  }
  if(typeof record.artifact!=='string'||record.artifact.length>200||
     !/^[A-Za-z0-9._/-]+$/.test(record.artifact)||path.isAbsolute(record.artifact)){
   faults.push(where+':ARTIFACT_PATH_INVALID');return;
  }
  const full=path.resolve(base,record.artifact);
  if(!full.startsWith(base+path.sep)){
   faults.push(where+':ARTIFACT_OUTSIDE_PACKET');return;
  }
  try{
   const stat=fs.lstatSync(full),canonical=fs.realpathSync(full);
   if(!stat.isFile()||stat.isSymbolicLink()||!canonical.startsWith(base+path.sep)||
      stat.size===0||stat.size>2_000_000)throw Error('bad_file');
   const digest=createHash('sha256').update(fs.readFileSync(full)).digest('hex');
   if(digest!==record.sha256)throw Error('hash_mismatch');
  }catch{faults.push(where+':ARTIFACT_UNAVAILABLE_OR_DIGEST_MISMATCH')}
 }
 for(const key of REQUIRED)checkArtifact(data.scenarios?.[key],key);
 for(const key of ['securityReview','customerSignoff']){
  const item=data[key];
  if(!item||item.status!=='APPROVED'||typeof item.reviewer!=='string'||!item.reviewer.trim()){
   missing.push(key+':HUMAN_APPROVAL');continue;
  }
  checkArtifact({...item,status:'PASS'},key);
 }
 const complete=faults.length===0&&missing.length===0;
 process.stdout.write(JSON.stringify({
  schema:'qualityrag.customer-pilot-gate-result/v1',
  evidencePacketComplete:complete,
  pilotAccepted:false,
  independentAuthenticityVerified:false,
  customerIdentityVerified:false,
  productionDeploymentVerified:false,
  status:complete?'READY_FOR_INDEPENDENT_HUMAN_AUDIT':'INCOMPLETE_OR_INVALID',
  scenariosPresent:REQUIRED.length,
  faults,missing,
  caveat:'Checks file completeness and local SHA-256 integrity only. It never approves a pilot or validates signers.'
 },null,2)+'\n');
 if(!complete)process.exitCode=2;
}
main(process.argv[2]);
