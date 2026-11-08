import React,{useEffect,useState} from 'react';

type Source={sourceId:string;filename:string;mimeType:string;revision:string;lineCount:number;
  searchable:boolean;evidenceStatus:string;provenanceStatus:string};
type Inventory={name:string;mimeType:string;status:string};
type Activity={at:string;sourceId:string;action:string;reason:string};
type Visibility={
  indexed:boolean;stale?:boolean;lastSyncedAt?:string;
  account?:string;folderId?:string;scope?:string;coverage:string;
  summary?:{listed:number;eligible:number;indexed:number;unsupported:number;failed:number;
    tooLarge:number;excludedEmpty:number;truncatedLines:number};
  sources:Source[];inventory:Inventory[];activity:Activity[];
  sourceTruth:string;packSpecAdmission:string;activityLogScope?:string
};
type Props={token:string;folderId:string|null;connected:boolean;
  indexEnabled:boolean;lastSyncedAt?:string};

export function DriveTrustControls({token,folderId,connected,indexEnabled,lastSyncedAt}:Props){
 const [report,setReport]=useState<Visibility|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState('');
 const [reason,setReason]=useState('OUT_OF_SCOPE');
 const [updated,setUpdated]=useState('');
 useEffect(()=>{
   let mounted=true;
   setReport(null);setError('');setUpdated('');
   if(!token||!connected||!indexEnabled||!folderId)return;
   fetch('/v1/drives/google/visibility',{
     headers:{Authorization:'Bearer '+token},cache:'no-store',redirect:'error'
   }).then(async res=>{
     const data=await res.json();
     if(!res.ok)throw Error(String(data.error||'Unable to read source inventory'));
     if(mounted)setReport(data);
   }).catch(e=>{if(mounted)setError(String(e))});
   return()=>{mounted=false};
 },[token,folderId,connected,indexEnabled,lastSyncedAt]);
 async function control(sourceId:string,searchable:boolean){
   setBusy(sourceId);setError('');setUpdated('');
   try{
     const response=await fetch('/v1/drives/google/source-control',{
       method:'POST',cache:'no-store',redirect:'error',
       headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
       body:JSON.stringify({sourceId,searchable,
         reason:searchable?'OWNER_SELECTION':reason})
     });
     const data=await response.json();
     if(!response.ok)throw Error(String(data.error||'Source control failed'));
     setReport(data.visibility);
     setUpdated(searchable?
       'Source explicitly included in your private lexical search. No evidence admission performed.':
       'Source excluded from your private lexical search. Exclusion persists after resync.');
   }catch(e){setError(String(e))}
   finally{setBusy('')}
 }
 function exportReport(){
   if(!report?.indexed)return;
   const data={schema:'qualityrag.drive-visibility-preview/v1',
     exportedAt:new Date().toISOString(),verification:'NOT_EXTERNALLY_ATTESTED',
     claim:'OWNER_CONTROLLED_LOCAL_INVENTORY_ONLY',report};
   const href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],
     {type:'application/json'}));
   const anchor=document.createElement('a');
   anchor.href=href;anchor.download='qualityrag-drive-source-visibility.json';
   document.body.append(anchor);anchor.click();anchor.remove();
   URL.revokeObjectURL(href);
 }
 if(!indexEnabled||!connected)return null;
 return <section aria-label="Source visibility and control" style={{
   border:'1px solid #bcd9c4',borderRadius:13,padding:16,
   background:'#fff',marginTop:16}}>
   <h4 style={{marginTop:0}}>Evidence visibility and owner control</h4>
   <p><strong>Credibility requires visibility and control.</strong> Inspect each indexed source,
     see exclusions and omissions, and decide whether a source may appear in your private
     lexical search. This does not authorize a QualityRAG answer.</p>
   {!report&&<p role="status">Loading the current source inventory…</p>}
   {report?.indexed&&<>
     <div style={{display:'flex',gap:14,flexWrap:'wrap',fontSize:13}}>
       <span><strong>Scope:</strong> one selected folder, direct children only</span>
       <span><strong>Coverage:</strong> {report.coverage}</span>
       <span><strong>Freshness:</strong> {report.stale?'STALE':'CURRENTLY CACHED'}</span>
       <span><strong>Authenticity:</strong> {report.sourceTruth}</span>
       <span><strong>PackSpec:</strong> {report.packSpecAdmission}</span>
     </div>
     <p style={{fontSize:13,marginTop:10}}>
       {report.summary?.listed??0} listed · {report.summary?.indexed??0} indexed ·
       {report.summary?.unsupported??0} unsupported ·
       {report.summary?.failed??0} failed ·
       {report.summary?.tooLarge??0} oversized ·
       {report.summary?.truncatedLines??0} truncated
     </p>
     <div className="line" style={{marginBottom:12}}>
       <label>Reason for excluding a source
         <select value={reason} onChange={e=>setReason(e.target.value)} aria-label="Exclusion reason">
           <option value="OUT_OF_SCOPE">Outside approved scope</option>
           <option value="SENSITIVE">Sensitive content</option>
           <option value="NEEDS_REVIEW">Needs domain review</option>
         </select>
       </label>
       <button type="button" onClick={exportReport} disabled={Boolean(busy)}>
         Export unsigned visibility report
       </button>
     </div>
     <div style={{overflowX:'auto'}}>
       <table style={{width:'100%',borderCollapse:'collapse',fontSize:13}}>
         <thead><tr>
           <th scope="col" align="left">Source</th>
           <th scope="col" align="left">Search control</th>
           <th scope="col" align="left">Review status</th>
           <th scope="col" align="left">Owner action</th>
         </tr></thead>
         <tbody>{report.sources.map(source=><tr key={source.sourceId}>
           <td style={{borderTop:'1px solid #e2eae3',padding:9}}>
             <strong>{source.filename}</strong>
             <div style={{fontSize:11,wordBreak:'break-word'}}>
               {source.mimeType} · revision {source.revision.slice(0,14)}…
               · {source.lineCount} extracted lines
             </div>
           </td>
           <td style={{borderTop:'1px solid #e2eae3',padding:9}}>
             {source.searchable?'Included in private search':'Excluded from search'}
           </td>
           <td style={{borderTop:'1px solid #e2eae3',padding:9}}>
             {source.evidenceStatus}<div style={{fontSize:11}}>{source.provenanceStatus}</div>
           </td>
           <td style={{borderTop:'1px solid #e2eae3',padding:9}}>
             <button type="button" disabled={Boolean(busy)||Boolean(report.stale)}
               onClick={()=>control(source.sourceId,!source.searchable)}>
               {source.searchable?'Exclude':'Include'}
             </button>
           </td>
         </tr>)}</tbody>
       </table>
     </div>
     {report.sources.length===0&&<p role="status">No text sources indexed in this folder.</p>}
     <details style={{marginTop:12}}>
       <summary>Show all files considered during sync ({report.inventory.length})</summary>
       <ul>{report.inventory.map((file,i)=><li key={i}>
         {file.name} · {file.mimeType} · <strong>{file.status}</strong>
       </li>)}</ul>
     </details>
     <details style={{marginTop:12}}>
       <summary>Show recent owner-control activity ({report.activity.length})</summary>
       <ul>{report.activity.map((activity,i)=><li key={activity.at+'-'+activity.sourceId+'-'+i}>
         {activity.at} · {activity.action} · {activity.reason} ·
         source {activity.sourceId.slice(-10)}
       </li>)}</ul>
       <p>This is a local operational history, not a signed, externally anchored audit log.</p>
     </details>
     <p style={{fontSize:12}}>
       This inventory proves neither publisher authenticity nor source independence.
       An excluded source is removed from this private lexical search, but any previously
       exported report must be handled separately. Customer acceptance requires
       a reviewed PackSpec and independently verified custody.
     </p>
   </>}
   {report&&!report.indexed&&<p role="status">No indexed source inventory.
     Choose a folder and sync explicitly to inspect the sources.</p>}
   {updated&&<p role="status">{updated}</p>}
   {error&&<p role="alert">{error}</p>}
 </section>;
}
