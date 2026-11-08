import React,{useEffect,useState} from 'react';

type Verdict='ADMIT'|'REFUSE'|'INCONCLUSIVE';
type Finding={requirement_id:string;verdict:Verdict;independent_sources:number;reasons:string[]};
type Evidence={id:string;requirement_id:string;origin:string;source_ref:string;status:string;observed_at:string};
type Review={at:string;actorHash:string;decision:'ACCEPTED'|'DISPUTED';reasonCode:string;note:string;chainHash:string};
type Evaluation={id:string;serviceId:string;environment:string;requestId:string;traceId:string;at:string;
  policySha256:string;evaluator:string;verdict:Verdict;findings:Finding[];evidence:Evidence[];
  requirements:{id:string;min_independent_sources?:number;max_age_seconds?:number}[];
  reviewHistory:Review[];chainHash:string;declaredOriginsOnly:boolean};
type Replay={reproduced:boolean;verdict:Verdict;asOf:string;policySha256:string;
  result:{verdict:Verdict;findings:Finding[]};scope:string;sourceAuthenticityVerified:boolean};
type Props={token:string;serviceId:string;environment:string};
const forest='#102d21',green='#038112',muted='#587064';
const panel:React.CSSProperties={border:'1px solid #cfe2d4',borderRadius:13,padding:18,background:'#fff'};
const verdictStyle=(v:Verdict):React.CSSProperties=>({fontWeight:800,fontSize:12,padding:'5px 9px',borderRadius:16,
 background:v==='ADMIT'?'#e8f8eb':v==='REFUSE'?'#ffece8':'#fff4df',
 color:v==='ADMIT'?'#076c1c':v==='REFUSE'?'#a83224':'#926316'});
