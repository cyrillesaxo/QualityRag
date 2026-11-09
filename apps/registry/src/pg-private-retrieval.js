import {chunkDocument} from './private-retrieval.js';
// Postgres full-text retrieval with explicit tenant predicates on every query.
export class PgPrivateRetrievalIndex {
 constructor(pool){if(!pool?.query||!pool?.connect)throw new Error('POSTGRES_POOL_REQUIRED');this.pool=pool}
 static scope({tenantId,principalId,sourceId}){
  if(typeof principalId!=='string'||!principalId||tenantId!=='balafons:'+principalId||
   (sourceId!==undefined&&(typeof sourceId!=='string'||!sourceId.startsWith(tenantId+':'))))throw new Error('INVALID_SOURCE_SCOPE');
 }
 async upsert({tenantId,principalId,sourceId,revision,content,metadata={}}){
  PgPrivateRetrievalIndex.scope({tenantId,principalId,sourceId});
  if(typeof revision!=='string'||!revision||!metadata||typeof metadata!=='object'||Array.isArray(metadata))throw new Error('INVALID_SOURCE_METADATA');
  const chunks=chunkDocument(content);const c=await this.pool.connect();
  try{await c.query('BEGIN');
   await c.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',[tenantId+'\\0'+sourceId]);
   await c.query('DELETE FROM qr_source_chunks WHERE tenant_id=$1 AND principal_id=$2 AND source_id=$3',[tenantId,principalId,sourceId]);
   for(const chunk of chunks)await c.query(`INSERT INTO qr_source_chunks
    (tenant_id,principal_id,source_id,revision,ordinal,start_offset,end_offset,content,metadata)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)`,
    [tenantId,principalId,sourceId,revision,chunk.ordinal,chunk.start,chunk.end,chunk.text,JSON.stringify(metadata)]);
   await c.query('COMMIT');return {source_id:sourceId,revision,chunks:chunks.length};
  }catch(e){await c.query('ROLLBACK').catch(()=>{});throw e}finally{c.release()}
 }
 async delete({tenantId,principalId,sourceId}){
  PgPrivateRetrievalIndex.scope({tenantId,principalId,sourceId});
  const c=await this.pool.connect();try{await c.query('BEGIN');
   await c.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',[tenantId+'\\0'+sourceId]);
   const r=await c.query('DELETE FROM qr_source_chunks WHERE tenant_id=$1 AND principal_id=$2 AND source_id=$3',[tenantId,principalId,sourceId]);
   await c.query('COMMIT');return r.rowCount>0;
  }catch(e){await c.query('ROLLBACK').catch(()=>{});throw e}finally{c.release()}
 }
 async search({tenantId,principalId,query,limit=8}){
  PgPrivateRetrievalIndex.scope({tenantId,principalId});
  if(typeof query!=='string'||!query.trim()||query.length>500||!Number.isInteger(limit)||limit<1||limit>50)throw new Error('INVALID_SEARCH_SCOPE');
  const r=await this.pool.query(`SELECT source_id,revision,ordinal AS chunk_ordinal,start_offset AS start,end_offset AS end,
   content AS text,metadata,ts_rank_cd(lexemes,plainto_tsquery('simple',$3)) AS score
   FROM qr_source_chunks WHERE tenant_id=$1 AND principal_id=$2
    AND lexemes @@ plainto_tsquery('simple',$3)
   ORDER BY score DESC,source_id,ordinal LIMIT $4`,[tenantId,principalId,query,limit]);
  return r.rows.map(row=>({...row,tenant_id:tenantId}));
 }
}
