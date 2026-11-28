// The private index is Balafons-specific and asynchronously updated.
// Reassemble a candidate only; do not use this as current-source authority.
export function reconstructIndexedSource(rows){
 if(!Array.isArray(rows)||rows.length===0||rows.length>130)return null;
 let text='',revision=rows[0]?.revision;
 if(typeof revision!=='string'||!revision)return null;
 for(let i=0;i<rows.length;i++){
  const r=rows[i];
  if(!r||r.revision!==revision||r.ordinal!==i||!Number.isInteger(r.start_offset)||!Number.isInteger(r.end_offset)||r.start_offset<0||r.end_offset<=r.start_offset||r.end_offset>100000||typeof r.content!=='string'||r.content.length!==r.end_offset-r.start_offset||r.start_offset>text.length||r.end_offset<=text.length)return null;
  const overlap=text.length-r.start_offset;
  if(r.content.slice(0,overlap)!==text.slice(r.start_offset))return null;
  text+=r.content.slice(overlap);
 }
 return {revision,text,authority:'INDEX_CANDIDATE_ONLY'};
}
// Live reader and target loader are trusted host adapters, not client inputs.
// The live reader must authenticate access, obtain current complete bytes and
// revision, and not substitute a cached search hit for the source.
export function createBalafonsQuestionSourceReader({pool,readAuthorizedLiveSource}={}){
 if(typeof pool?.query!=='function'||typeof readAuthorizedLiveSource!=='function')throw Error('LIVE_SOURCE_AUTHORITY_REQUIRED');
 return async function read(identity,sourceId){
  const principal=identity?.subject;
  if(typeof principal!=='string'||!principal||typeof sourceId!=='string'||!sourceId.startsWith('balafons:'+principal+':'))return null;
  const tenant='balafons:'+principal;
  try{
   const r=await pool.query(`SELECT c.revision,c.ordinal,c.start_offset,c.end_offset,c.content
    FROM qr_source_chunks c
    JOIN qr_source_watermarks w ON w.tenant_id=c.tenant_id AND w.principal_id=c.principal_id AND w.source_id=c.source_id
    JOIN qr_balafons_evidence_inbox i ON i.event_id=w.last_event_id AND i.tenant_id=c.tenant_id AND i.principal_id=c.principal_id AND i.source_id=c.source_id AND i.source_sequence=w.source_sequence AND i.revision=c.revision
    WHERE c.tenant_id=$1 AND c.principal_id=$2 AND c.source_id=$3 AND w.deleted=false AND i.state='completed' AND i.action='index'
    AND NOT EXISTS (SELECT 1 FROM qr_balafons_evidence_inbox pending WHERE pending.tenant_id=$1 AND pending.principal_id=$2 AND pending.source_id=$3 AND (pending.source_sequence IS NULL OR pending.source_sequence>w.source_sequence))
    ORDER BY c.ordinal LIMIT 131`,[tenant,principal,sourceId]);
   const candidate=reconstructIndexedSource(r.rows);
   if(!candidate)return null;
   const live=await readAuthorizedLiveSource(identity,sourceId);
   if(!live||live.id!==sourceId||live.revision!==candidate.revision||live.text!==candidate.text)return null;
   return {id:sourceId,revision:live.revision,text:live.text};
  }catch{return null;}
 };
}
