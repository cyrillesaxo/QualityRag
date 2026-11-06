import {Pool} from 'pg';
import {createHash} from 'node:crypto';
import {verifySignedPolicy} from './signed.js';
import {verifySignedContract,validateContract,contractSha256} from './contracts.js';
import {checkMigrations} from './migrate.js';

const valid=/^[A-Za-z0-9._-]+$/;
const err=(code)=>{throw new Error(code)};
const hash=(x)=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const ZERO='0'.repeat(64);

export class PgSignedRegistryStore {
 constructor(pool){if(!pool||typeof pool.connect!=='function')err('PG_POOL_REQUIRED');this.pool=pool}
 async close(){await this.pool.end()}
 async transaction(service,environment,fn,create=false){
  if(!valid.test(service||'')||!valid.test(environment||''))err('INVALID_SIGNED_SCOPE');
  const c=await this.pool.connect();
  try{
   await c.query('BEGIN');
   if(create){
    const exists=await c.query('SELECT 1 FROM qr_services WHERE service_id=$1',[service]);
    if(!exists.rowCount)err('UNKNOWN_SERVICE');
    await c.query('INSERT INTO qr_scopes(service_id,environment) VALUES($1,$2) ON CONFLICT DO NOTHING',[service,environment]);
    await c.query('INSERT INTO qr_governance_heads(service_id,environment) VALUES($1,$2) ON CONFLICT DO NOTHING',[service,environment]);
   }
   const locked=await c.query('SELECT * FROM qr_scopes WHERE service_id=$1 AND environment=$2 FOR UPDATE',[service,environment]);
   if(!locked.rowCount)err('UNBOUND_SERVICE');
   const out=await fn(c,locked.rows[0]);
   await c.query('COMMIT');
   return out;
  }catch(e){await c.query('ROLLBACK');throw e}
  finally{c.release()}
 }
 async audit(c,service,environment,sequence,actor,action){
  const r=await c.query('SELECT last_hash FROM qr_governance_heads WHERE service_id=$1 AND environment=$2 FOR UPDATE',[service,environment]);
  if(!r.rowCount)err('AUDIT_HEAD_MISSING');
  const previous=r.rows[0].last_hash;
  const h=hash({service,environment,sequence,actor,action,previous});
  await c.query('INSERT INTO qr_governance_events(service_id,environment,sequence,actor,action,previous_hash,event_hash) VALUES($1,$2,$3,$4,$5,$6,$7)',
    [service,environment,sequence,actor,action,previous,h]);
  await c.query('UPDATE qr_governance_heads SET last_hash=$3 WHERE service_id=$1 AND environment=$2',[service,environment,h]);
 }
 async register(s){
  if(!valid.test(s?.id||'')||typeof s?.displayName!=='string'||!s.displayName.trim())err('INVALID_SERVICE');
  const r=await this.pool.query('INSERT INTO qr_services(service_id,display_name) VALUES($1,$2) ON CONFLICT(service_id) DO UPDATE SET display_name=EXCLUDED.display_name RETURNING service_id AS id,display_name AS "displayName"',
    [s.id,s.displayName]);
  return r.rows[0];
 }
 async stageSigned(bundle,actor,keys){
  const m=verifySignedPolicy(bundle,keys),s=m.serviceId,e=m.environment,n=m.sequence;
  return this.transaction(s,e,async(c,scope)=>{
   if(n<=Number(scope.published_sequence))err('SIGNED_SEQUENCE_ROLLBACK');
   const existing=await c.query('SELECT 1 FROM qr_signed_promotions WHERE service_id=$1 AND environment=$2 AND sequence=$3',[s,e,n]);
   if(existing.rowCount)err('SIGNED_SEQUENCE_EXISTS');
   await c.query('INSERT INTO qr_signed_promotions(service_id,environment,sequence,status,bundle,signature,ir_sha256,key_id,staged_by) VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9)',
    [s,e,n,'STAGED',JSON.stringify(bundle),bundle.signature,m.irSha256,m.keyId,actor]);
   await this.audit(c,s,e,n,actor,'STAGED');
   return {serviceId:s,environment:e,sequence:n,status:'STAGED',keyId:m.keyId,irSha256:m.irSha256};
  },true);
 }
 async approveSigned(s,e,n,actor,keys,{enforceSeparation=false}={}){
  return this.transaction(s,e,async(c)=>{
   const r=await c.query('SELECT * FROM qr_signed_promotions WHERE service_id=$1 AND environment=$2 AND sequence=$3 FOR UPDATE',[s,e,n]);
   if(!r.rowCount)err('NOT_FOUND');
   const row=r.rows[0];
   if(row.status!=='STAGED')err('SIGNED_NOT_STAGED');
   if(enforceSeparation&&actor===row.staged_by)err('SELF_APPROVAL_FORBIDDEN');
   const m=verifySignedPolicy(row.bundle,keys);
   if(m.serviceId!==s||m.environment!==e||m.sequence!==n||m.irSha256!==row.ir_sha256||row.signature!==row.bundle.signature)err('SIGNED_BINDING_MISMATCH');
   await c.query('UPDATE qr_signed_promotions SET status=$4,approved_by=$5,approved_at=now() WHERE service_id=$1 AND environment=$2 AND sequence=$3',[s,e,n,'APPROVED',actor]);
   await this.audit(c,s,e,n,actor,'APPROVED');
   return {serviceId:s,environment:e,sequence:n,status:'APPROVED'};
  });
 }
 async publishSigned(s,e,n,actor,keys,{enforceSeparation=false}={}){
  return this.transaction(s,e,async(c,scope)=>{
   const r=await c.query('SELECT * FROM qr_signed_promotions WHERE service_id=$1 AND environment=$2 AND sequence=$3 FOR UPDATE',[s,e,n]);
   if(!r.rowCount)err('NOT_FOUND');
   const row=r.rows[0];
   if(row.status!=='APPROVED')err('SIGNED_NOT_APPROVED');
   if(enforceSeparation&&(actor===row.staged_by||actor===row.approved_by))err('SAME_ACTOR_PROMOTION_FORBIDDEN');
   const m=verifySignedPolicy(row.bundle,keys);
   if(m.serviceId!==s||m.environment!==e||m.sequence!==n||m.irSha256!==row.ir_sha256||m.keyId!==row.key_id||row.signature!==row.bundle.signature)err('SIGNED_BINDING_MISMATCH');
   if(n<=Number(scope.published_sequence))err('SIGNED_SEQUENCE_ROLLBACK');
   await c.query('UPDATE qr_signed_promotions SET status=$4,published_by=$5,published_at=now() WHERE service_id=$1 AND environment=$2 AND sequence=$3',[s,e,n,'PUBLISHED',actor]);
   await c.query('UPDATE qr_scopes SET published_sequence=$3,published_signature=$4,published_ir_sha256=$5 WHERE service_id=$1 AND environment=$2',[s,e,n,row.signature,row.ir_sha256]);
   await this.audit(c,s,e,n,actor,'PUBLISHED');
   return {serviceId:s,environment:e,sequence:n,status:'PUBLISHED',irSha256:m.irSha256};
  });
 }
 async resolveSigned(s,e,keys){
  return this.transaction(s,e,async(c,scope)=>{
   const n=Number(scope.published_sequence);
   if(!n)err('UNBOUND_SERVICE');
   const r=await c.query('SELECT * FROM qr_signed_promotions WHERE service_id=$1 AND environment=$2 AND sequence=$3',[s,e,n]);
   if(!r.rowCount||r.rows[0].status!=='PUBLISHED')err('SIGNED_POLICY_INTEGRITY_FAILURE');
   const row=r.rows[0];
   if(scope.published_signature!==row.signature||scope.published_ir_sha256!==row.ir_sha256)err('SIGNED_POLICY_INTEGRITY_FAILURE');
   const m=verifySignedPolicy(row.bundle,keys);
   if(m.serviceId!==s||m.environment!==e||m.sequence!==n||m.irSha256!==row.ir_sha256||row.signature!==row.bundle.signature)err('SIGNED_POLICY_INTEGRITY_FAILURE');
   return {serviceId:s,environment:e,sequence:n,status:'PUBLISHED',signedPolicy:row.bundle};
  });
 }
 async state(){
  const [ss,ps,bs,cp,cb]=await Promise.all([
   this.pool.query('SELECT service_id AS id,display_name AS "displayName" FROM qr_services ORDER BY service_id'),
   this.pool.query('SELECT service_id AS "serviceId",environment,sequence,status,ir_sha256 AS "irSha256",key_id AS "keyId",staged_by AS "stagedBy",approved_by AS "approvedBy",published_by AS "publishedBy" FROM qr_signed_promotions ORDER BY service_id,environment,sequence'),
   this.pool.query('SELECT service_id AS "serviceId",environment,published_sequence AS sequence,published_ir_sha256 AS "irSha256" FROM qr_scopes WHERE published_sequence>0 ORDER BY service_id,environment'),
   this.pool.query('SELECT p.contract_id AS "contractId",h.kind,h.tenant,p.sequence,p.status,p.sha256,p.key_id AS "keyId",p.staged_by AS "stagedBy",p.approved_by AS "approvedBy",p.published_by AS "publishedBy" FROM qr_contract_promotions p JOIN qr_contract_heads h USING(contract_id) ORDER BY p.contract_id,p.sequence'),
   this.pool.query('SELECT contract_id AS "contractId",kind,tenant,published_sequence AS sequence,published_sha256 AS sha256 FROM qr_contract_heads WHERE published_sequence>0 ORDER BY contract_id')
  ]);
  return {services:ss.rows,policies:[],bindings:[],signedPromotions:ps.rows.map(x=>({...x,sequence:Number(x.sequence)})),signedBindings:bs.rows.map(x=>({...x,sequence:Number(x.sequence)})),
   contractPromotions:cp.rows.map(x=>({...x,sequence:Number(x.sequence)})),contractBindings:cb.rows.map(x=>({...x,sequence:Number(x.sequence)}))};
 }
 async verifyGovernanceIntegrity(queryable=this.pool){
  // Read-only validation, detecting missing events, altered links, mismatched
  // heads and status/audit inconsistencies without mutating operator state.
  const scopes=await queryable.query('SELECT service_id,environment,published_sequence FROM qr_scopes ORDER BY service_id,environment');
  for(const scope of scopes.rows){
   const s=scope.service_id,e=scope.environment;
   const [head,events,promotions]=await Promise.all([
    queryable.query('SELECT last_hash FROM qr_governance_heads WHERE service_id=$1 AND environment=$2',[s,e]),
    queryable.query('SELECT sequence,actor,action,previous_hash,event_hash FROM qr_governance_events WHERE service_id=$1 AND environment=$2 ORDER BY event_id',[s,e]),
    queryable.query('SELECT sequence,status,staged_by,approved_by,published_by FROM qr_signed_promotions WHERE service_id=$1 AND environment=$2',[s,e])
   ]);
   if(head.rowCount!==1)err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
   let previous=ZERO,actions=new Map();
   for(const event of events.rows){
    if(event.previous_hash!==previous)err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
    const expected=hash({service:s,environment:e,sequence:Number(event.sequence),
      actor:event.actor,action:event.action,previous});
    if(event.event_hash!==expected)err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
    previous=expected;
    const n=Number(event.sequence), steps=actions.get(n)||[];
    steps.push({action:event.action,actor:event.actor});
    actions.set(n,steps);
   }
   if(head.rows[0].last_hash!==previous)err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
   for(const p of promotions.rows){
    const n=Number(p.sequence),steps=actions.get(n)||[];
    const expected=p.status==='STAGED'?['STAGED']:
     p.status==='APPROVED'?['STAGED','APPROVED']:['STAGED','APPROVED','PUBLISHED'];
    if(JSON.stringify(steps.map(x=>x.action))!==JSON.stringify(expected)||
      steps[0]?.actor!==p.staged_by||
      (expected.length>1 && steps[1]?.actor!==p.approved_by)||
      (expected.length>2 && steps[2]?.actor!==p.published_by))
      err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
    actions.delete(n);
   }
   if(actions.size)err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
  }
  return {scopes:scopes.rowCount};
 }
 async readiness(){
  const c=await this.pool.connect();
  try{
   // One consistent snapshot across scopes, heads and events under concurrent publishing.
   await c.query('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
   await c.query('SELECT 1');
   const migration=await checkMigrations(c);
   const audit=await this.verifyGovernanceIntegrity(c);
   const contracts=await this.verifyContractIntegrity(c);
   await c.query('COMMIT');
   return {ready:true,backend:'postgres',migration:migration.version,checkedScopes:audit.scopes,checkedContracts:contracts.contracts};
  }catch(error){
   await c.query('ROLLBACK').catch(()=>{});
   throw error;
  }finally{c.release()}
 }

 // ---------- Data contracts (ADR-0002) ----------
 validateContractDraft(raw){
  const c=validateContract(raw);
  return {valid:true,contractId:c.id,kind:c.kind,tenant:c.tenant,sha256:contractSha256(c)};
 }
 async contractTransaction(id,fn,create=null){
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id||''))err('INVALID_CONTRACT_ID');
  const c=await this.pool.connect();
  try{
   await c.query('BEGIN');
   if(create)await c.query('INSERT INTO qr_contract_heads(contract_id,tenant,kind) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',[id,create.tenant,create.kind]);
   const head=await c.query('SELECT * FROM qr_contract_heads WHERE contract_id=$1 FOR UPDATE',[id]);
   if(!head.rowCount)err('UNBOUND_CONTRACT');
   const out=await fn(c,head.rows[0]);
   await c.query('COMMIT');
   return out;
  }catch(e){await c.query('ROLLBACK');throw e}
  finally{c.release()}
 }
 async contractAudit(c,head,sequence,actor,action){
  const previous=head.last_hash;
  const h=hash({contract:head.contract_id,sequence,actor,action,previous});
  await c.query('INSERT INTO qr_contract_events(contract_id,sequence,actor,action,previous_hash,event_hash) VALUES($1,$2,$3,$4,$5,$6)',
   [head.contract_id,sequence,actor,action,previous,h]);
  await c.query('UPDATE qr_contract_heads SET last_hash=$2 WHERE contract_id=$1',[head.contract_id,h]);
  head.last_hash=h;
 }
 async stageContract(envelope,actor,keys){
  const m=verifySignedContract(envelope,keys);
  return this.contractTransaction(m.contractId,async(c,head)=>{
   if(head.tenant!==m.tenant||head.kind!==m.kind)err('CONTRACT_IDENTITY_CHANGE_FORBIDDEN');
   if(m.sequence<=Number(head.published_sequence))err('SIGNED_SEQUENCE_ROLLBACK');
   const exists=await c.query('SELECT 1 FROM qr_contract_promotions WHERE contract_id=$1 AND sequence=$2',[m.contractId,m.sequence]);
   if(exists.rowCount)err('SIGNED_SEQUENCE_EXISTS');
   await c.query('INSERT INTO qr_contract_promotions(contract_id,sequence,status,envelope,signature,sha256,key_id,staged_by) VALUES($1,$2,$3,$4::jsonb,$5,$6,$7,$8)',
    [m.contractId,m.sequence,'STAGED',JSON.stringify(envelope),envelope.signature,m.sha256,m.keyId,actor]);
   await this.contractAudit(c,head,m.sequence,actor,'STAGED');
   return {contractId:m.contractId,kind:m.kind,tenant:m.tenant,sequence:m.sequence,status:'STAGED',keyId:m.keyId,sha256:m.sha256};
  },{tenant:m.tenant,kind:m.kind});
 }
 async approveContract(id,n,actor,keys,{enforceSeparation=false}={}){
  return this.contractTransaction(id,async(c,head)=>{
   const r=await c.query('SELECT * FROM qr_contract_promotions WHERE contract_id=$1 AND sequence=$2 FOR UPDATE',[id,n]);
   if(!r.rowCount)err('NOT_FOUND');
   const row=r.rows[0];
   if(row.status!=='STAGED')err('SIGNED_NOT_STAGED');
   if(enforceSeparation&&actor===row.staged_by)err('SELF_APPROVAL_FORBIDDEN');
   const m=verifySignedContract(row.envelope,keys);
   if(m.sha256!==row.sha256||m.sequence!==n||row.signature!==row.envelope.signature)err('SIGNED_BINDING_MISMATCH');
   await c.query('UPDATE qr_contract_promotions SET status=$3,approved_by=$4,approved_at=now() WHERE contract_id=$1 AND sequence=$2',[id,n,'APPROVED',actor]);
   await this.contractAudit(c,head,n,actor,'APPROVED');
   return {contractId:id,sequence:n,status:'APPROVED'};
  });
 }
 async publishContract(id,n,actor,keys,{enforceSeparation=false}={}){
  return this.contractTransaction(id,async(c,head)=>{
   const r=await c.query('SELECT * FROM qr_contract_promotions WHERE contract_id=$1 AND sequence=$2 FOR UPDATE',[id,n]);
   if(!r.rowCount)err('NOT_FOUND');
   const row=r.rows[0];
   if(row.status!=='APPROVED')err('SIGNED_NOT_APPROVED');
   if(enforceSeparation&&(actor===row.staged_by||actor===row.approved_by))err('SAME_ACTOR_PROMOTION_FORBIDDEN');
   const m=verifySignedContract(row.envelope,keys);
   if(m.sha256!==row.sha256||m.sequence!==n||m.contractId!==id||row.signature!==row.envelope.signature)err('SIGNED_BINDING_MISMATCH');
   if(n<=Number(head.published_sequence))err('SIGNED_SEQUENCE_ROLLBACK');
   await c.query('UPDATE qr_contract_promotions SET status=$3,published_by=$4,published_at=now() WHERE contract_id=$1 AND sequence=$2',[id,n,'PUBLISHED',actor]);
   await c.query('UPDATE qr_contract_heads SET published_sequence=$2,published_signature=$3,published_sha256=$4 WHERE contract_id=$1',[id,n,row.signature,row.sha256]);
   await this.contractAudit(c,head,n,actor,'PUBLISHED');
   return {contractId:id,sequence:n,status:'PUBLISHED',sha256:m.sha256};
  });
 }
 async resolveContract(id,keys,queryable=this.pool){
  const h=await queryable.query('SELECT * FROM qr_contract_heads WHERE contract_id=$1',[id]);
  if(!h.rowCount||!Number(h.rows[0].published_sequence))err('UNBOUND_CONTRACT');
  const head=h.rows[0],n=Number(head.published_sequence);
  const r=await queryable.query('SELECT * FROM qr_contract_promotions WHERE contract_id=$1 AND sequence=$2',[id,n]);
  if(!r.rowCount||r.rows[0].status!=='PUBLISHED'||r.rows[0].signature!==head.published_signature)err('CONTRACT_INTEGRITY_FAILURE');
  const m=verifySignedContract(r.rows[0].envelope,keys);
  if(m.sha256!==head.published_sha256||m.sequence!==n)err('CONTRACT_INTEGRITY_FAILURE');
  return {contractId:id,kind:m.kind,tenant:m.tenant,sequence:n,status:'PUBLISHED',sha256:m.sha256,signedContract:r.rows[0].envelope};
 }
 async publishedContracts(tenant,keys){
  if(typeof tenant!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(tenant))err('INVALID_TENANT');
  const ids=await this.pool.query('SELECT contract_id FROM qr_contract_heads WHERE tenant=$1 AND published_sequence>0 ORDER BY contract_id',[tenant]);
  const out=[];
  for(const row of ids.rows)out.push((await this.resolveContract(row.contract_id,keys)).signedContract);
  return {tenant,contracts:out};
 }
 async verifyContractIntegrity(queryable=this.pool){
  const heads=await queryable.query('SELECT contract_id,last_hash FROM qr_contract_heads ORDER BY contract_id');
  for(const head of heads.rows){
   const events=await queryable.query('SELECT sequence,actor,action,previous_hash,event_hash FROM qr_contract_events WHERE contract_id=$1 ORDER BY event_id',[head.contract_id]);
   let previous=ZERO;
   for(const e of events.rows){
    const expected=hash({contract:head.contract_id,sequence:Number(e.sequence),actor:e.actor,action:e.action,previous});
    if(e.previous_hash!==previous||e.event_hash!==expected)err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
    previous=expected;
   }
   if(head.last_hash!==previous)err('GOVERNANCE_AUDIT_INTEGRITY_FAILURE');
  }
  return {contracts:heads.rowCount};
 }
 async draft(){err('UNSUPPORTED_IN_POSTGRES_MODE')}
 async approve(){err('UNSUPPORTED_IN_POSTGRES_MODE')}
 async bind(){err('UNSUPPORTED_IN_POSTGRES_MODE')}
 async resolve(){err('UNSUPPORTED_IN_POSTGRES_MODE')}
}
export function createPgSignedRegistryStore(connectionString){
 if(!connectionString||typeof connectionString!=='string')err('DATABASE_URL_REQUIRED');
 return new PgSignedRegistryStore(new Pool({connectionString,max:12,connectionTimeoutMillis:3000,idleTimeoutMillis:10000,statement_timeout:5000}));
}
