import React,{useEffect,useState} from 'react';
import {ProtectedAdmission} from './ProtectedAdmission';

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
type Summary={admit:number;refuse:number;inconclusive:number;accepted:number;disputed:number;unreviewed:number;reviewedFalseBlocks:number;blockedUnattestedIngress?:number;governedCandidateChecks?:number;governedCandidateRefusals?:number};
type Protection={schema:string;serviceId:string;environment:string;protected:boolean;
  mode:'BLOCK_UNATTESTED_GENERIC_EVIDENCE'|'LEGACY_METADATA_GATE';
  genericEvidenceIngress:'BLOCKED'|'ALLOWED';sourceAdmission:string;
  independentSourceVerification:string;globalApplicationEnforcement:boolean;
  policy:{id:string;version:string;sha256:string};
  guardTelemetry:{observedBlockedAttempts:number;lastBlockedAt:string|null;
  protectedSince?:string|null;governedCandidateChecks?:number;
  governedCandidateRefusals?:number;lastCandidateCheckAt?:string|null;
  protectedDecisions?:number;protectedAdmitted?:number;protectedInconclusive?:number;
  protectedUses?:number;protectedBufferedReleases?:number;
  protectedRevocations?:number;
  externallyAnchored:boolean;coverage:string}};
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
 const [summary,setSummary]=useState<Summary|null>(null);
 const [protection,setProtection]=useState<Protection|null>(null);
 const [replay,setReplay]=useState<Replay|null>(null);
 const [reasonCode,setReasonCode]=useState(reasons[0]);
 const [note,setNote]=useState('');
 const current=records.find(x=>x.id===selected);
 useEffect(()=>{setRecords([]);setSelected('');setObserved(null);setSummary(null);setReplay(null);
   setProtection(null);
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
    const [data,protectedState]=await Promise.all([
      api('/v1/evidence/evaluations?'+q.toString()),
      api('/v1/evidence/enforcement?'+q.toString())
    ]);
    setRecords(data.evaluations||[]);setObserved(data.observedCount);setSummary(data.summary||null);
    setProtection(protectedState);
    setSelected(old=>(data.evaluations||[]).some((x:Evaluation)=>x.id===old)?old:
       data.evaluations?.[0]?.id||'');
    setReplay(null);
    setStatus('Registry evidence ledger loaded. Coverage of eligible requests is unknown.');
   }catch(e){setRecords([]);setSelected('');setReplay(null);setObserved(null);
     setSummary(null);setProtection(null);setStatus(String(e))}
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
 async function exportReceipt(){
   if(!current)return;
   setBusy(true);
   try{
     const packageData=await api('/v1/evidence/evaluations/'+current.id+'/export');
     if(packageData.payload?.schema!=='qualityrag.evidence-replay/v1')
       throw Error('Unsupported replay package.');
     const url=URL.createObjectURL(new Blob([JSON.stringify(packageData,null,2)],
       {type:'application/json'}));
     const link=document.createElement('a');link.href=url;
     link.download='qualityrag-replay-'+current.id+'.json';document.body.append(link);
     link.click();link.remove();URL.revokeObjectURL(url);
     setStatus('Server replay package exported. Verify separately using python -m qualityrag.verify_receipt. This export is unsigned.');
   }catch(e){setStatus(String(e))}
   finally{setBusy(false)}
 }
 return <section className="panel" style={{borderTop:'4px solid '+green}} aria-label="Recorded Evidence Assurance telemetry">
   <div style={{display:'flex',alignItems:'start',justifyContent:'space-between',gap:12,flexWrap:'wrap'}}>
     <div><p style={{margin:'0 0 5px',color:green,fontSize:12,fontWeight:800,letterSpacing:'.10em'}}>6. EVIDENCE ASSURANCE / RECORDED TELEMETRY</p>
       <h2 style={{fontSize:25}}>Show me the evidence — from an actual registry event.</h2>
       <p>Replay captured metadata against its approved, pinned PackSpec. A separate authorized reviewer can accept or dispute a finding.</p>
     </div>
     <button type="button" disabled={!token||busy} onClick={refresh}>Refresh recorded events</button>
   </div>
   {protection&&<div role="status" style={{padding:14,borderRadius:10,margin:'12px 0',
     border:'1px solid #ceded4',background:'#f6faf7',fontSize:13}}>
     <strong>Service evidence ingress: {protection.protected?
       'PROTECTED — generic unreviewed submissions are blocked':
       'LEGACY — generic metadata submissions remain allowed'}</strong>
     <p>PackSpec {protection.policy.id} v{protection.policy.version}
       {' · '} Mode: <code>{protection.mode}</code></p>
     <p>Protection activated: <strong>{protection.guardTelemetry.protectedSince||'not activated'}</strong>.</p>
     <p>Blocked generic submissions: <strong>{protection.guardTelemetry.observedBlockedAttempts}</strong>
       {protection.guardTelemetry.lastBlockedAt?
         ' · Last block: '+protection.guardTelemetry.lastBlockedAt:''}.</p>
     <p>Human-signed protected decisions:
       <strong> {protection.guardTelemetry.protectedDecisions||0}</strong>
       {' · '}Admitted signed claims:
       <strong> {protection.guardTelemetry.protectedAdmitted||0}</strong>.
       These are human-approved metadata claims, not independently proven facts.</p>
     <p>Request-specific evidence-use permissions issued:
       <strong> {protection.guardTelemetry.protectedUses||0}</strong>.
       Of these, <strong>{protection.guardTelemetry.protectedBufferedReleases||0}</strong>
       {' '}were issued by the server-buffered response gateway; the remainder
       were digest-only client checks. These counts reflect registry decisions,
       not confirmed network delivery or downstream answer correctness.
       A historical ADMIT or prior permit is not authorization for future
       answers; each use requires fresh permissions and current source bytes.</p>
     <p>Explicit owner-reviewed decision withdrawals:
       <strong> {protection.guardTelemetry.protectedRevocations||0}</strong>.
       A withdrawal leaves historical receipts replayable while blocking future use.</p>
     <p>Governed Drive candidate checks: <strong>{protection.guardTelemetry.governedCandidateChecks||0}</strong>
       {' · '}Refused: <strong>{protection.guardTelemetry.governedCandidateRefusals||0}</strong>
       {protection.guardTelemetry.lastCandidateCheckAt?
         ' · Most recent: '+protection.guardTelemetry.lastCandidateCheckAt:''}.</p>
     <p style={{fontSize:12}}>These are locally recorded registry events, not counts of all downstream
       application requests or an independently anchored audit record. Earlier ADMIT events may
       predate protection and are not retroactively authorized.</p>
     <p><strong>Remaining boundary:</strong> This is a server operator setting, not a tenant-wide or
       universal guarantee. Source authenticity, semantic review, independent admission, and external
       application enforcement are not yet implemented.</p>
   </div>}
   {protection?.protected&&<ProtectedAdmission token={token}
     serviceId={serviceId} environment={environment}
     enabled={protection.sourceAdmission==='TWO_TRUSTED_HUMAN_SIGNATURES_AND_LIVE_BYTES'}/>}
   <p className="notice"><strong>Local, opt-in ledger.</strong> No live telemetry exists until an application explicitly sends evaluation events. Source origin labels are declared, not independently authenticated. The hash chain is not an externally anchored audit record.</p>
   <p style={{fontSize:13,color:muted}}>
    Service: <code>{serviceId}</code> · Environment: <code>{environment}</code> ·
    Observed events: <strong>{observed===null?'unknown':observed}</strong> ·
    Eligible request coverage: <strong>unknown</strong>
   </p>
   {summary&&<div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(145px,1fr))',gap:10,margin:'12px 0'}}>
     {([['ADMIT',summary.admit],['INCONCLUSIVE',summary.inconclusive],['REFUSE',summary.refuse],
        ['Accepted findings',summary.accepted],['Disputed findings',summary.disputed],
        ['Not yet reviewed',summary.unreviewed],
        ['Blocked ingress',summary.blockedUnattestedIngress||0]] as [string,number][]).map(([name,count])=>
        <div key={name} style={{background:'#f5fbf6',border:'1px solid #dce7dd',borderRadius:10,padding:'12px 14px'}}>
          <div style={{fontSize:12,color:muted}}>{name}</div>
          <strong style={{display:'block',fontSize:25,color:forest}}>{count}</strong>
        </div>)}
   </div>}
   <p role="status" style={{fontSize:13,color:forest}}>{status}</p>
   {records.length===0 ? <div style={panel}><strong>No telemetry events shown.</strong>
     <p>{protection?.protected?
       'This service blocks generic evidence ingestion. Blocked attempts are tracked above, but they are not accepted evaluations. The scoped Drive candidate gate remains a separate review-only path.':
       'To collect one, configure the local registry ledger and send a scoped evaluation event with opaque source and origin tokens. The synthetic demonstrations below are not observations from customers.'}</p></div>
   :<div className="columns" style={{gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,330px),1fr))',gap:15}}>
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
          <button type="button" disabled={busy} onClick={exportReceipt}>Export independently replayable JSON</button>
        </div>
        <div role="note" style={{margin:'14px 0',padding:13,
          border:'1px solid #eed6a5',borderRadius:9,background:'#fffaf0',fontSize:13}}>
          <strong>Source custody is NOT authenticated by this dashboard.</strong>
          <p style={{margin:'8px 0'}}>Origin tokens are submitted by the application. Independent replay
            establishes a reproducible metadata decision, not genuine source independence.
            A customer custodian can separately sign the exact source-byte hashes and approved
            origin mapping without uploading private files to Studio.</p>
          <a href="https://github.com/cyrillesaxo/QualityRag/blob/feat/studio-evidence-assurance-telemetry-20261108/docs/EVIDENCE-CUSTOMER-SOURCE-CUSTODY.md"
            target="_blank" rel="noreferrer">Run the customer-controlled source custody challenge</a>
        </div>
        {replay&&<p role="status" style={{color:replay.reproduced?green:'#a12a23',fontWeight:700,fontSize:13}}>
         Replay {replay.reproduced?'MATCH':'MISMATCH'} · {replay.verdict} · as of {replay.asOf}.
         This is same-server deterministic replay; run the exported package through the independent Python SDK to compare.</p>}
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
