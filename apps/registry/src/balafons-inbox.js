// Atomic replay claim + durable inbox insertion, preventing accepted-but-lost events.
export class PgBalafonsEvidenceInbox{
 constructor(pool){if(!pool?.connect)throw new Error('POSTGRES_POOL_REQUIRED');this.pool=pool}
 async accept(event){
  if(!event||!event.event_id||!event.tenant_id||!event.principal_id||!event.source_id||
   event.tenant_id!=='balafons:'+event.principal_id||
   !Number.isSafeInteger(event.source_sequence)||event.source_sequence<0||!event.source_id.startsWith(event.tenant_id+':')||event.acl?.owner_id!==event.principal_id||
   event.acl?.visibility!=='private'||!['index','delete'].includes(event.action))throw new Error('INVALID_EVIDENCE_OWNER');
  const c=await this.pool.connect();
  try{
   await c.query('BEGIN');
   const claimed=await c.query(`INSERT INTO qr_balafons_evidence_events(event_id,tenant_id,principal_id,expires_at)
    VALUES($1,$2,$3,now()+interval '5 minutes') ON CONFLICT(event_id) DO NOTHING RETURNING event_id`,
    [event.event_id,event.tenant_id,event.principal_id]);
   if(claimed.rowCount!==1){await c.query('ROLLBACK');return false}
   await c.query(`INSERT INTO qr_balafons_evidence_inbox
    (event_id,tenant_id,principal_id,source_id,action,revision,content,metadata,acl,source_sequence)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10)`,
    [event.event_id,event.tenant_id,event.principal_id,event.source_id,event.action,event.revision,
     event.content,JSON.stringify(event.metadata??null),JSON.stringify(event.acl),event.source_sequence]);
   await c.query('COMMIT');return true;
  }catch(error){await c.query('ROLLBACK').catch(()=>{});throw error}
  finally{c.release()}
 }
 // Workers must use tenant-aware indexing and idempotent processing keyed by event_id.
 async claimBatch(limit=20){
  if(!Number.isSafeInteger(limit)||limit<1||limit>100)throw new Error('INVALID_BATCH_SIZE');
  const r=await this.pool.query(`WITH picked AS (
   SELECT event_id FROM qr_balafons_evidence_inbox WHERE state='pending'
   ORDER BY created_at,event_id FOR UPDATE SKIP LOCKED LIMIT $1
  ) UPDATE qr_balafons_evidence_inbox AS i SET state='processing',attempts=attempts+1,updated_at=now()
  FROM picked WHERE i.event_id=picked.event_id RETURNING i.*`,[limit]);return r.rows;
 }
 async complete({eventId,tenantId,principalId}){
  const r=await this.pool.query(`UPDATE qr_balafons_evidence_inbox SET state='completed',content=NULL,updated_at=now()
   WHERE event_id=$1 AND tenant_id=$2 AND principal_id=$3 AND state='processing' RETURNING event_id`,
   [eventId,tenantId,principalId]);if(r.rowCount!==1)throw new Error('INBOX_EVENT_NOT_FOUND');
 }
}
