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
    if(e.tenant_id!=='balafons:'+e.principal_id||!e.source_id?.startsWith(e.tenant_id+':')||
      e.acl?.owner_id!==e.principal_id||e.acl?.visibility!=='private'||!['index','delete'].includes(e.action))
     throw new Error('INBOX_SCOPE_INVALID');
    // Lock by source so concurrent workers cannot interleave revisions.
    await c.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',[e.tenant_id+'\\0'+e.source_id]);
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
    await c.query(`UPDATE qr_balafons_evidence_inbox SET state='completed',content=NULL,updated_at=now(),attempts=attempts+1
     WHERE event_id=$1 AND tenant_id=$2 AND principal_id=$3 AND state='pending'`,
     [e.event_id,e.tenant_id,e.principal_id]);count++;
   }
   await c.query('COMMIT');return {processed:count};
  }catch(error){await c.query('ROLLBACK').catch(()=>{});throw error}finally{c.release()}
 }
}
