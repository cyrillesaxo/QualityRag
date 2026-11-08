import React,{useState} from 'react';

type Outcome={id:string;verdict:'ADMIT'|'REFUSE'|'INCONCLUSIVE';
 admissionStatus:string;at:string;sourceCount:number;policySha256:string;
 chainHash:string;meaningVerifiedByMachine:boolean;originalPublisherAuthenticated:boolean;
 independentOriginProven:boolean;result:{findings:{requirement_id:string;verdict:string;reasons:string[]}[]}};
type UseCheck={schema:'qualityrag.protected-decision-use/v1';
 permission:'PERMIT_SIGNED_ASSERTION_USE';decisionId:string;requestId:string;
 answerSha256:string;checkedAt:string;receiptId:string;scope:string;
 answerSemanticsVerified:false;globalEnforcement:false};
type Props={token:string;serviceId:string;environment:string;enabled:boolean};

export function ProtectedAdmission({token,serviceId,environment,enabled}:Props){
 const [json,setJson]=useState('');
 const [outcome,setOutcome]=useState<Outcome|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [answer,setAnswer]=useState('');
 const [useReceipt,setUseReceipt]=useState<UseCheck|null>(null);
 const [useError,setUseError]=useState('');
 if(!enabled)return <p style={{fontSize:13,color:'#81571f'}}>
   Signed reviewer admission is not configured for this service. Generic unreviewed
   evidence remains blocked while this protection is active.
 </p>;
 async function submit(){
   setBusy(true);setError('');setOutcome(null);
   setUseReceipt(null);setUseError('');setAnswer('');
   try{
     if(!token)throw Error('A signed registry identity is required.');
     if(json.length>60_000)throw Error('Signed request is too large.');
     let payload;
     try{payload=JSON.parse(json)}
     catch{throw Error('Paste the JSON built from two offline signed attestations.')}
     if(!payload||typeof payload!=='object'||Array.isArray(payload)||
       Object.keys(payload).length!==6||
       !['serviceId','environment','requestId','traceId','custody','meaning'].every(
         key=>Object.hasOwn(payload,key)))
       throw Error('Unexpected protected request format.');
     if(payload.serviceId!==serviceId||payload.environment!==environment)
       throw Error('Signed request service/environment must match the selected Studio scope.');
     const response=await fetch('/v1/evidence/protected-admit',{
       method:'POST',cache:'no-store',redirect:'error',
       headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
       body:JSON.stringify(payload)
     });
     const received=await response.json();
     if(!response.ok)throw Error(String(received.error||'Protected review was refused'));
     setOutcome(received);
     setJson(''); // do not keep a signed replayable request on screen
   }catch(e){setError(String(e))}
   finally{setBusy(false)}
 }
 async function exportReceipt(){
   if(!outcome||!token)return;
   setBusy(true);setError('');
   try{
     const response=await fetch('/v1/evidence/protected-decisions/'+outcome.id+'/export',{
       headers:{Authorization:'Bearer '+token},redirect:'error',cache:'no-store'
     });
     const packet=await response.json();
     if(!response.ok)throw Error(String(packet.error||'Receipt export forbidden'));
     if(packet.schema!=='qualityrag.protected-drive-decision-replay/v1')
       throw Error('Unsupported protected receipt schema.');
     const href=URL.createObjectURL(new Blob([JSON.stringify(packet,null,2)],
       {type:'application/json'}));
     const link=document.createElement('a');link.href=href;
     link.download='qualityrag-protected-human-review-'+outcome.id+'.json';
     document.body.append(link);link.click();link.remove();
     URL.revokeObjectURL(href);
   }catch(e){setError(String(e))}
   finally{setBusy(false)}
 }
 async function checkUse(){
   if(!outcome||outcome.verdict!=='ADMIT'||!token)return;
   setBusy(true);setUseError('');setUseReceipt(null);
   try{
     if(!answer.trim()||new TextEncoder().encode(answer).length>128000)
       throw Error('Enter a short answer draft to compute its SHA-256 digest locally.');
     const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(answer));
     const answerSha256=Array.from(new Uint8Array(bytes))
       .map(b=>b.toString(16).padStart(2,'0')).join('');
     const requestId='use-'+crypto.randomUUID();
     const response=await fetch('/v1/evidence/protected-decisions/'+outcome.id+'/use-check',{
       method:'POST',cache:'no-store',redirect:'error',
       headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
       body:JSON.stringify({requestId,answerSha256})
     });
     const receipt=await response.json();
     if(!response.ok)throw Error(String(receipt.error||'Current evidence use is not permitted'));
     if(receipt.schema!=='qualityrag.protected-decision-use/v1'||
        receipt.permission!=='PERMIT_SIGNED_ASSERTION_USE'||
        receipt.decisionId!==outcome.id||receipt.requestId!==requestId||
        receipt.answerSha256!==answerSha256||
        receipt.globalEnforcement!==false||
        receipt.answerSemanticsVerified!==false)
       throw Error('Registry did not return a valid request-specific permit.');
     setUseReceipt(receipt);
   }catch(e){setUseError(String(e))}
   finally{setBusy(false)}
 }
 return <section aria-label="Customer-signed protected review" style={{
   border:'1px solid #cddfcf',borderRadius:13,padding:16,margin:'14px 0',background:'#f7fbf7'}}>
   <h3 style={{marginTop:0}}>Customer-signed protected evidence review</h3>
   <p>Two separately trusted role keys—a custodian and a semantic reviewer—must
     sign the same source-and-policy claim <strong>offline</strong>. The registry
     rechecks current Google bytes and your owner-controlled source index before
     recording a verdict. Do not paste private keys, customer document text or secrets here.</p>
   <p><a href="https://github.com/cyrillesaxo/QualityRag/blob/feat/studio-evidence-assurance-telemetry-20261108/docs/PROTECTED-HUMAN-REVIEW-ADMISSION.md"
       target="_blank" rel="noreferrer">Offline signing and independent verification guide</a></p>
   <label>Reviewed request JSON (two signed attestations, no raw documents)
     <textarea value={json} rows={5} maxLength={60000}
       onChange={e=>setJson(e.target.value)}
       placeholder='Paste the signed request generated offline with prepare_protected_drive_review.py'
       style={{width:'100%',fontFamily:'monospace',fontSize:12}}/>
   </label>
   <div className="line">
     <button type="button" disabled={busy||!json.trim()||!token}
       onClick={submit}>Submit separately signed review</button>
   </div>
   {outcome&&<div role="status" style={{marginTop:12,padding:12,
     borderRadius:10,background:'#fff',border:'1px solid #d3e3d5'}}>
     <strong>Recorded decision: {outcome.verdict}</strong>
     <p>{outcome.admissionStatus} · {outcome.at}</p>
     <p>Exact Google source bytes: checked at evaluation ·
       Source count: {outcome.sourceCount} ·
       PackSpec SHA-256: <code>{outcome.policySha256.slice(0,18)}…</code></p>
     <ul>{outcome.result.findings.map(f=><li key={f.requirement_id}>
       {f.requirement_id}: {f.verdict} ({f.reasons.join(', ')||'threshold satisfied'})
     </li>)}</ul>
     <p><strong>Proof boundaries:</strong> meaning verified by machine:
       {String(outcome.meaningVerifiedByMachine)}; real publisher authenticated:
       {String(outcome.originalPublisherAuthenticated)};
       independent origins proven: {String(outcome.independentOriginProven)}.
       This is a customer-signed human assertion, not objective source truth,
       a production authorization certificate, or externally anchored audit.</p>
     <button type="button" disabled={busy} onClick={exportReceipt}>
       Export independently replayable signed receipt
     </button>
     {outcome.verdict==='ADMIT'&&<div style={{marginTop:15,padding:12,
       borderRadius:8,border:'1px solid #dedac7'}}>
       <strong>Check whether this signed evidence may still be used</strong>
       <p style={{fontSize:12}}>
         A recorded ADMIT is historical, not a perpetual authorization.
         The registry rechecks the signatures, approved PackSpec, current
         Google bytes and your source exclusions on each use. The browser sends
         only a SHA-256 digest of the drafted answer—not its text.
       </p>
       <label>Proposed answer (kept in this browser, not uploaded)
         <textarea rows={3} value={answer} onChange={e=>{
           setAnswer(e.target.value);setUseReceipt(null);setUseError('');
         }} style={{width:'100%'}} maxLength={64000}/>
       </label>
       <button type="button" onClick={checkUse} disabled={busy||!answer.trim()}>
         Check live evidence-use permission
       </button>
       {useReceipt&&<p role="status">
         <strong>PERMITTED for this request and answer digest only.</strong>
         {' '}Checked at {useReceipt.checkedAt}. Local receipt:
         {' '}<code>{useReceipt.receiptId}</code>.
         The answer's meaning was not checked and this is not a permit for
         other applications or later requests.
       </p>}
       {useError&&<p role="alert" style={{color:'#a83224'}}>
         No evidence-use permission: {useError}
       </p>}
     </div>}
   </div>}
   {error&&<p role="alert" style={{color:'#a83224'}}>{error}</p>}
 </section>;
}
