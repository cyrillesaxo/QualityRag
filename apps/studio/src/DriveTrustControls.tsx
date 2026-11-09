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
type GovernedCheck={
 schema:string;result:'REFUSE'|'INCONCLUSIVE';evaluationAdmitted:boolean;
 decisionBoundary:string;meaningVerified:boolean;independentProvenanceVerified:boolean;
 policy:{id:string;version:string;sha256:string};
 telemetry?:{recorded:boolean;receiptId:string|null;chainHash:string|null;
  externallyAnchored:boolean;scope:string};
 observations:{sourceId:string;decision:string;reasons:string[];eligibleForReviewedEvidence:boolean}[];
};
type Props={token:string;folderId:string|null;connected:boolean;
  indexEnabled:boolean;lastSyncedAt?:string;serviceId:string;environment:string};

export function DriveTrustControls({token,folderId,connected,indexEnabled,
 lastSyncedAt,serviceId,environment}:Props){
 const [report,setReport]=useState<Visibility|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState('');
 const [reason,setReason]=useState('OUT_OF_SCOPE');
 const [updated,setUpdated]=useState('');
 const [governedChallengeAvailable,setGovernedChallengeAvailable]=useState(false);
 const [requirements,setRequirements]=useState<string[]>([]);
 const [requirement,setRequirement]=useState('');
 const [requirementsError,setRequirementsError]=useState('');
 const [gate,setGate]=useState<GovernedCheck|null>(null);
 const [gateBusy,setGateBusy]=useState(false);
 useEffect(()=>{
   let mounted=true;
   setReport(null);setError('');setUpdated('');setGate(null);
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
 useEffect(()=>{
   let active=true;
   setRequirements([]);setRequirement('');setGate(null);setRequirementsError('');
   setGovernedChallengeAvailable(false);
   if(!token||!connected||!indexEnabled||!serviceId||!environment)return;
   const query=new URLSearchParams({serviceId,environment});
   fetch('/v1/drives/google/governed-requirements?'+query.toString(),{
     headers:{Authorization:'Bearer '+token},redirect:'error',cache:'no-store'
   }).then(async result=>{
     const content=await result.json();
     if(!result.ok)throw Error(String(content.error||'Unable to resolve approved requirements'));
     const ids=(content.requirements||[]).map((r:{id:string})=>r.id);
     if(active){setRequirements(ids);setRequirement(ids[0]||'');
       setGovernedChallengeAvailable(content.schema==='qualityrag.drive-governed-requirements/v1');}
   }).catch(e=>{if(active){setGovernedChallengeAvailable(false);setRequirementsError('Governed candidate checks unavailable: '+String(e))}});
   return()=>{active=false};
 },[token,connected,indexEnabled,serviceId,environment]);
 async function checkGoverned(source:Source,record=false){
   if(!requirement)return;
   setGateBusy(true);setGate(null);setRequirementsError('');
   try{
     const result=await fetch(record?'/v1/drives/google/record-check':
       '/v1/drives/google/governed-check',{
       method:'POST',cache:'no-store',redirect:'error',
       headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
       body:JSON.stringify({serviceId,environment,candidates:[{
         sourceId:source.sourceId,revision:source.revision,
         requirementId:requirement,lineNumber:1
       }]})
     });
     const value=await result.json();
     if(!result.ok)throw Error(String(value.error||'Governed source check failed'));
     setGate(value);
   }catch(e){setRequirementsError(String(e))}
   finally{setGateBusy(false)}
 }
 async function control(sourceId:string,searchable:boolean){
   setBusy(sourceId);setError('');setUpdated('');setGate(null);
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
     <div style={{border:'1px solid #d6e7d8',padding:12,borderRadius:9,margin:'12px 0'}}>
       <strong>PackSpec candidate challenges — service-scoped availability</strong>
       <p style={{fontSize:13,margin:'6px 0'}}>Selected service: <code>{serviceId}</code>;
         environment: <code>{environment}</code>. Requires both
         <code> drive.reader</code> and <code> evidence.reader</code>, plus access
         to this service. No arbitrary browser-supplied PackSpec or verdict is accepted.</p>
       <label>Approved governing requirement
         <select value={requirement} onChange={e=>{
           setRequirement(e.target.value);setGate(null);
         }} disabled={!governedChallengeAvailable||!requirements.length||gateBusy}>
           {requirements.length===0?<option value="">No approved requirement available</option>:
             requirements.map(id=><option key={id} value={id}>{id}</option>)}
         </select>
       </label>
       <p style={{fontSize:12}}>These controls activate only after the Registry returns a valid, service-scoped requirements contract. Candidate checks cannot admit evidence or verify semantics.</p>
       <p style={{fontSize:12}}>Use “Check candidate” to preview without writing to
         the ledger. “Record challenge” requires a separate <code>evidence.reviewer</code>
         role, creates a local ledger receipt, and never changes source admission.
         Excluded sources are refused; included but unreviewed sources remain inconclusive.</p>
     </div>
     {gate&&<div role="status" style={{padding:12,margin:'10px 0',
       border:'1px solid #e6d7b6',background:'#fffaf0',borderRadius:8}}>
       <strong>Governed source check: {gate.result}</strong>
       <p>Policy {gate.policy.id} v{gate.policy.version}
         {' · '} SHA-256 <code>{gate.policy.sha256.slice(0,18)}…</code></p>
       <p>{gate.observations.flatMap(o=>o.reasons).join(', ')}</p>
       <p style={{fontSize:12}}>Admitted: {gate.evaluationAdmitted?'yes':'no'};
         meaning verified: {gate.meaningVerified?'yes':'no'};
         independent provenance verified: {gate.independentProvenanceVerified?'yes':'no'}.
         This check does not independently authenticate source content.</p>
       <p style={{fontSize:12}}>
         Local telemetry: <strong>{gate.telemetry?.recorded?'RECORDED':'NOT ENABLED'}</strong>
         {gate.telemetry?.receiptId?' · Receipt '+gate.telemetry.receiptId:''}.
         No externally anchored signature or customer acceptance is implied.</p>
     </div>}
     {requirementsError&&<p role="alert">{requirementsError}</p>}
     <div style={{overflowX:'auto'}}> 
       <table style={{width:'100%',borderCollapse:'collapse',fontSize:13}}>
         <thead><tr>
           <th scope="col" align="left">Source</th>
           <th scope="col" align="left">Search control</th>
           <th scope="col" align="left">Review status</th>
           <th scope="col" align="left">Owner action</th>
           <th scope="col" align="left">PackSpec check</th>
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
           <td style={{borderTop:'1px solid #e2eae3',padding:9}}>
             <button type="button" disabled={!governedChallengeAvailable||gateBusy||Boolean(busy)||!requirement}
               onClick={()=>checkGoverned(source)}>Check candidate</button>
             <button type="button" disabled={gateBusy||Boolean(busy)||!requirement}
               onClick={()=>checkGoverned(source,true)}>Record challenge (reviewer)</button>
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
