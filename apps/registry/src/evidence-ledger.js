import fs from 'node:fs';
import path from 'node:path';
import {createHash, randomUUID} from 'node:crypto';

// Opt-in, single-process, local-first evidence telemetry. Not an attested audit log.
const ZERO = '0'.repeat(64);
const hex = value => createHash('sha256').update(value).digest('hex');
const sha = value => hex(JSON.stringify(value));
const idPattern = /^[a-zA-Z][a-zA-Z0-9_.-]{0,79}$/;
const opaque = /^(ev|org|src)_[a-f0-9]{24,64}$/;
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
  if(!Array.isArray(evidence) || !evidence.length || evidence.length>100)
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
    const entries=this.readAll().filter(x=>x.type==='evaluation'&&x.serviceId===serviceId&&x.environment===environment);
    return {observedCount:entries.length,coverage:'UNKNOWN',
      evaluations:entries.slice(-limit).reverse().map(x=>this.snapshot(x.id))};
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