const reasons=['REPRODUCED','FALSE_BLOCK','PROVENANCE_UNVERIFIED','POLICY_DISAGREEMENT','OTHER'];
export function EvidenceTelemetryLive({token,serviceId,environment}:Props){
 const [records,setRecords]=useState<Evaluation[]>([]);
 const [selected,setSelected]=useState('');
 const [status,setStatus]=useState('Connect to see recorded events, not synthetic examples.');
 const [busy,setBusy]=useState(false);
 const [observed,setObserved]=useState<number|null>(null);
 const [replay,setReplay]=useState<Replay|null>(null);
 const [reasonCode,setReasonCode]=useState(reasons[0]);
 const [note,setNote]=useState('');
 const current=records.find(x=>x.id===selected);
 useEffect(()=>{setRecords([]);setSelected('');setObserved(null);setReplay(null);
   setStatus('Scope changed. Refresh to load authorized evidence telemetry.');
 },[serviceId,environment,token]);
 const api=async(route:string,method='GET',body?:unknown)=>{
   if(!token)throw Error('A scoped registry token is required.');
   const response=await fetch(route,{method,headers:{
     Authorization:'Bearer '+token,'Content-Type':'application/json'
   },body:body===undefined?undefined:JSON.stringify(body),redirect:'error'});
   const result=await response.json();
   if(!response.ok)throw Error(result.error||'Evidence telemetry request failed');
   return result;
 };
 async function refresh(){
   setBusy(true);
   try{
    const q=new URLSearchParams({serviceId,environment});
    const data=await api('/v1/evidence/evaluations?'+q.toString());
    setRecords(data.evaluations||[]);setObserved(data.observedCount);
    setSelected(old=>(data.evaluations||[]).some((x:Evaluation)=>x.id===old)?old:
       data.evaluations?.[0]?.id||'');
    setReplay(null);
    setStatus('Registry evidence ledger loaded. Coverage of eligible requests is unknown.');
   }catch(e){setRecords([]);setSelected('');setReplay(null);setObserved(null);setStatus(String(e))}
   finally{setBusy(false)}
 }
 async function runReplay(){
   if(!current)return;
   setBusy(true);
   try{const r=await api('/v1/evidence/evaluations/'+current.id+'/replay','POST');
     setReplay(r);setStatus(r.reproduced?'Deterministic replay matches the recorded outcome.':'REPLAY MISMATCH — investigate integrity.');
   }catch(e){setStatus(String(e))}finally{setBusy(false)}
 }
 async function review(decision:'ACCEPTED'|'DISPUTED'){
   if(!current)return;
   setBusy(true);
   try{
     await api('/v1/evidence/evaluations/'+current.id+'/reviews','POST',{decision,reasonCode,note:note.trim()});
     setStatus('Authenticated review appended. The engine verdict was not modified.');
     setNote('');
     await refresh();
   }catch(e){setStatus(String(e));setBusy(false)}
 }
 function exportReceipt(){
   if(!current)return;
   const safe={schema:'qualityrag.evidence-review-export/v1',type:'server_record',
     unsigned:true,not_a_compliance_certificate:true,
     evaluation:current,replay,retrievedAt:new Date().toISOString()};
   const url=URL.createObjectURL(new Blob([JSON.stringify(safe,null,2)],{type:'application/json'}));
   const link=document.createElement('a');link.href=url;
   link.download='qualityrag-evidence-'+current.id+'.json';document.body.append(link);
   link.click();link.remove();URL.revokeObjectURL(url);
 }
 return <section className="panel" style={{borderTop:'4px solid '+green}} aria-label="Recorded Evidence Assurance telemetry">
   <div style={{display:'flex',alignItems:'start',justifyContent:'space-between',gap:12,flexWrap:'wrap'}}>
     <div><p style={{margin:'0 0 5px',color:green,fontSize:12,fontWeight:800,letterSpacing:'.10em'}}>6. EVIDENCE ASSURANCE / RECORDED TELEMETRY</p>
       <h2 style={{fontSize:25}}>Show me the evidence — from an actual registry event.</h2>
       <p>Replay captured metadata against its approved, pinned PackSpec. A separate authorized reviewer can accept or dispute a finding.</p>
     </div>
     <button type="button" disabled={!token||busy} onClick={refresh}>Refresh recorded events</button>
   </div>
   <p className="notice"><strong>Local, opt-in ledger.</strong> No live telemetry exists until an application explicitly sends evaluation events. Source origin labels are declared, not independently authenticated. The hash chain is not an externally anchored audit record.</p>
   <p style={{fontSize:13,color:muted}}>
    Service: <code>{serviceId}</code> · Environment: <code>{environment}</code> ·
    Observed events: <strong>{observed===null?'unknown':observed}</strong> ·
    Eligible request coverage: <strong>unknown</strong>
   </p>
   <p role="status" style={{fontSize:13,color:forest}}>{status}</p>
   {records.length===0 ? <div style={panel}><strong>No telemetry events shown.</strong>
     <p>To collect one, configure the local registry ledger and send a scoped evaluation event with opaque source and origin tokens. The synthetic demonstrations below are not observations from customers.</p></div>
   :<div className="columns" style={{gridTemplateColumns:'minmax(220px,1fr) minmax(350px,2fr)',gap:15}}>
      <div style={panel}>
        <h3 style={{marginTop:0}}>Recorded evaluations</h3>
        {records.map(r=><button type="button" key={r.id} aria-pressed={selected===r.id}
          onClick={()=>{setSelected(r.id);setReplay(null);setStatus('Showing a recorded event.');}}
          style={{display:'block',width:'100%',textAlign:'left',marginBottom:8,
            background:selected===r.id?'#e8f8eb':'#f8fbf9',color:forest,border:'1px solid #d4e4d7'}}>
          <strong>{r.requestId}</strong> <span style={verdictStyle(r.verdict)}>{r.verdict}</span>
          <div style={{fontSize:11,marginTop:6}}>{r.at} · {r.findings.length} requirement(s)</div>
        </button>)}
      </div>
      {current&&<div style={panel}>
        <h3 style={{marginTop:0}}>Evidence inspector</h3>
        <p style={{fontSize:12}}>Event ID <code>{current.id}</code><br/>
          Trace ID <code>{current.traceId}</code><br/>
          PackSpec SHA-256 <code style={{wordBreak:'break-all'}}>{current.policySha256}</code><br/>
          Evaluator <code>{current.evaluator}</code></p>
        <span style={verdictStyle(current.verdict)}>{current.verdict}</span>
        <h4>Required evidence</h4>
        <div style={{overflowX:'auto'}}><table style={{width:'100%',fontSize:13,borderCollapse:'collapse'}}>
          <thead><tr><th align="left">Obligation</th><th align="left">Result</th><th align="left">Origins</th><th align="left">Reason</th></tr></thead>
          <tbody>{current.findings.map(f=><tr key={f.requirement_id}>
            <td style={{padding:8,borderBottom:'1px solid #ddd'}}>{f.requirement_id}</td>
            <td style={{padding:8,borderBottom:'1px solid #ddd'}}>{f.verdict}</td>
            <td style={{padding:8,borderBottom:'1px solid #ddd'}}>{f.independent_sources}</td>
            <td style={{padding:8,borderBottom:'1px solid #ddd'}}>{f.reasons.join(', ')||'declared checks satisfied'}</td>
          </tr>)}</tbody>
        </table></div>
        <details style={{marginTop:12}}><summary>Inspectable source-token metadata ({current.evidence.length})</summary>
          {current.evidence.map(e=><p key={e.id} style={{fontSize:12,overflowWrap:'anywhere'}}>
            <strong>{e.id}</strong> · {e.status}<br/>Source token {e.source_ref}<br/>
            Origin token {e.origin}<br/>Observed {e.observed_at}</p>)}
        </details>
        <div className="line" style={{marginTop:15}}>
          <button type="button" disabled={busy} onClick={runReplay}>Re-run pinned evaluation</button>
          <button type="button" disabled={busy} onClick={exportReceipt}>Export unsigned receipt</button>
        </div>
        {replay&&<p role="status" style={{color:replay.reproduced?green:'#a12a23',fontWeight:700,fontSize:13}}>
         Replay {replay.reproduced?'MATCH':'MISMATCH'} · {replay.verdict} · as of {replay.asOf}.
         This is same-server deterministic replay, not independent source validation.</p>}
        <h4>Customer challenge</h4>
        <p>Acceptance never changes the engine decision. OIDC review role and a separate reviewer identity are required.</p>
        <label>Reason code
          <select value={reasonCode} onChange={e=>setReasonCode(e.target.value)}
            style={{padding:11,borderRadius:8,border:'1px solid #c8d6df'}}>
            {reasons.map(x=><option key={x} value={x}>{x.replaceAll('_',' ')}</option>)}
          </select>
        </label>
        <label>Optional non-sensitive note (280 characters)
          <textarea value={note} maxLength={280} onChange={e=>setNote(e.target.value)}
            placeholder="No customer names, documents, secrets or personal data."/>
        </label>
        <div className="line"><button type="button" disabled={busy} onClick={()=>review('ACCEPTED')}>Accept finding</button>
          <button type="button" disabled={busy} onClick={()=>review('DISPUTED')}>Dispute finding</button></div>
        <h4>Recorded reviews</h4>
        {current.reviewHistory.length===0?<p>No customer review recorded.</p>:
          <ul>{current.reviewHistory.map((r,i)=><li key={r.chainHash}>
            {r.decision} · {r.reasonCode} · {r.at} · reviewer {r.actorHash.slice(0,12)}…
            {r.note&&<div>{r.note}</div>}</li>)}</ul>}
      </div>}
    </div>}
   <p style={{fontSize:12,color:muted}}>This interface reads stored evaluations only; it does not claim to measure every request. A missing event is not proof of an acceptable answer.</p>
 </section>;
}
