#!/usr/bin/env node
// Reproducible synthetic integration evidence. NOT a security or customer sign-off.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdirSync,writeFileSync} from 'node:fs';
import path from 'node:path';

const out=path.resolve(process.argv[2]||'release-evidence');
mkdirSync(out,{recursive:true});
const demos=[
  ['drive-control','scripts/drive-governed-control-show-me.mjs'],
  ['signed-admission','scripts/protected-human-admission-show-me.mjs']
];
const sha256=value=>createHash('sha256').update(value).digest('hex');
const results={};
for(const [key,file] of demos){
  const stdout=execFileSync('node',[file],{encoding:'utf8',maxBuffer:1024*1024,timeout:90000});
  const data=JSON.parse(stdout);
  assert.equal(typeof data.demonstration,'string');
  results[key]={script:file,scriptOutputSha256:sha256(stdout),output:data};
}
const drive=results['drive-control'].output;
const signed=results['signed-admission'].output;
assert.equal(drive.ownerExcluded.decision,'REFUSE');
assert.equal(drive.excludedAfterResync.decision,'REFUSE');
assert.equal(drive.ownerIncludedAgain.decision,'INCONCLUSIVE');
assert.equal(drive.observedGuardTelemetry.storedPassages,0);
assert.equal(signed.dualRoleSignaturesVerified,true);
assert.equal(signed.distantExceptionScreen.candidates,1);
assert.equal(signed.distantExceptionScreen.extractBlocked,'PROTECTED_SUFFICIENCY_UNREVIEWED_SIGNAL');
assert.equal(signed.distantExceptionScreen.documentWideSemanticCompletenessVerified,false);
assert.equal(signed.sourceGroundedExtract.http,200);
assert.equal(signed.sourceGroundedExtract.documentWideCompletenessVerified,false);
assert.equal(signed.sourceGroundedExtract.originalSourceTextStoredInLedger,false);
assert.equal(signed.specificDecisionWithdrawal.useAfterWithdrawal,'PROTECTED_DECISION_REVOKED');
assert.equal(signed.offlineTamperedFile,'REJECTED');
assert.equal(signed.productionReady,false);
const packet={
  schema:'qualityrag.synthetic-release-evidence/v1',
  generatedAt:new Date().toISOString(),
  git:{sha:process.env.GITHUB_SHA||null,ref:process.env.GITHUB_REF||null,runId:process.env.GITHUB_RUN_ID||null},
  evidenceType:'synthetic-local-HTTP',
  customerWorkflowAccepted:false,
  securityReviewApproved:false,
  productionApproved:false,
  scenarios:{
    A1:{status:'PARTIAL_SYNTHETIC',evidence:'owner exclusion, resync, reinclusion; no real Google OAuth'},
    A2:{status:'SYNTHETIC_PASS',evidence:'unsigned distant exception blocks source-grounded output'},
    A3:{status:'PARTIAL_SYNTHETIC',evidence:'dual signing, grounded extract, independent Python receipt replay; no customer human review'},
    A4:{status:'NOT_COVERED_BY_THIS_PACKET',evidence:'cross-document relation tests are separate; not asserted here'},
    A5:{status:'SYNTHETIC_PASS',evidence:'decision withdrawal and tampered source failure'},
    A6:{status:'NOT_COVERED_BY_THIS_PACKET',evidence:'production tenant/OIDC isolation requires independent security review'},
    A7:{status:'PARTIAL_SYNTHETIC',evidence:'metadata-only guard telemetry counters, not deployed Studio verification'}
  },
  proofs:{
    ownerExclusion:'REFUSE',
    distantException:'PROTECTED_SUFFICIENCY_UNREVIEWED_SIGNAL',
    signedGroundedDelivery:'HTTP_200',
    withdrawal:'PROTECTED_DECISION_REVOKED',
    tamperedSource:'REJECTED',
    ledgerStoresRawPassages:false
  },
  demoOutputSha256:Object.fromEntries(Object.entries(results).map(([k,v])=>[k,v.scriptOutputSha256])),
  limitations:['Synthetic provider and identities','Ephemeral signer keys','No independently verified publisher authenticity','No deployed Studio browser acceptance','No semantic completeness guarantee','No independent security sign-off']
};
const file=path.join(out,'acceptance.json');
writeFileSync(file,JSON.stringify(packet,null,2)+'\n',{mode:0o600});
writeFileSync(path.join(out,'SHA256SUMS'),sha256(JSON.stringify(packet,null,2)+'\n')+'  acceptance.json\n',{mode:0o600});
console.log(JSON.stringify({packet:file,scenarioStatus:packet.scenarios,customerWorkflowAccepted:false},null,2));
