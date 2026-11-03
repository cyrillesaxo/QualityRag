import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {verifySignedPolicy} from './signed.js';

export const hashPolicy = (policy) => createHash('sha256').update(JSON.stringify(policy)).digest('hex');
export function validatePolicy(p) {
  if (!p || typeof p !== 'object' || !p.id || !p.version || !Array.isArray(p.requirements) || !p.requirements.length) throw new Error('INVALID_POLICY');
  const ids = new Set();
  for (const r of p.requirements) {
    if (!r?.id || ids.has(r.id) || (r.min_independent_sources !== undefined && (!Number.isInteger(r.min_independent_sources) || r.min_independent_sources < 1)) || (r.max_age_seconds !== undefined && (!Number.isInteger(r.max_age_seconds) || r.max_age_seconds < 0))) throw new Error('INVALID_POLICY');
    ids.add(r.id);
  }
  return {id:p.id,version:p.version,requirements:p.requirements.map(r=>({...r}))};
}
const empty = () => ({services:{},policies:{},bindings:{},signedPromotions:{},signedBindings:{},audit:[],governanceAudit:[],governanceHead:'0'.repeat(64)});
export class RegistryStore {
  constructor(file) {
    this.file=file;
    this.data=fs.existsSync(file)? JSON.parse(fs.readFileSync(file,'utf8')) : empty();
    this.data.signedPromotions??={};this.data.signedBindings??={};
    this.data.governanceAudit??=[];this.data.governanceHead??='0'.repeat(64);
    this.verifyGovernanceAudit();
  }
  save() {
    fs.mkdirSync(path.dirname(this.file),{recursive:true});
    const tmp=this.file+'.'+process.pid+'.tmp';
    fs.writeFileSync(tmp,JSON.stringify(this.data,null,2),{mode:0o600});
    fs.renameSync(tmp,this.file);
  }
  verifyGovernanceAudit(){
    let prev='0'.repeat(64);
    for(const event of this.data.governanceAudit){
      if(event.previousHash!==prev||typeof event.hash!=='string')
        throw new Error('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
      const {hash,...fields}=event;
      const calculated=createHash('sha256').update(JSON.stringify(fields)).digest('hex');
      if(hash!==calculated)throw new Error('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
      prev=hash;
    }
    if(prev!==this.data.governanceHead)throw new Error('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
  }
  record(actor,action,detail) {
    const time=new Date().toISOString();
    this.data.audit.push({actor,action,detail,time});
    if(action.startsWith('SIGNED_')){
      this.verifyGovernanceAudit();
      const event={previousHash:this.data.governanceHead,actor,action,detail,time};
      const hash=createHash('sha256').update(JSON.stringify(event)).digest('hex');
      this.data.governanceAudit.push({...event,hash});
      this.data.governanceHead=hash;
    }
  }
  register(service,actor) {
    if (!service?.id || !/^[a-zA-Z0-9._-]+$/.test(service.id) || !service?.displayName) throw new Error('INVALID_SERVICE');
    const next={id:service.id,displayName:service.displayName,createdAt:this.data.services[service.id]?.createdAt??new Date().toISOString()};
    this.data.services[service.id]=next;this.record(actor,'SERVICE_REGISTERED',service.id);this.save();return next;
  }
  draft(raw,actor) {
    const policy=validatePolicy(raw);
    const key=policy.id+'@'+policy.version;
    if (this.data.policies[key]) throw new Error('VERSION_EXISTS');
    const entry={policy,status:'DRAFT',sha256:hashPolicy(policy),createdBy:actor};
    this.data.policies[key]=entry;this.record(actor,'POLICY_DRAFTED',key);this.save();return entry;
  }
  approve(id,version,actor,{enforceSeparation=false}={}) {
    const key=id+'@'+version, entry=this.data.policies[key];
    if (!entry) throw new Error('NOT_FOUND');
    if(entry.status!=='DRAFT') throw new Error('NOT_DRAFT');
    if(enforceSeparation && entry.createdBy===actor)throw new Error('SELF_APPROVAL_FORBIDDEN');
    entry.status='APPROVED';entry.approvedBy=actor;entry.approvedAt=new Date().toISOString();
    this.record(actor,'POLICY_APPROVED',key);this.save();return entry;
  }
  bind(serviceId,environment,policyId,version,actor){
    if (!this.data.services[serviceId]) throw new Error('UNKNOWN_SERVICE');
    if (!/^[a-zA-Z0-9._-]+$/.test(environment||'')) throw new Error('INVALID_ENVIRONMENT');
    const entry=this.data.policies[policyId+'@'+version];
    if (!entry || entry.status!=='APPROVED') throw new Error('UNAPPROVED_POLICY');
    const key=serviceId+'@'+environment;
    const binding={serviceId,environment,policyId,version,sha256:entry.sha256};
    this.data.bindings[key]=binding;this.record(actor,'BINDING_UPDATED',key);this.save();return binding;
  }
  stageSigned(bundle,actor,trustedKeys) {
    const record=verifySignedPolicy(bundle,trustedKeys);
    if(!this.data.services[record.serviceId])throw new Error('UNKNOWN_SERVICE');
    const scope=record.serviceId+'@'+record.environment;
    const floor=this.data.signedBindings[scope]?.sequence??0;
    if(record.sequence<=floor)throw new Error('SIGNED_SEQUENCE_ROLLBACK');
    const key=scope+'#'+record.sequence;
    if(this.data.signedPromotions[key])throw new Error('SIGNED_SEQUENCE_EXISTS');
    const entry={...record,status:'STAGED',bundle,stagedBy:actor,stagedAt:new Date().toISOString()};
    this.data.signedPromotions[key]=entry;
    this.record(actor,'SIGNED_POLICY_STAGED',key);
    this.save();
    return {serviceId:record.serviceId,environment:record.environment,sequence:record.sequence,
      status:entry.status,keyId:record.keyId,irSha256:record.irSha256};
  }
  approveSigned(serviceId,environment,sequence,actor,trustedKeys,{enforceSeparation=false}={}) {
    const key=serviceId+'@'+environment+'#'+sequence;
    const entry=this.data.signedPromotions[key];
    if(!entry)throw new Error('NOT_FOUND');
    if(entry.status!=='STAGED')throw new Error('SIGNED_NOT_STAGED');
    if(enforceSeparation && entry.stagedBy===actor)throw new Error('SELF_APPROVAL_FORBIDDEN');
    verifySignedPolicy(entry.bundle,trustedKeys);
    entry.status='APPROVED';entry.approvedBy=actor;entry.approvedAt=new Date().toISOString();
    this.record(actor,'SIGNED_POLICY_APPROVED',key);this.save();
    return {serviceId,environment,sequence,status:entry.status};
  }
  publishSigned(serviceId,environment,sequence,actor,trustedKeys,{enforceSeparation=false}={}) {
    const key=serviceId+'@'+environment+'#'+sequence;
    const entry=this.data.signedPromotions[key];
    if(!entry)throw new Error('NOT_FOUND');
    if(entry.status!=='APPROVED')throw new Error('SIGNED_NOT_APPROVED');
    if(enforceSeparation && (entry.stagedBy===actor||entry.approvedBy===actor))
      throw new Error('SAME_ACTOR_PROMOTION_FORBIDDEN');
    const verified=verifySignedPolicy(entry.bundle,trustedKeys);
    if(verified.serviceId!==serviceId||verified.environment!==environment||verified.sequence!==sequence)
      throw new Error('SIGNED_BINDING_MISMATCH');
    const scope=serviceId+'@'+environment;
    const floor=this.data.signedBindings[scope]?.sequence??0;
    if(sequence<=floor)throw new Error('SIGNED_SEQUENCE_ROLLBACK');
    // Preserve exact signature and immutable bundle; no server-side signing keys.
    this.data.signedBindings[scope]={serviceId,environment,sequence,promotionKey:key,
      irSha256:entry.irSha256,signature:entry.bundle.signature};
    entry.status='PUBLISHED';entry.publishedBy=actor;entry.publishedAt=new Date().toISOString();
    this.record(actor,'SIGNED_POLICY_PUBLISHED',key);this.save();
    return {serviceId,environment,sequence,status:entry.status,irSha256:entry.irSha256};
  }
  resolveSigned(serviceId,environment,trustedKeys) {
    if(!this.data.services[serviceId])throw new Error('UNKNOWN_SERVICE');
    const binding=this.data.signedBindings[serviceId+'@'+environment];
    if(!binding)throw new Error('UNBOUND_SERVICE');
    const entry=this.data.signedPromotions[binding.promotionKey];
    if(!entry||entry.status!=='PUBLISHED'||entry.bundle.signature!==binding.signature)
      throw new Error('SIGNED_POLICY_INTEGRITY_FAILURE');
    const verified=verifySignedPolicy(entry.bundle,trustedKeys);
    if(verified.serviceId!==serviceId||verified.environment!==environment||
       verified.sequence!==binding.sequence||verified.irSha256!==binding.irSha256)
      throw new Error('SIGNED_POLICY_INTEGRITY_FAILURE');
    return {serviceId,environment,sequence:binding.sequence,status:'PUBLISHED',
      signedPolicy:entry.bundle};
  }
  resolve(serviceId,environment) {
    if (!this.data.services[serviceId]) throw new Error('UNKNOWN_SERVICE');
    const binding=this.data.bindings[serviceId+'@'+environment];
    if (!binding) throw new Error('UNBOUND_SERVICE');
    const entry=this.data.policies[binding.policyId+'@'+binding.version];
    if (!entry || entry.status!=='APPROVED' || entry.sha256!==binding.sha256 || hashPolicy(entry.policy)!==entry.sha256) throw new Error('POLICY_INTEGRITY_FAILURE');
    return {serviceId,environment,policy:entry.policy,sha256:entry.sha256,status:'APPROVED'};
  }
}
