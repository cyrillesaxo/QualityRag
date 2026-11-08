import fs from 'node:fs';
import path from 'node:path';
import {createHash, randomUUID} from 'node:crypto';

// Opt-in, single-process, local-first evidence telemetry. Not an attested audit log.
const ZERO = '0'.repeat(64);
const hex = value => createHash('sha256').update(value).digest('hex');
const sha = value => hex(JSON.stringify(value));
const idPattern = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const limited = (value,max=80) => typeof value==='string' && value.length<=max && idPattern.test(value);
function exactKeys(obj, keys, label) {
  if(!obj || Array.isArray(obj) || typeof obj!=='object' ||
     Object.keys(obj).some(k=>!keys.includes(k)))throw Error('INVALID_'+label);
}
function validTime(value) {
  return typeof value==='string' && ISO.test(value) && Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString().slice(0,19)===value.slice(0,19);
}
function validateEvidence(evidence,pack) {
  if(!Array.isArray(evidence) || evidence.length>100)
    throw Error('INVALID_EVIDENCE');
  const requirements=new Set(pack.requirements.map(r=>r.id));
  const seen=new Set();
  for(const item of evidence){
    exactKeys(item,['id','requirement_id','origin','source_ref','status','observed_at'],'EVIDENCE');
    if(typeof item.id!=='string'||!/^ev_[a-f0-9]{24,64}$/.test(item.id)||seen.has(item.id)||
       !requirements.has(item.requirement_id)||typeof item.origin!=='string'||
       !/^org_[a-f0-9]{24,64}$/.test(item.origin)||
       typeof item.source_ref!=='string'||!/^src_[a-f0-9]{24,64}$/.test(item.source_ref)||
       !['SUPPORTS','CONTRADICTS','UNKNOWN'].includes(item.status)||
       !validTime(item.observed_at))throw Error('INVALID_EVIDENCE');
    seen.add(item.id);
  }
}
export function evaluateEvidence(pack,evidence,asOf) {
  if(!pack||!Array.isArray(pack.requirements)||!pack.requirements.length||!validTime(asOf))
    throw Error('INVALID_EVALUATION_INPUT');
  const findings=[];
  for(const req of pack.requirements) {
    const minimum=req.min_independent_sources??1;
    const maxAge=req.max_age_seconds;
    if(!Number.isSafeInteger(minimum)||minimum<1||
       (maxAge!==undefined&&(!Number.isSafeInteger(maxAge)||maxAge<0)))throw Error('INVALID_POLICY');
    const valid=[], reasons=[];
    let contradicted=false;
    for(const item of evidence.filter(x=>x.requirement_id===req.id)){
      const age=(Date.parse(asOf)-Date.parse(item.observed_at))/1000;
      if(age<0){reasons.push('FUTURE_EVIDENCE');continue}
      if(maxAge!==undefined&&age>maxAge){reasons.push('STALE_EVIDENCE');continue}
      if(item.status==='CONTRADICTS')contradicted=true;
      else if(item.status==='SUPPORTS')valid.push(item);
      else reasons.push('UNKNOWN_EVIDENCE');
    }
    const count=new Set(valid.map(x=>x.origin)).size;
    const verdict=contradicted?'REFUSE':count<minimum?'INCONCLUSIVE':'ADMIT';
    if(contradicted)reasons.push('CONTRADICTION');
    else if(count<minimum)reasons.push('INSUFFICIENT_INDEPENDENT_EVIDENCE');
    findings.push({requirement_id:req.id,verdict,independent_sources:count,
      reasons:[...new Set(reasons)].sort()});
  }
  const verdict=findings.some(x=>x.verdict==='REFUSE')?'REFUSE':
    findings.some(x=>x.verdict==='INCONCLUSIVE')?'INCONCLUSIVE':'ADMIT';
  return {schema:'qualityrag.result/v0.1',pack_id:pack.id,pack_version:pack.version,verdict,findings};
}
function publicRecord(entry){
  return {id:entry.id,serviceId:entry.serviceId,environment:entry.environment,
    requestId:entry.requestId,traceId:entry.traceId,at:entry.at,
    policySha256:entry.policySha256,evaluator:entry.evaluator,verdict:entry.result.verdict,
    findings:entry.result.findings,evidence:entry.evidence,requirements:entry.policy.requirements,
    reviewHistory:entry.reviewHistory,chainHash:entry.chainHash,declaredOriginsOnly:true};
}
export class EvidenceLedger {
  constructor(file,{maxRecords=10000}={}) {
    if(typeof file!=='string'||!file.trim())throw Error('EVIDENCE_LEDGER_PATH_REQUIRED');
    this.file=file;this.maxRecords=maxRecords;this.readAll();
  }
  readAll(){
    if(!fs.existsSync(this.file))return [];
    const content=fs.readFileSync(this.file,'utf8');
    if(content && !content.endsWith('\n'))throw Error('EVIDENCE_LEDGER_INTEGRITY_FAILURE');
    const rows=content.split('\n').filter(Boolean);
    let prev=ZERO;
    const seenIds=new Set();
    return rows.map((line,i)=>{
      let row;
      try{row=JSON.parse(line)}catch{throw Error('EVIDENCE_LEDGER_INTEGRITY_FAILURE')}
      const {chainHash,...rest}=row;
      if(row.seq!==i+1||row.previousHash!==prev||!row.id||seenIds.has(row.id)||
         typeof chainHash!=='string'||sha(rest)!==chainHash)
        throw Error('EVIDENCE_LEDGER_INTEGRITY_FAILURE');
      seenIds.add(row.id);prev=chainHash;return row;
    });
  }
  append(row) {
    const rows=this.readAll();
    if(rows.length>=this.maxRecords)throw Error('EVIDENCE_LEDGER_CAPACITY_EXCEEDED');
    const entry={seq:rows.length+1,previousHash:rows.at(-1)?.chainHash||ZERO,...row};
    entry.chainHash=sha(entry);
    fs.mkdirSync(path.dirname(this.file),{recursive:true,mode:0o700});
    const fd=fs.openSync(this.file,'a',0o600);
    try{fs.writeSync(fd,JSON.stringify(entry)+'\n');fs.fsyncSync(fd)}finally{fs.closeSync(fd)}
    return entry;
  }
  protectedScopes(){
    return new Set(this.readAll().filter(x=>
      x.type==='protection'&&x.mode==='BLOCK_UNATTESTED_GENERIC_EVIDENCE'
    ).map(x=>x.serviceId+'@'+x.environment));
  }
  protectedSince(serviceId,environment){
    return this.readAll().find(x=>x.type==='protection'&&
      x.serviceId===serviceId&&x.environment===environment)?.at||null;
  }
  recordProtectionActivation(serviceId,environment){
    if(!limited(serviceId)||!limited(environment))
      throw Error('INVALID_PROTECTED_DRIVE_SERVICES');
    if(this.protectedScopes().has(serviceId+'@'+environment))return false;
    this.append({id:randomUUID(),type:'protection',
      at:new Date().toISOString(),serviceId,environment,
      mode:'BLOCK_UNATTESTED_GENERIC_EVIDENCE',
      caveat:'REGISTRY_INGRESS_ONLY_UNATTESTED_METADATA_REJECTED'});
    return true;
  }
  recordProtectedDecision({serviceId,environment,actor,policy,policySha256,
    requestId,traceId,custody,meaning,verified,result,evidence,live}){
    if(!limited(serviceId)||!limited(environment)||
       !limited(requestId)||!limited(traceId)||
       typeof actor!=='string'||!actor||
       typeof policySha256!=='string'||!/^[a-f0-9]{64}$/.test(policySha256)||
       !verified?.payload||!['ADMIT','REFUSE','INCONCLUSIVE'].includes(result?.verdict)||
       !Array.isArray(evidence)||evidence.length<1||evidence.length>8||
       live?.verifiedExactLiveBytes!==true||live.owner!==actor)
      throw Error('INVALID_PROTECTED_DECISION');
    const nonceDigest=hex(serviceId+'@'+environment+':'+verified.payload.nonce);
    const requestHash=hex(serviceId+'@'+environment+':'+requestId);
    const records=this.readAll();
    if(records.some(x=>x.type==='protected-decision'&&x.serviceId===serviceId&&
      x.environment===environment&&x.nonceDigest===nonceDigest))
      throw Error('PROTECTED_ATTESTATION_REPLAY');
    if(records.some(x=>x.type==='protected-decision'&&x.serviceId===serviceId&&
      x.environment===environment&&x.requestHash===requestHash))
      throw Error('PROTECTED_REQUEST_REPLAY');
    const actorHash=hex(actor);
    if(records.filter(x=>x.type==='protected-decision'&&
      x.actorHash===actorHash&&Date.parse(x.at)>=Date.now()-60000).length>=10)
      throw Error('PROTECTED_DECISION_RATE_LIMITED');
    const at=new Date().toISOString();
    const row=this.append({id:randomUUID(),type:'protected-decision',
      at,serviceId,environment,actorHash,policySha256,
      requestHash,traceHash:hex(traceId),nonceDigest,
      policy:structuredClone(policy),
      evidence:structuredClone(evidence),result:structuredClone(result),
      asOf:live.checkedAt,sourceCount:live.sourceCount,
      signedCustody:structuredClone(custody),signedMeaning:structuredClone(meaning),
      signedPayloadSha256:verified.signedPayloadSha256,
      custodianKeyId:verified.signerIds[0],
      meaningReviewerKeyId:verified.signerIds[1],
      provenanceBasis:'CUSTOMER_CUSTODIAN_ATTESTED_PLUS_LIVE_GOOGLE_BYTES',
      semanticBasis:'INDEPENDENT_HUMAN_REVIEWER_ATTESTED',
      realPublisherVerified:false,externalAnchor:false});
    return {id:row.id,at,verdict:result.verdict,
      policySha256,chainHash:row.chainHash,
      sourceCount:row.sourceCount,custodianKeyId:row.custodianKeyId,
      meaningReviewerKeyId:row.meaningReviewerKeyId,
      evidenceSemantics:'HUMAN_APPROVED_CLAIM_NOT_OBJECTIVE_TRUTH',
      independentPublisherVerified:false,externallyAnchored:false,
      coverage:'ONE_PROTECTED_REGISTRY_DECISION_ONLY'};
  }
  protectedDecisionForOwner(id,actor){
    if(typeof id!=='string'||!/^[0-9a-f-]{36}$/.test(id)||
       typeof actor!=='string'||!actor)
      throw Error('PROTECTED_DECISION_NOT_FOUND');
    const row=this.readAll().find(x=>x.type==='protected-decision'&&x.id===id);
    if(!row)throw Error('PROTECTED_DECISION_NOT_FOUND');
    if(row.actorHash!==hex(actor))throw Error('PROTECTED_DECISION_OWNER_FORBIDDEN');
    return row;
  }
  protectedDecisionRevocation(id){
    return this.readAll().find(x=>x.type==='protected-revocation'&&x.decisionId===id)||null;
  }
  revokeProtectedDecision(id,actor,reason){
    const decision=this.protectedDecisionForOwner(id,actor);
    if(!['OWNER_WITHDRAWN','REVIEW_DISPUTED','CUSTODY_DISPUTED'].includes(reason))
      throw Error('PROTECTED_REVOCATION_REASON_INVALID');
    const existing=this.protectedDecisionRevocation(id);
    if(existing)throw Error('PROTECTED_DECISION_ALREADY_REVOKED');
    const item=this.append({id:randomUUID(),type:'protected-revocation',
      at:new Date().toISOString(),decisionId:decision.id,
      serviceId:decision.serviceId,environment:decision.environment,
      actorHash:hex(actor),policySha256:decision.policySha256,reason,
      effect:'PERMANENTLY_BLOCK_FUTURE_PROTECTED_USE_CHECKS'});
    return {schema:'qualityrag.protected-decision-revocation/v1',
      decisionId:decision.id,status:'REVOKED',
      revokedAt:item.at,reason,receiptId:item.id,
      externallyAnchored:false};
  }
  recordProtectedUse({decision,actor,requestId,answerSha256,checkedAt}){
    if(!decision||decision.type!=='protected-decision'||
       decision.result?.verdict!=='ADMIT'||
       typeof actor!=='string'||!actor||decision.actorHash!==hex(actor)||
       !limited(requestId)||typeof answerSha256!=='string'||
       !/^[a-f0-9]{64}$/.test(answerSha256)||
       typeof checkedAt!=='string'||!Number.isFinite(Date.parse(checkedAt)))
      throw Error('PROTECTED_USE_INVALID');
    const rows=this.readAll();
    if(rows.some(x=>x.type==='protected-revocation'&&
       x.decisionId===decision.id))throw Error('PROTECTED_DECISION_REVOKED');
    const requestHash=hex(decision.serviceId+'@'+decision.environment+':'+requestId);
    if(rows.some(x=>x.type==='protected-use'&&
       x.serviceId===decision.serviceId&&x.environment===decision.environment&&
       x.requestHash===requestHash))
      throw Error('PROTECTED_USE_REPLAY');
    const lastMinute=rows.filter(x=>x.type==='protected-use'&&
      x.actorHash===decision.actorHash&&Date.parse(x.at)>=Date.now()-60000);
    if(lastMinute.length>=20)throw Error('PROTECTED_USE_RATE_LIMITED');
    const item=this.append({id:randomUUID(),type:'protected-use',
      at:new Date().toISOString(),serviceId:decision.serviceId,
      environment:decision.environment,actorHash:decision.actorHash,
      decisionId:decision.id,policySha256:decision.policySha256,
      requestHash,answerSha256,checkedAt,
      typeOfAuthorization:'HUMAN_SIGNED_EVIDENCE_USE_ONLY',
      answerSemanticsVerified:false,
      independentPublisherVerified:false,externallyAnchored:false});
    return {schema:'qualityrag.protected-decision-use/v1',
      permission:'PERMIT_SIGNED_ASSERTION_USE',decisionId:decision.id,
      requestId,answerSha256,at:item.at,checkedAt,
      policySha256:decision.policySha256,
      receiptId:item.id,chainHash:item.chainHash,
      globalEnforcement:false,answerSemanticsVerified:false,
      independentPublisherVerified:false,externallyAnchored:false,
      scope:'THIS_REGISTRY_CHECK_ONLY'};
  }
  exportProtectedDecision(id,actor){
    const row=this.protectedDecisionForOwner(id,actor);
    return {schema:'qualityrag.protected-drive-decision-replay/v1',
      id:row.id,serviceId:row.serviceId,environment:row.environment,
      at:row.at,asOf:row.asOf,policy:row.policy,
      policySha256:row.policySha256,evidence:row.evidence,result:row.result,
      signedCustody:row.signedCustody,signedMeaning:row.signedMeaning,
      claim:'CUSTOMER_SIGNED_AUTHORITIES_PLUS_LIVE_BYTES_AT_EVALUATION',
      sourceTruthProven:false,independentOriginsProven:false,
      externallyAnchored:false,chainHash:row.chainHash};
  }
  recordCandidateCheck(serviceId,environment,actor,policySha256,check){
    if(!limited(serviceId)||!limited(environment)||
       typeof actor!=='string'||!actor||
       typeof policySha256!=='string'||!/^[a-f0-9]{64}$/.test(policySha256)||
       !check||check.schema!=='qualityrag.drive-governed-candidate-check/v1'||
       !['REFUSE','INCONCLUSIVE'].includes(check.result)||
       check.evaluationAdmitted!==false||!check.counters||
       !['submitted','ownerExcluded','eligibleForReview','otherUnresolved'].every(k=>
         Number.isSafeInteger(check.counters[k])&&check.counters[k]>=0&&
         check.counters[k]<=25))
      throw Error('INVALID_DRIVE_CANDIDATE_TELEMETRY');
    const c=check.counters;
    if(c.submitted!==c.ownerExcluded+c.eligibleForReview+c.otherUnresolved)
      throw Error('INVALID_DRIVE_CANDIDATE_TELEMETRY');
    const actorHash=hex(actor);
    const cutoff=Date.now()-60_000;
    const recent=this.readAll().filter(x=>x.type==='drive-check'&&
      x.actorHash===actorHash&&Date.parse(x.at)>=cutoff);
    if(recent.length>=20)throw Error('DRIVE_CHALLENGE_RATE_LIMITED');
    const item=this.append({id:randomUUID(),type:'drive-check',
      at:new Date().toISOString(),serviceId,environment,
      actorHash,policySha256,
      verdict:check.result,submitted:c.submitted,ownerExcluded:c.ownerExcluded,
      eligibleForReview:c.eligibleForReview,otherUnresolved:c.otherUnresolved,
      admission:false,sourceAuthenticityVerified:false});
    return {id:item.id,at:item.at,chainHash:item.chainHash,
      externallyAnchored:false};
  }
  recordBlockedIngress(serviceId,environment,actor,policySha256){
    if(!limited(serviceId)||!limited(environment)||
       typeof actor!=='string'||!actor||
       typeof policySha256!=='string'||!/^[a-f0-9]{64}$/.test(policySha256))
      throw Error('INVALID_ENFORCEMENT_EVENT');
    const item=this.append({
      id:randomUUID(),type:'guard',
      at:new Date().toISOString(),serviceId,environment,
      actorHash:hex(actor),policySha256,
      reason:'PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED',
      candidateReviewOnly:true
    });
    return {id:item.id,at:item.at,reason:item.reason,chainHash:item.chainHash};
  }
  ingest(raw,policy,policySha256,actor) {
    exactKeys(raw,['serviceId','environment','requestId','traceId','evidence'],'EVALUATION');
    if(!limited(raw.serviceId)||!limited(raw.environment)||!limited(raw.requestId)||
       !limited(raw.traceId)||!policy||sha(policy)!==policySha256)
      throw Error('INVALID_EVALUATION');
    validateEvidence(raw.evidence,policy);
    const fingerprint=sha({serviceId:raw.serviceId,environment:raw.environment,
      requestId:raw.requestId,traceId:raw.traceId,evidence:raw.evidence,policySha256});
    const rows=this.readAll();
    const past=rows.find(x=>x.type==='evaluation'&&x.serviceId===raw.serviceId&&
      x.environment===raw.environment&&x.requestId===raw.requestId);
    if(past) {
      if(past.requestFingerprint!==fingerprint)throw Error('EVIDENCE_REQUEST_CONFLICT');
      return this.snapshot(past.id);
    }
    const at=new Date().toISOString();
    const result=evaluateEvidence(policy,raw.evidence,at);
    const entry=this.append({id:randomUUID(),type:'evaluation',at,
      serviceId:raw.serviceId,environment:raw.environment,
      requestId:raw.requestId,traceId:raw.traceId,
      actorHash:hex(actor),requestFingerprint:fingerprint,
      policy:structuredClone(policy),policySha256,
      evaluator:'qualityrag.registry-metadata-gate/v1',evidence:structuredClone(raw.evidence),result});
    return publicRecord({...entry,reviewHistory:[]});
  }
  snapshot(id){
    const rows=this.readAll();
    const found=rows.find(x=>x.type==='evaluation'&&x.id===id);
    if(!found)throw Error('EVIDENCE_NOT_FOUND');
    const reviews=rows.filter(x=>x.type==='review'&&x.evaluationId===id)
      .map(x=>({at:x.at,actorHash:x.actorHash,decision:x.decision,
        reasonCode:x.reasonCode,note:x.note||'',chainHash:x.chainHash}));
    return publicRecord({...found,reviewHistory:reviews});
  }
  list(serviceId,environment,limit=50) {
    if(!limited(serviceId)||!limited(environment)||!Number.isInteger(limit)||limit<1||limit>50)
      throw Error('INVALID_EVIDENCE_QUERY');
    const rows=this.readAll();
    const entries=rows.filter(x=>x.type==='evaluation'&&x.serviceId===serviceId&&x.environment===environment);
    const matching=new Set(entries.map(x=>x.id));
    const latestReviews=new Map();
    for(const review of rows)if(review.type==='review'&&matching.has(review.evaluationId))
      latestReviews.set(review.evaluationId,review);
    const dispositions=[...latestReviews.values()];
    const summary={
      admit:entries.filter(x=>x.result.verdict==='ADMIT').length,
      refuse:entries.filter(x=>x.result.verdict==='REFUSE').length,
      inconclusive:entries.filter(x=>x.result.verdict==='INCONCLUSIVE').length,
      accepted:dispositions.filter(x=>x.decision==='ACCEPTED').length,
      disputed:dispositions.filter(x=>x.decision==='DISPUTED').length,
      unreviewed:entries.length-dispositions.length,
      reviewedFalseBlocks:dispositions.filter(x=>x.reasonCode==='FALSE_BLOCK').length,
      blockedUnattestedIngress:rows.filter(x=>x.type==='guard'&&
        x.serviceId===serviceId&&x.environment===environment&&
        x.reason==='PROTECTED_DRIVE_UNATTESTED_EVIDENCE_BLOCKED').length,
      governedCandidateChecks:rows.filter(x=>x.type==='drive-check'&&
        x.serviceId===serviceId&&x.environment===environment).length,
      governedCandidateRefusals:rows.filter(x=>x.type==='drive-check'&&
        x.serviceId===serviceId&&x.environment===environment&&x.verdict==='REFUSE').length,
      protectedDecisions:rows.filter(x=>x.type==='protected-decision'&&
        x.serviceId===serviceId&&x.environment===environment).length,
      protectedAdmitted:rows.filter(x=>x.type==='protected-decision'&&
        x.serviceId===serviceId&&x.environment===environment&&
        x.result.verdict==='ADMIT').length,
      protectedInconclusive:rows.filter(x=>x.type==='protected-decision'&&
        x.serviceId===serviceId&&x.environment===environment&&
        x.result.verdict==='INCONCLUSIVE').length,
      protectedUses:rows.filter(x=>x.type==='protected-use'&&
        x.serviceId===serviceId&&x.environment===environment).length,
      protectedRevocations:rows.filter(x=>x.type==='protected-revocation'&&
        x.serviceId===serviceId&&x.environment===environment).length
    };
    const latestBlocked=rows.filter(x=>x.type==='guard'&&x.serviceId===serviceId&&
      x.environment===environment).at(-1);
    const latestCandidate=rows.filter(x=>x.type==='drive-check'&&x.serviceId===serviceId&&
      x.environment===environment).at(-1);
    return {observedCount:entries.length,coverage:'UNKNOWN',summary,
      guardTelemetry:{
        observedBlockedAttempts:summary.blockedUnattestedIngress,
        lastBlockedAt:latestBlocked?.at||null,
        protectedSince:this.protectedSince(serviceId,environment),
        governedCandidateChecks:summary.governedCandidateChecks,
        governedCandidateRefusals:summary.governedCandidateRefusals,
        protectedDecisions:summary.protectedDecisions,
        protectedAdmitted:summary.protectedAdmitted,
        protectedInconclusive:summary.protectedInconclusive,
        protectedUses:summary.protectedUses,
        protectedRevocations:summary.protectedRevocations,
        lastCandidateCheckAt:latestCandidate?.at||null,
        externallyAnchored:false,coverage:'REGISTRY_EVENT_ENDPOINTS_ONLY'
      },
      evaluations:entries.slice(-limit).reverse().map(x=>this.snapshot(x.id))};
  }
  exportReplay(id){
    const rows=this.readAll();
    const entry=rows.find(x=>x.type==='evaluation'&&x.id===id);
    if(!entry)throw Error('EVIDENCE_NOT_FOUND');
    if(sha(entry.policy)!==entry.policySha256)throw Error('EVIDENCE_LEDGER_INTEGRITY_FAILURE');
    const payload={
      schema:'qualityrag.evidence-replay/v1',
      evaluationId:entry.id,
      serviceId:entry.serviceId,
      environment:entry.environment,
      requestId:entry.requestId,
      traceId:entry.traceId,
      asOf:entry.at,
      evaluator:entry.evaluator,
      policy:entry.policy,
      policySha256:entry.policySha256,
      evidence:entry.evidence,
      expectedResult:entry.result,
      sourceOriginStatus:'CALLER_DECLARED_NOT_AUTHENTICATED',
      ledgerRecordHash:entry.chainHash
    };
    return {payload,integrity:{
      sha256:sha(payload),
      externallyAnchored:false,
      digitallySigned:false,
      authenticityVerified:false
    }};
  }
  replay(id){
    const rows=this.readAll(),row=rows.find(x=>x.type==='evaluation'&&x.id===id);
    if(!row)throw Error('EVIDENCE_NOT_FOUND');
    if(sha(row.policy)!==row.policySha256)throw Error('EVIDENCE_LEDGER_INTEGRITY_FAILURE');
    const repeated=evaluateEvidence(row.policy,row.evidence,row.at);
    const match=sha(repeated)===sha(row.result);
    return {id,verdict:repeated.verdict,result:repeated,original:row.result,
      reproduced:match,policySha256:row.policySha256,asOf:row.at,
      evaluator:row.evaluator,scope:'same-server deterministic metadata replay',
      sourceAuthenticityVerified:false};
  }
  review(id,input,actor){
    exactKeys(input,['decision','reasonCode','note'],'REVIEW');
    if(!['ACCEPTED','DISPUTED'].includes(input.decision)||
       !['REPRODUCED','FALSE_BLOCK','PROVENANCE_UNVERIFIED','POLICY_DISAGREEMENT','OTHER'].includes(input.reasonCode)||
       (input.note!==undefined && (typeof input.note!=='string'||input.note.length>280||
        /[\r\n@<>]/.test(input.note))))throw Error('INVALID_REVIEW');
    const all=this.readAll(),base=all.find(x=>x.type==='evaluation'&&x.id===id);
    if(!base)throw Error('EVIDENCE_NOT_FOUND');
    if(base.actorHash===hex(actor))throw Error('SELF_REVIEW_FORBIDDEN');
    const replay=this.replay(id);
    if(!replay.reproduced)throw Error('REPLAY_MISMATCH');
    const at=new Date().toISOString();
    const row=this.append({id:randomUUID(),type:'review',evaluationId:id,at,
      actorHash:hex(actor),decision:input.decision,reasonCode:input.reasonCode,
      note:input.note||'',replayReproduced:true});
    return {evaluationId:id,decision:input.decision,reasonCode:input.reasonCode,
      reviewedAt:at,chainHash:row.chainHash,replayReproduced:true};
  }
}
