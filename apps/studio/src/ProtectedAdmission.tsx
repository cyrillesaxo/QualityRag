import React,{useState} from 'react';

type Outcome={id:string;verdict:'ADMIT'|'REFUSE'|'INCONCLUSIVE';
 admissionStatus:string;at:string;sourceCount:number;policySha256:string;
 chainHash:string;meaningVerifiedByMachine:boolean;originalPublisherAuthenticated:boolean;
 independentOriginProven:boolean;result:{findings:{requirement_id:string;verdict:string;reasons:string[]}[]}};
type UseCheck={schema:'qualityrag.protected-decision-use/v1';
 permission:'PERMIT_SIGNED_ASSERTION_USE';decisionId:string;requestId:string;
 answerSha256:string;checkedAt:string;receiptId:string;scope:string;
 answerSemanticsVerified:false;globalEnforcement:false};
type Grounded={schema:'qualityrag.source-grounded-extract/v1';
 answer:string;delivery:'SERVER_GENERATED_EXTRACT_ONLY';
 coverage:{requiredPolicyObligations:number;humanSignedSupports:number;
   allSignedAnchorsIncluded:true;fullDocumentExaminedForExceptions:false};
 assertions:{modelGeneratedParaphrase:false;freeFormAnswerEntailmentVerified:false};
 receipt:{answerSha256:string;deliveryMode:'SOURCE_GROUNDED_EXTRACT'}};
type Sufficiency={
 schema:'qualityrag.constraint-signal-scan/v1';
 status:'UNREVIEWED_LEXICAL_SIGNALS'|'NO_UNREVIEWED_LEXICAL_SIGNALS';
 candidateCount:number;reviewedSignalCount:number;
 sourcesScanned:number;linesScanned:number;candidatesTruncated:boolean;
 checkedAt:string;
 candidates:{sourceId:string;lineNumber:number;category:string;
   reviewStatus:string}[];
 scope:'LIVE_VERIFIED_SIGNED_SOURCE_FILES_ONLY';
 sourceTextIncluded:false;documentWideSemanticCompletenessVerified:false;
 releasePermittedByThisPreview:false;
};
type RelationPreview={
 schema:'qualityrag.cross-document-relation-candidates/v1';
 candidateCount:number;bothSignedConflicts:number;
 sourcesScanned:number;linesScanned:number;
 findingsTruncated:boolean;checkedAt:string;
 findings:Array<{category:string;left:{sourceId:string;lineNumber:number;
 signedSupportingWitness:boolean};right:{sourceId:string;lineNumber:number;
 signedSupportingWitness:boolean};reviewState:string}>;
 scope:'LIVE_VERIFIED_INCLUDED_SELECTED_FOLDER_TEXT_FILES';
 sourceTextIncluded:false;actorNamesIncluded:false;
 semanticCompletenessVerified:false;
 releasePermittedByThisPreview:false;
};
type Props={token:string;serviceId:string;environment:string;enabled:boolean};

