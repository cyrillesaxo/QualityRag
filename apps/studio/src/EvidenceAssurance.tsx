import React, {useState} from 'react';

type Verdict='ADMIT'|'REFUSE'|'INCONCLUSIVE';
type Review={state:'UNREVIEWED'|'ACCEPTED'|'DISPUTED';actor:string;reason:string};
type Witness={id:string;origin:string;source_ref:string;status:'SUPPORTS'|'CONTRADICTS'};
type Frame={label:string;verdict:Verdict;witnesses:Witness[];count:number;reasons:string[]};
type Case={id:string;name:string;requirement:string;min:number;frames:Frame[]};
const e=(id:string,origin:string,status:Witness['status']='SUPPORTS'):Witness=>
 ({id,origin,source_ref:'synthetic:'+id,status});
const cases:Case[]=[
 {id:'QR-001',name:'Three citations, one origin',requirement:'independent-approval',min:2,frames:[
  {label:'Initial evidence',verdict:'INCONCLUSIVE',count:1,reasons:['INSUFFICIENT_INDEPENDENT_EVIDENCE'],witnesses:[e('sop-pdf','sop'),e('sop-wiki','sop'),e('sop-email','sop')]},
  {label:'Independent witness added',verdict:'ADMIT',count:2,reasons:[],witnesses:[e('sop-pdf','sop'),e('sop-wiki','sop'),e('sop-email','sop'),e('approval','process-owner')]}]},
 {id:'QR-002',name:'Exception not checked',requirement:'exception',min:1,frames:[
  {label:'No exception witness',verdict:'INCONCLUSIVE',count:0,reasons:['INSUFFICIENT_INDEPENDENT_EVIDENCE'],witnesses:[e('general-policy','policy')]},
  {label:'Exception witness provided',verdict:'ADMIT',count:1,reasons:[],witnesses:[e('general-policy','policy'),e('exception','annex')]}]},
 {id:'QR-003',name:'Outdated policy',requirement:'current-policy',min:1,frames:[
  {label:'Stale policy',verdict:'INCONCLUSIVE',count:0,reasons:['STALE_EVIDENCE','INSUFFICIENT_INDEPENDENT_EVIDENCE'],witnesses:[e('old-policy','policy-2024')]},
  {label:'Fresh policy',verdict:'ADMIT',count:1,reasons:[],witnesses:[e('current-policy','policy-2026')]}]},
 {id:'QR-004',name:'Contradiction',requirement:'approval',min:1,frames:[
  {label:'Disputed evidence',verdict:'REFUSE',count:1,reasons:['CONTRADICTION'],witnesses:[e('approval','policy'),e('restriction','control','CONTRADICTS')]}]}
];
const green='#038112',muted='#53695d';
const block:React.CSSProperties={border:'1px solid #dce7dd',borderRadius:12,padding:16,background:'#fff'};
const badge=(v:Verdict):React.CSSProperties=>({display:'inline-block',padding:'4px 10px',borderRadius:20,fontSize:12,fontWeight:800,color:v==='ADMIT'?'#067219':v==='REFUSE'?'#a3322d':'#986308',background:v==='ADMIT'?'#e5f8e8':v==='REFUSE'?'#ffeae8':'#fff2d5'});
export function EvidenceAssurance(){
 const [selected,setSelected]=useState(0),[stage,setStage]=useState(0);
 const [reviews,setReviews]=useState<Record<string,Review>>({});
 const [actor,setActor]=useState(''),[reason,setReason]=useState(''),[message,setMessage]=useState('');
 const item=cases[selected],frame=item.frames[stage],review=reviews[item.id];
 const reviewed=Object.values(reviews).filter(r=>r.state!=='UNREVIEWED').length;
 function choose(index:number){setSelected(index);setStage(0);setActor(reviews[cases[index].id]?.actor||'');setReason(reviews[cases[index].id]?.reason||'');setMessage('')}
 function submit(state:Review['state']){
  if(state!=='UNREVIEWED'&&(!actor.trim()||!reason.trim())){setMessage('A reviewer role and rationale are required.');return}
  setReviews(prev=>({...prev,[item.id]:{state,actor:state==='UNREVIEWED'?'':actor.trim(),reason:state==='UNREVIEWED'?'':reason.trim()}}));
  setMessage('Local-only demo review recorded; unsigned and not persisted.');
 }
 function exportJson(){
  const payload={schema:'qualityrag.review-demo/v1',synthetic:true,caseId:item.id,requirement:item.requirement,
    minimumIndependentSources:item.min,evaluation:frame,review:reviews[item.id]||{state:'UNREVIEWED'},disclaimer:'Metadata only; unverified origins and no customer signature.'};
  const u=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=u;link.download=item.id.toLowerCase()+'-review.json';document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(u);
 }
 return <section className="panel" aria-label="Evidence Assurance preview" style={{borderTop:'4px solid '+green}}>
  <p style={{color:green,fontSize:12,fontWeight:800,letterSpacing:'.1em'}}>6. EVIDENCE ASSURANCE / CUSTOMER TELEMETRY</p>
  <h2 style={{fontSize:28}}>Don't convince me. Show me.</h2>
  <p>Inspect a declared requirement, source-origin evidence, and a deterministic verdict. Replay the changed inputs, then accept or dispute the finding.</p>
  <p className="notice">SYNTHETIC SDK-STYLE FIXTURES · NOT LIVE TELEMETRY. No source truth, legal authorization, or compliance is established.</p>
  <div className="line" style={{gap:12,marginBottom:16}}>
   <div style={block}><strong>{cases.length} cases</strong><div>Illustrative tests</div></div>
   <div style={block}><strong>3 initial INCONCLUSIVE</strong><div>Evidence gaps</div></div>
   <div style={block}><strong>1 initial REFUSE</strong><div>Contradiction</div></div>
   <div style={block}><strong>{reviewed}/{cases.length} reviewed</strong><div>Browser memory</div></div>
  </div>
  <div className="columns" style={{gridTemplateColumns:'minmax(220px,1fr) minmax(0,2.1fr)'}}>
   <div style={block}>{cases.map((c,i)=><button type="button" key={c.id} onClick={()=>choose(i)} aria-pressed={selected===i}
     style={{background:selected===i?'#e5f7e8':'#fff',color:'#133a20',border:'1px solid #cfe3d0',width:'100%',marginBottom:9,textAlign:'left'}}>
     <strong>{c.id}</strong><br/>{c.name}<br/><span style={badge(c.frames[0].verdict)}>{c.frames[0].verdict}</span></button>)}</div>
   <div style={block}>
    <h3>{item.name}</h3><p>PackSpec: {item.requirement} · required independent origins: {item.min}</p>
    <div className="line">{item.frames.map((s,i)=><button key={s.label} type="button" aria-pressed={stage===i} onClick={()=>setStage(i)}
      style={{background:stage===i?green:'#eff6f0',color:stage===i?'white':green}}>{s.label}</button>)}</div>
    <div style={{...block,background:'#f4faf5',marginTop:12}}>
      <span style={badge(frame.verdict)}>{frame.verdict}</span>
      <p>Counted independent origins: <strong>{frame.count}</strong> · {frame.reasons.join(', ')||'Declared checks met'}</p>
      <p style={{fontSize:12}}>Trace: request → {frame.witnesses.length} retrieved witnesses → PackSpec → {frame.verdict}</p>
    </div>
    <h4>Inspect source metadata</h4>{frame.witnesses.map(w=><div key={w.id} style={{borderBottom:'1px solid #dce7dd',padding:'8px 0',fontSize:13}}>
      <strong>{w.id}</strong> · origin <code>{w.origin}</code> · {w.status} · <code>{w.source_ref}</code>
    </div>)}
   </div>
  </div>
  <div className="columns" style={{marginTop:15}}>
   <div style={block}><h3>Customer challenge</h3><p>Customer review is distinct from engine admission.</p>
    <label>Reviewer role<input value={actor} onChange={e=>setActor(e.target.value)} placeholder="Policy owner"/></label>
    <label>Rationale<textarea value={reason} onChange={e=>setReason(e.target.value)} placeholder="Why is the finding valid or disputed?"/></label>
    <div className="line"><button onClick={()=>submit('ACCEPTED')}>Accept</button><button onClick={()=>submit('DISPUTED')}>Dispute</button><button onClick={()=>submit('UNREVIEWED')}>Clear</button></div>
    <p role="status">{message||'Status: '+(review?.state||'UNREVIEWED')}</p>
   </div>
   <div style={block}><h3>Inspectable receipt</h3><p>Review metadata, requirement and evidence, without raw document bodies. The export is not cryptographically signed.</p>
    <button onClick={exportJson}>Export review JSON</button><p><strong>Next integration:</strong> authenticated event ingestion, replay with pinned SDK and clock, tenant separation, reviewer authorization, and durable approval records.</p>
   </div>
  </div>
  <p style={{color:muted,fontSize:12}}>The Studio preview contains deterministic synthetic example outcomes; it does not call the Python SDK from the browser or verify source origins.</p>
 </section>;
}
