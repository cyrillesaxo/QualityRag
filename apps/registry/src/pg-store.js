import {Pool} from 'pg';
import {createHash} from 'node:crypto';
import {verifySignedPolicy} from './signed.js';
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
  const [ss,ps,bs]=await Promise.all([
   this.pool.query('SELECT service_id AS id,display_name AS "displayName" FROM qr_services ORDER BY service_id'),
   this.pool.query('SELECT service_id AS "serviceId",environment,sequence,status,ir_sha256 AS "irSha256",key_id AS "keyId",staged_by AS "stagedBy",approved_by AS "approvedBy",published_by AS "publishedBy" FROM qr_signed_promotions ORDER BY service_id,environment,sequence'),
   this.pool.query('SELECT service_id AS "serviceId",environment,published_sequence AS sequence,published_ir_sha256 AS "irSha256" FROM qr_scopes WHERE published_sequence>0 ORDER BY service_id,environment')
  ]);
  return {services:ss.rows,policies:[],bindings:[],signedPromotions:ps.rows.map(x=>({...x,sequence:Number(x.sequence)})),signedBindings:bs.rows.map(x=>({...x,sequence:Number(x.sequence)}))};
 }
 async verifyGovernanceIntegrity(){
  // Read-only validation, detecting missing events, altered links, mismatched
  // heads and status/audit inconsistencies without mutating operator state.
  const scopes=await this.pool.query('SELECT service_id,environment,published_sequence FROM qr_scopes ORDER BY service_id,environment');
  for(const scope of scopes.rows){
   const s=scope.service_id,e=scope.environment;
   const [head,events,promotions]=await Promise.all([
    this.pool.query('SELECT last_hash FROM qr_governance_heads WHERE service_id=$1 AND environment=$2',[s,e]),
    this.pool.query('SELECT sequence,actor,action,previous_hash,event_hash FROM qr_governance_events WHERE service_id=$1 AND environment=$2 ORDER BY event_id',[s,e]),
    this.pool.query('SELECT sequence,status,staged_by,approved_by,published_by FROM qr_signed_promotions WHERE service_id=$1 AND environment=$2',[s,e])
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
  await this.pool.query('SELECT 1');
  const migration=await checkMigrations(this.pool);
  const audit=await this.verifyGovernanceIntegrity();
  return {ready:true,backend:'postgres',migration:migration.version,checkedScopes:audit.scopes};
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