export function ProtectedAdmission({token,serviceId,environment,enabled}:Props){
 const [json,setJson]=useState('');
 const [outcome,setOutcome]=useState<Outcome|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [answer,setAnswer]=useState('');
 const [useReceipt,setUseReceipt]=useState<UseCheck|null>(null);
 const [useError,setUseError]=useState('');
 const [sendDraftToGateway,setSendDraftToGateway]=useState(false);
 const [delivered,setDelivered]=useState(false);
 const [deliveryError,setDeliveryError]=useState('');
 const [grounded,setGrounded]=useState<Grounded|null>(null);
 const [groundingError,setGroundingError]=useState('');
 const [sufficiency,setSufficiency]=useState<Sufficiency|null>(null);
 const [sufficiencyError,setSufficiencyError]=useState('');
 const [relationPreview,setRelationPreview]=useState<RelationPreview|null>(null);
 const [relationError,setRelationError]=useState('');
 const [revocationReason,setRevocationReason]=useState('OWNER_WITHDRAWN');
 const [revoked,setRevoked]=useState(false);
 const [revocationResult,setRevocationResult]=useState('');
 if(!enabled)return <p style={{fontSize:13,color:'#81571f'}}>
   Signed reviewer admission is not configured for this service. Generic unreviewed
   evidence remains blocked while this protection is active.
 </p>;
 async function submit(){
   setBusy(true);setError('');setOutcome(null);
   setUseReceipt(null);setUseError('');setAnswer('');
   setDelivered(false);setDeliveryError('');setSendDraftToGateway(false);
   setGrounded(null);setGroundingError('');
   setSufficiency(null);setSufficiencyError('');
   setRelationPreview(null);setRelationError('');
   setRevoked(false);setRevocationResult('');
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
 async function revokeDecision(){
   if(!outcome||outcome.verdict!=='ADMIT'||revoked||!token)return;
   setBusy(true);setError('');setRevocationResult('');
   try{
     const response=await fetch(
       '/v1/evidence/protected-decisions/'+outcome.id+'/revoke',{
         method:'POST',cache:'no-store',redirect:'error',
         headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
         body:JSON.stringify({reason:revocationReason})
       });
     const result=await response.json();
     if(!response.ok)throw Error(String(result.error||'Revocation not authorized'));
     if(result.schema!=='qualityrag.protected-decision-revocation/v1'||
        result.decisionId!==outcome.id||result.status!=='REVOKED')
       throw Error('Unexpected revocation response');
     setRevoked(true);setUseReceipt(null);setUseError('');
     setDelivered(false);setDeliveryError('');
     setGrounded(null);setGroundingError('');
     setRevocationResult('Approval withdrawn at '+result.revokedAt+
       '. Historical audit remains, but future evidence-use checks are blocked.');
   }catch(e){setError(String(e))}
   finally{setBusy(false)}
 }
 async function checkUse(){
   if(!outcome||outcome.verdict!=='ADMIT'||revoked||!token)return;
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
 async function deliverViaGateway(){
   if(!outcome||outcome.verdict!=='ADMIT'||revoked||!token||!sendDraftToGateway)return;
   setBusy(true);setDeliveryError('');setDelivered(false);setUseReceipt(null);
   try{
     if(!answer.trim()||new TextEncoder().encode(answer).length>16384||
        answer.includes('\0'))
       throw Error('Gateway pilot limits the draft to 16 KiB without NUL bytes.');
     const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(answer));
     const answerSha256=Array.from(new Uint8Array(digest))
       .map(b=>b.toString(16).padStart(2,'0')).join('');
     const requestId='delivery-'+crypto.randomUUID();
     const response=await fetch(
       '/v1/evidence/protected-decisions/'+outcome.id+'/deliver',{
         method:'POST',cache:'no-store',redirect:'error',
         headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
         body:JSON.stringify({requestId,answer})
       });
     const received=await response.json();
     if(!response.ok)throw Error(String(received.error||'Gateway denied delivery'));
     const receipt=received.receipt;
     if(received.schema!=='qualityrag.protected-answer-delivery/v1'||
        received.answer!==answer||received.delivery!=='BUFFERED_SINGLE_RESPONSE'||
        received.answerSemanticsVerified!==false||
        received.globalEnforcement!==false||
        receipt?.schema!=='qualityrag.protected-decision-use/v1'||
        receipt.permission!=='PERMIT_SIGNED_ASSERTION_USE'||
        receipt.decisionId!==outcome.id||receipt.requestId!==requestId||
        receipt.answerSha256!==answerSha256||receipt.globalEnforcement!==false||
        receipt.answerSemanticsVerified!==false)
       throw Error('Gateway response did not match the exact draft and request.');
     setUseReceipt(receipt);
     setDelivered(true);
   }catch(e){setDeliveryError(String(e))}
   finally{setBusy(false)}
 }
 async function checkSufficiency(){
   if(!outcome||outcome.verdict!=='ADMIT'||revoked||!token)return;
   setBusy(true);setSufficiency(null);setSufficiencyError('');
   try{
     const response=await fetch(
       '/v1/evidence/protected-decisions/'+outcome.id+'/sufficiency-check',{
         method:'POST',cache:'no-store',redirect:'error',
         headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
         body:JSON.stringify({requestId:'signals-'+crypto.randomUUID()})
       });
     const result=await response.json();
     if(!response.ok)throw Error(String(result.error||'Constraint scan unavailable'));
     if(result.schema!=='qualityrag.constraint-signal-scan/v1'||
       !Number.isSafeInteger(result.candidateCount)||
       !Array.isArray(result.candidates)||
       result.sourceTextIncluded!==false||
       result.scope!=='LIVE_VERIFIED_SIGNED_SOURCE_FILES_ONLY'||
       result.documentWideSemanticCompletenessVerified!==false||
       result.releasePermittedByThisPreview!==false)
       throw Error('Unsupported signal-scan scope or assurance claims');
     setSufficiency(result);
   }catch(e){setSufficiencyError(String(e))}
   finally{setBusy(false)}
 }
 async function checkRelations(){
   if(!outcome||outcome.verdict!=='ADMIT'||revoked||!token)return;
   setBusy(true);setRelationError('');setRelationPreview(null);
   try{
     const response=await fetch(
       '/v1/evidence/protected-decisions/'+outcome.id+'/relation-check',{
         method:'POST',cache:'no-store',redirect:'error',
         headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
         body:JSON.stringify({requestId:'relations-'+crypto.randomUUID()})
       });
     const result=await response.json();
     if(!response.ok)throw Error(String(result.error||'Relation scan refused'));
     if(result.schema!=='qualityrag.cross-document-relation-candidates/v1'||
        !Number.isSafeInteger(result.candidateCount)||
        !Array.isArray(result.findings)||
        result.scope!=='LIVE_VERIFIED_INCLUDED_SELECTED_FOLDER_TEXT_FILES'||
        result.sourceTextIncluded!==false||
        result.actorNamesIncluded!==false||
        result.semanticCompletenessVerified!==false||
        result.releasePermittedByThisPreview!==false)
       throw Error('Unexpected relation scan assurance scope or fields');
     setRelationPreview(result);
   }catch(e){setRelationError(String(e))}
   finally{setBusy(false)}
 }
 async function extractGrounded(){
   if(!outcome||outcome.verdict!=='ADMIT'||revoked||!token)return;
   setBusy(true);setGroundingError('');setGrounded(null);
   try{
     const requestId='extract-'+crypto.randomUUID();
     const response=await fetch(
       '/v1/evidence/protected-decisions/'+outcome.id+'/grounded-deliver',{
         method:'POST',cache:'no-store',redirect:'error',
         headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
         body:JSON.stringify({requestId})
       });
     const result=await response.json();
     if(!response.ok)throw Error(String(result.error||'Source-grounded extraction refused'));
     const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(
       String(result.answer||'')));
     const answerSha256=Array.from(new Uint8Array(bytes))
       .map(b=>b.toString(16).padStart(2,'0')).join('');
     if(result.schema!=='qualityrag.source-grounded-extract/v1'||
       result.delivery!=='SERVER_GENERATED_EXTRACT_ONLY'||
       result.coverage?.allSignedAnchorsIncluded!==true||
       result.coverage.fullDocumentExaminedForExceptions!==false||
       result.assertions?.modelGeneratedParaphrase!==false||
       result.assertions?.freeFormAnswerEntailmentVerified!==false||
       result.receipt?.deliveryMode!=='SOURCE_GROUNDED_EXTRACT'||
       result.receipt.answerSha256!==answerSha256)
       throw Error('Source-grounded response has inconsistent coverage or digest.');
     setGrounded(result);
   }catch(e){setGroundingError(String(e))}
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
       borderRadius:8,border:'1px solid #b7d8c4',background:'#f3faf6'}}>
       <strong>Show exact source-grounded clauses</strong>
       <p style={{fontSize:12}}>
         QualityRAG rechecks the current approved source and PackSpec, includes
         every signed SUPPORTS anchor for the required obligations, and preserves
         the exact source wording. The adjacent lines are marked as unreviewed
         context so nearby exceptions remain visible.
         <strong> This does not search the entire document for hidden exceptions
         or prove paraphrase entailment.</strong> Excerpts are returned only
         to the authenticated owner and are not written into the evidence ledger.
       </p>
       <button type="button" disabled={busy||revoked}
         onClick={checkSufficiency}>
         Scan referenced files for distant constraints
       </button>
       {sufficiency&&<div role="status" style={{marginTop:10}}>
         <p>Snapshot {sufficiency.checkedAt}: checked {sufficiency.linesScanned}
           {' '}lines across {sufficiency.sourcesScanned} signed source files.
           Unreviewed lexical signals:
           {' '}<strong>{sufficiency.candidateCount}</strong>.
         </p>
         {sufficiency.candidateCount>0&&<p>
           Extraction is blocked until these candidate source lines
           receive independent human review and a new signed decision.
           Candidates are warnings, not proven contradictions.
         </p>}
         {sufficiency.candidates.length>0&&<ul>
           {sufficiency.candidates.map((c,i)=><li key={i}>
             {c.category}: <code>{c.sourceId}</code>, line {c.lineNumber}
             {' '}— not signed as a supporting witness
           </li>)}
         </ul>}
         {sufficiency.candidatesTruncated&&<p>
           More findings exist than are shown; the listing is incomplete.
         </p>}
         <p style={{fontSize:12}}>Only referenced, live-verified files were
           scanned using bounded language patterns. No document text is
           copied into this report. This preview is not an authorization
           for a later request; release checks the live source again.
           A clean scan does not prove that other files lack exceptions,
           or that the semantic relationships in this document are complete.</p>
       </div>}
       {sufficiencyError&&<p role="alert" style={{color:'#a83224'}}>
         Constraint scan could not be completed: {sufficiencyError}
       </p>}
       <div style={{marginTop:12,padding:12,
         border:'1px solid #bfcbdc',borderRadius:8}}>
         <strong>Cross-document relationship challenge (research)</strong>
         <p style={{fontSize:12}}>Verify all included text files in your
           selected Drive folder and look for explicit payer/payee reversals
           and opposite payment obligations. The result lists source
           locations, not customer names or document passages. Two signed
           contradictory statements remain a conflict to investigate.</p>
         <button type="button" disabled={busy||revoked}
           onClick={checkRelations}>
           Check cross-document payer/payee relationships
         </button>
         {relationPreview&&<div role="status" style={{marginTop:9}}>
           <p>Snapshot {relationPreview.checkedAt}:
             {' '}{relationPreview.sourcesScanned} included files inspected,
             {' '}{relationPreview.linesScanned} lines.
             Possible relationship conflicts:
             {' '}<strong>{relationPreview.candidateCount}</strong>.
             Both signed, but not adjudicated:
             {' '}{relationPreview.bothSignedConflicts}.
           </p>
           {relationPreview.candidateCount>0&&<p>
             Grounded extraction is blocked until the customer resolves the
             source authority, date, scope, or explicit payer/payee mapping.
             A second signature alone does not resolve inconsistency.
           </p>}
           {relationPreview.findings.length>0&&<ul>
             {relationPreview.findings.map((f,i)=><li key={i}>
               <strong>{f.category}</strong>:
               {' '}<code>{f.left.sourceId}</code> line {f.left.lineNumber}
               {' '}versus <code>{f.right.sourceId}</code> line {f.right.lineNumber}
               {' '}(signed witnesses:
               {' '}{f.left.signedSupportingWitness?'yes':'no'}/
               {f.right.signedSupportingWitness?'yes':'no'})
             </li>)}
           </ul>}
           {relationPreview.findingsTruncated&&<p>
             Additional unresolved pairs were counted but not displayed.
           </p>}
           <p style={{fontSize:12}}>This is a bounded English-language
             surface grammar, not an interpretation of every document.
             Excluded sources, implicit relationships, time-dependent
             exceptions and unsupported paraphrases remain unverified.
             A clean result is not an authorization or completeness proof.</p>
         </div>}
         {relationError&&<p role="alert" style={{color:'#a83224'}}>
           Cross-document review unavailable: {relationError}
         </p>}
       </div>
       <button type="button" disabled={busy||revoked} onClick={extractGrounded}>
         Generate exact-source extract
       </button>
       {grounded&&<div role="status" style={{marginTop:8}}>
         <p><strong>{grounded.coverage.humanSignedSupports} signed anchors</strong>
           {' '}cover {grounded.coverage.requiredPolicyObligations} required
           obligations in the selected reviewed source scope.
           Document-wide exception completeness: <strong>not established</strong>.
         </p>
         <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',
           fontSize:12,maxHeight:400,overflow:'auto'}}>{grounded.answer}</pre>
       </div>}
       {groundingError&&<p role="alert" style={{color:'#a83224'}}>
         Extract denied: {groundingError}
       </p>}
     </div>}
     {outcome.verdict==='ADMIT'&&<div style={{marginTop:15,padding:12,
       borderRadius:8,border:'1px solid #e6d6bd',background:'#fffaf5'}}>
       <strong>Withdraw this signed approval</strong>
       <p style={{fontSize:12}}>An authorized <code>evidence.reviewer</code> and
         <code> drive.manager</code> acting as the same source owner may permanently
         withdraw this decision. The source can remain searchable. Withdrawal is
         recorded; older independent replay still reproduces what happened then,
         but future use is blocked.</p>
       <label>Reason for withdrawal
         <select disabled={busy||revoked} value={revocationReason}
           onChange={e=>setRevocationReason(e.target.value)}>
           <option value="OWNER_WITHDRAWN">Owner withdrew approval</option>
           <option value="REVIEW_DISPUTED">Meaning review disputed</option>
           <option value="CUSTODY_DISPUTED">Source custody disputed</option>
         </select>
       </label>
       <button type="button" disabled={busy||revoked} onClick={revokeDecision}>
         {revoked?'Approval withdrawn':'Revoke signed approval (owner reviewer)'}
       </button>
       {revocationResult&&<p role="status">{revocationResult}</p>}
     </div>}
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
           setDelivered(false);setDeliveryError('');
         }} style={{width:'100%'}} maxLength={64000}/>
       </label>
       <button type="button" onClick={checkUse} disabled={busy||revoked||!answer.trim()}>
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
       <div style={{marginTop:14,padding:12,border:'1px solid #dfd7b7',
         borderRadius:8,background:'#fffaf0'}}>
         <strong>Controlled response gateway — explicit plaintext opt-in</strong>
         <p style={{fontSize:12}}>The stronger gateway buffers your answer draft
           inside this registry and returns it only if all current evidence checks
           succeed. <strong>Unlike digest-only checking, this sends the full
           draft to the registry.</strong> Use only in a trusted customer-operated
           environment. No answer text is intentionally written to the ledger.
           The answer's factual meaning is still not verified.</p>
         <label style={{display:'block',fontSize:12}}>
           <input type="checkbox" checked={sendDraftToGateway}
             onChange={e=>{setSendDraftToGateway(e.target.checked);
               setDelivered(false);setDeliveryError('');}}/>
           I authorize sending this draft to the configured registry for
           buffered release in this demonstration
         </label>
         <button type="button" disabled={busy||revoked||!sendDraftToGateway||
           !answer.trim()||new TextEncoder().encode(answer).length>16384}
           onClick={deliverViaGateway}>
           Release through customer-operated gateway
         </button>
         {delivered&&<p role="status"><strong>Gateway released this exact draft.</strong>
           {' '}The registry checked current source permissions and recorded
           the request-specific permit. This is not proof of answer correctness.</p>}
         {deliveryError&&<p role="alert" style={{color:'#a83224'}}>
           Gateway did not release the answer: {deliveryError}
         </p>}
       </div>
     </div>}
   </div>}
   {error&&<p role="alert" style={{color:'#a83224'}}>{error}</p>}
 </section>;
}
