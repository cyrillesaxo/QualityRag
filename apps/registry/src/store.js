import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

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
const empty = () => ({services:{},policies:{},bindings:{},audit:[]});
export class RegistryStore {
  constructor(file) {
    this.file=file;
    this.data=fs.existsSync(file)? JSON.parse(fs.readFileSync(file,'utf8')) : empty();
  }
  save() {
    fs.mkdirSync(path.dirname(this.file),{recursive:true});
    const tmp=this.file+'.'+process.pid+'.tmp';
    fs.writeFileSync(tmp,JSON.stringify(this.data,null,2),{mode:0o600});
    fs.renameSync(tmp,this.file);
  }
  record(actor,action,detail) {this.data.audit.push({actor,action,detail,time:new Date().toISOString()});}
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
  approve(id,version,actor) {
    const key=id+'@'+version, entry=this.data.policies[key];
    if (!entry) throw new Error('NOT_FOUND');
    if(entry.status!=='DRAFT') throw new Error('NOT_DRAFT');
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
  resolve(serviceId,environment) {
    if (!this.data.services[serviceId]) throw new Error('UNKNOWN_SERVICE');
    const binding=this.data.bindings[serviceId+'@'+environment];
    if (!binding) throw new Error('UNBOUND_SERVICE');
    const entry=this.data.policies[binding.policyId+'@'+binding.version];
    if (!entry || entry.status!=='APPROVED' || entry.sha256!==binding.sha256 || hashPolicy(entry.policy)!==entry.sha256) throw new Error('POLICY_INTEGRITY_FAILURE');
    return {serviceId,environment,policy:entry.policy,sha256:entry.sha256,status:'APPROVED'};
  }
}
