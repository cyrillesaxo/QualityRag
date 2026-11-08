// Minimal tenant-scoped retrieval foundation. This is lexical retrieval,
// not an embedding/vector index and not an answer generator.
const words=s=>(String(s).toLowerCase().match(/[\p{L}\p{N}]+/gu)||[]).filter(w=>w.length>1);
export function chunkDocument(content,{size=900,overlap=120}={}){
 if(typeof content!=='string'||!content.trim())throw new Error('EMPTY_DOCUMENT');
 if(!Number.isInteger(size)||size<100||size>10000||!Number.isInteger(overlap)||overlap<0||overlap>=size)throw new Error('INVALID_CHUNK_CONFIG');
 const chunks=[];for(let start=0;start<content.length;start+=size-overlap){
  const end=Math.min(content.length,start+size);chunks.push({ordinal:chunks.length,text:content.slice(start,end),start,end});if(end===content.length)break;
 }return chunks;
}
export class PrivateRetrievalIndex{
 constructor(){this.docs=new Map()}
 upsert({tenantId,principalId,sourceId,revision,content,metadata={}}){
  if(!tenantId||!principalId||tenantId!=='balafons:'+principalId||typeof sourceId!=='string'||!sourceId.startsWith(tenantId+':')||typeof revision!=='string'||!revision||!metadata||typeof metadata!=='object'||Array.isArray(metadata))throw new Error('INVALID_SOURCE_SCOPE');
  const key=tenantId+'\\0'+sourceId;
  this.docs.set(key,{tenantId,principalId,sourceId,revision,metadata:{...metadata},chunks:chunkDocument(content)});
 }
 delete({tenantId,principalId,sourceId}){
  if(tenantId!=='balafons:'+principalId||!sourceId?.startsWith(tenantId+':'))throw new Error('INVALID_SOURCE_SCOPE');
  return this.docs.delete(tenantId+'\\0'+sourceId);
 }
 search({tenantId,principalId,query,limit=8}){
  if(tenantId!=='balafons:'+principalId||typeof query!=='string'||!query.trim()||query.length>500||!Number.isInteger(limit)||limit<1||limit>50)throw new Error('INVALID_SEARCH_SCOPE');
  const terms=[...new Set(words(query))];if(!terms.length)return [];
  const hits=[];
  for(const d of this.docs.values()){
   if(d.tenantId!==tenantId||d.principalId!==principalId)continue;
   for(const c of d.chunks){const tokens=words(c.text),counts=new Map();for(const t of tokens)counts.set(t,(counts.get(t)||0)+1);
    const matched=terms.filter(t=>counts.has(t));if(!matched.length)continue;
    const score=matched.reduce((n,t)=>n+1+Math.log1p(counts.get(t)),0)/Math.sqrt(tokens.length||1);
    hits.push({tenant_id:tenantId,source_id:d.sourceId,revision:d.revision,chunk_ordinal:c.ordinal,start:c.start,end:c.end,text:c.text,metadata:{...d.metadata},score});
   }
  }
  return hits.sort((a,b)=>b.score-a.score||a.source_id.localeCompare(b.source_id)||a.chunk_ordinal-b.chunk_ordinal).slice(0,limit);
 }
}
