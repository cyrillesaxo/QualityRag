// Bounded inbox-to-index worker. The index and inbox share the same PostgreSQL
// database; a single transaction ensures that retries cannot lose events.
export class BalafonsIndexWorker{
 constructor({pool}){if(!pool?.connect)throw new Error('POSTGRES_POOL_REQUIRED');this.pool=pool}
 async processBatch(limit=20){
  if(!Number.isSafeInteger(limit)||limit<1||limit>100)throw new Error('INVALID_BATCH_SIZE');
  const c=await this.pool.connect();let count=0;
  try{
   await c.query('BEGIN');
   const r=await c.query(`SELECT * FROM qr_balafons_evidence_inbox
    WHERE state='pending' ORDER BY created_at,event_id
    FOR UPDATE SKIP LOCKED LIMIT $1`,[limit]);
   for(const e of r.rows){
    // Quarantine malformed evidence without blocking unrelated tenants.
    if(e.tenant_id!=='balafons:'+e.principal_id||!e.source_id?.startsWith(e.tenant_id+':')||
      e.acl?.owner_id!==e.principal_id||e.acl?.visibility!=='private'||!['index','delete'].includes(e.action))
    {await c.query(`UPDATE qr_balafons_evidence_inbox SET state='failed',attempts=attempts+1,content=NULL,updated_at=now() WHERE event_id=$1 AND state='pending'`,[e.event_id]);continue;}
    // Missing monotonic sequence cannot safely establish source order.
    if(!((typeof e.source_sequence==='number'&&Number.isSafeInteger(e.source_sequence)&&e.source_sequence>=0)||(typeof e.source_sequence==='string'&&/^(0|[1-9][0-9]*)$/.test(e.source_sequence)&&BigInt(e.source_sequence)<=BigInt(Number.MAX_SAFE_INTEGER)))){
     await c.query(`UPDATE qr_balafons_evidence_inbox SET state='failed',attempts=attempts+1,content=NULL,updated_at=now() WHERE event_id=$1 AND state='pending'`,[e.event_id]);continue;
    }
    // Lock by source so concurrent workers cannot interleave revisions.
    await c.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',[e.tenant_id+'\\0'+e.source_id]);
    const watermark=await c.query('SELECT source_sequence FROM qr_source_watermarks WHERE tenant_id=$1 AND principal_id=$2 AND source_id=$3 FOR UPDATE',[e.tenant_id,e.principal_id,e.source_id]);
    if(watermark.rows.length&&BigInt(watermark.rows[0].source_sequence)>=BigInt(e.source_sequence)){
     await c.query(`UPDATE qr_balafons_evidence_inbox SET state='completed',content=NULL,updated_at=now(),attempts=attempts+1 WHERE event_id=$1 AND state='pending'`,[e.event_id]);continue;
    }
    await c.query('DELETE FROM qr_source_chunks WHERE tenant_id=$1 AND principal_id=$2 AND source_id=$3',
     [e.tenant_id,e.principal_id,e.source_id]);
    if(e.action==='index'){
     if(typeof e.content!=='string'||!e.content.trim()||typeof e.revision!=='string'||!e.revision)throw new Error('INVALID_INDEX_EVENT');
     const {chunkDocument}=await import('./private-retrieval.js');
     for(const chunk of chunkDocument(e.content))await c.query(`INSERT INTO qr_source_chunks
      (tenant_id,principal_id,source_id,revision,ordinal,start_offset,end_offset,content,metadata)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)`,
      [e.tenant_id,e.principal_id,e.source_id,e.revision,chunk.ordinal,chunk.start,chunk.end,chunk.text,JSON.stringify(e.metadata??{})]);
    }
    await c.query(`INSERT INTO qr_source_watermarks(tenant_id,principal_id,source_id,source_sequence,last_event_id,deleted) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(tenant_id,source_id) DO UPDATE SET source_sequence=EXCLUDED.source_sequence,last_event_id=EXCLUDED.last_event_id,deleted=EXCLUDED.deleted,updated_at=now()`,[e.tenant_id,e.principal_id,e.source_id,e.source_sequence,e.event_id,e.action==='delete']);
    await c.query(`UPDATE qr_balafons_evidence_inbox SET state='completed',content=NULL,updated_at=now(),attempts=attempts+1
     WHERE event_id=$1 AND tenant_id=$2 AND principal_id=$3 AND state='pending'`,
     [e.event_id,e.tenant_id,e.principal_id]);count++;
   }
   await c.query('COMMIT');return {processed:count};
  }catch(error){await c.query('ROLLBACK').catch(()=>{});throw error}finally{c.release()}
 }
}
