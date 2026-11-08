import {createHmac,timingSafeEqual} from 'node:crypto';
const HEX=/^[a-f0-9]{64}$/;
const ID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// The caller MUST authenticate the Balafons service and independently resolve
// the authorized owner. Never derive expectedOwnerId from untrusted payload.
export async function acceptBalafonsEvidence({payload,signature,secret,expectedOwnerId,replayStore,skipReplayClaim=false,now=Date.now()}){
 if(typeof secret!=='string'||secret.length<32)throw new Error('EVIDENCE_SECRET_REQUIRED');
 if(typeof payload!=='string'||Buffer.byteLength(payload)>500000||!HEX.test(signature||''))throw new Error('INVALID_EVIDENCE_ENVELOPE');
 if(typeof expectedOwnerId!=='string'||!expectedOwnerId||expectedOwnerId.length>256)throw new Error('AUTHENTICATED_OWNER_REQUIRED');
 if(!skipReplayClaim&&(!replayStore||typeof replayStore.claim!=='function'))throw new Error('REPLAY_STORE_REQUIRED');
 const mac=createHmac('sha256',secret).update(payload).digest();
 if(!timingSafeEqual(mac,Buffer.from(signature,'hex')))throw new Error('INVALID_EVIDENCE_SIGNATURE');
 let e;try{e=JSON.parse(payload)}catch{throw new Error('INVALID_EVIDENCE_JSON')}
 if(e.schema!=='qualityrag.balafons.source/v1'||!ID.test(e.event_id||'')||
  e.principal_id!==expectedOwnerId||e.tenant_id!=='balafons:'+expectedOwnerId||
  e.acl?.owner_id!==expectedOwnerId||e.acl?.visibility!=='private'||
  typeof e.source_id!=='string'||!e.source_id.startsWith('balafons:'+expectedOwnerId+':'))throw new Error('EVIDENCE_OWNER_MISMATCH');
 const at=Date.parse(e.occurred_at);
 if(!Number.isFinite(at)||Math.abs(now-at)>300000)throw new Error('EVIDENCE_EVENT_EXPIRED');
 if(!['index','delete'].includes(e.action))throw new Error('INVALID_EVIDENCE_ACTION');
 if(e.action==='index'&&(!HEX.test(e.revision||'')||typeof e.content!=='string'))throw new Error('INVALID_EVIDENCE_SOURCE');
 // Atomic claim must precede any side effect; the ingestion worker must be
 // idempotent and record durable job outcome separately.
 if(!skipReplayClaim){
  const claimed=await replayStore.claim({eventId:e.event_id,tenantId:e.tenant_id,principalId:expectedOwnerId,expiresAt:new Date(at+300000)});
  if(!claimed)throw new Error('EVIDENCE_REPLAY');
 }
 return {tenant_id:e.tenant_id,principal_id:expectedOwnerId,source_id:e.source_id,
  action:e.action,revision:e.revision,content:e.content,metadata:e.metadata,acl:e.acl,event_id:e.event_id};
}
export class PgEvidenceReplayStore{
 constructor(pool){this.pool=pool}
 async claim({eventId,tenantId,principalId,expiresAt}){
  const r=await this.pool.query(`INSERT INTO qr_balafons_evidence_events(event_id,tenant_id,principal_id,expires_at)
    VALUES ($1,$2,$3,$4) ON CONFLICT (event_id) DO NOTHING RETURNING event_id`,
   [eventId,tenantId,principalId,expiresAt]);return r.rowCount===1;
 }
}
