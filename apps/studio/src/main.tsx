import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Service={id:string;displayName:string};
type Policy={policy:{id:string;version:string;requirements:unknown[]};status:string;sha256:string};
type Binding={serviceId:string;environment:string;policyId:string;version:string};
type SignedPromotion={serviceId:string;environment:string;sequence:number;keyId:string;status:string;irSha256:string};
type SignedBinding={serviceId:string;environment:string;sequence:number;irSha256:string};
const starter={id:'eligibility',version:'1.0.0',requirements:[{id:'governing-rule',min_independent_sources:2,max_age_seconds:86400}]};
function Studio(){
 const [token,setToken]=useState(''),[state,setState]=useState<{services:Service[];policies:Policy[];bindings:Binding[];signedPromotions:SignedPromotion[];signedBindings:SignedBinding[]}>({services:[],policies:[],bindings:[],signedPromotions:[],signedBindings:[]});
 const [serviceId,setServiceId]=useState('claims-api'),[name,setName]=useState('Claims API'),[environment,setEnvironment]=useState('dev');
 const [policyId,setPolicyId]=useState('eligibility'),[version,setVersion]=useState('1.0.0'),[editor,setEditor]=useState(JSON.stringify(starter,null,2)),[message,setMessage]=useState('');
 const [signedBundle,setSignedBundle]=useState('');
 const [gardenToken,setGardenToken]=useState('');
 const [gardenConnected,setGardenConnected]=useState(false);
 const [gardenBusy,setGardenBusy]=useState(false);
 const [gardenStatus,setGardenStatus]=useState('Not connected to Garden engine');
 const [gardenBranches,setGardenBranches]=useState<Array<{id:string;statement:string;assessment:string;active_research:boolean;admission:string}>>([]);
 const [gardenEvents,setGardenEvents]=useState<Array<{id:string;branch_id:string;assessment:string;reason:string;at:string}>>([]);
 const [gardenRelations,setGardenRelations]=useState<Array<{from:string;to:string;relation:string}>>([]);
 const [gardenDraft,setGardenDraft]=useState('');
 const [gardenReceipt,setGardenReceipt]=useState<{status:string;external_probe_count:number;qualityrag_admission:string;ledger_persisted?:boolean;ledger_reason?:string;investigation?:{experiment?:{results?:unknown[]}}}|null>(null);
 async function gardenRequest(path:string,data?:unknown){
  const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:{
   'Authorization':'Bearer '+gardenToken,'Content-Type':'application/json'
  },body:data===undefined?undefined:JSON.stringify(data)});
  let result:Record<string,unknown>;
  try{result=await response.json() as Record<string,unknown>}
  catch{throw new Error('Garden engine unavailable or invalid response')}
  if(!response.ok)throw new Error(String(result.error||'Garden engine request failed'));
  return result;
 }
 async function connectGarden(){
  setGardenBusy(true);setGardenConnected(false);setGardenReceipt(null);
  try {
   const status=await gardenRequest('/garden/status');
   if(status.schema!=='rct.garden-engine-status/v0.1'||status.connected!==true||
      status.ledger_integrity!=='CONSISTENT')throw new Error('Garden engine did not verify its ledger');
   const projection=await gardenRequest('/garden/projection');
   if(projection.schema!=='rct.semantic-gardener-projection/v0.1'||
      projection.ledger_integrity!=='CONSISTENT'||!Array.isArray(projection.branches)||
      !Array.isArray(projection.events)||!Array.isArray(projection.relations)){
    throw new Error('Garden engine returned incompatible research lineage');
   }
   setGardenBranches(projection.branches as typeof gardenBranches);
   setGardenEvents(projection.events as typeof gardenEvents);
   setGardenRelations(projection.relations as typeof gardenRelations);
   setGardenConnected(true);
   setGardenStatus('Connected: bounded Garden engine and verified research ledger ('+
      (projection.branches as unknown[]).length+' branches)');
  } catch(e){
   setGardenBranches([]);setGardenEvents([]);setGardenRelations([]);
   setGardenConnected(false);setGardenStatus(String(e));
  }finally{setGardenBusy(false)}
 }
 async function investigateGarden(){
  if(!gardenConnected)return;
  setGardenBusy(true);setGardenReceipt(null);
  try{
   if(gardenDraft.length>100000)throw new Error('Experiment payload too large');
   const data=JSON.parse(gardenDraft) as unknown;
   const result=await gardenRequest('/garden/investigate',data);
   if(result.schema!=='rct.garden-controller/v0.1'||
      result.qualityrag_admission!=='INCONCLUSIVE'||
      result.promotion_authorized!==false)throw new Error('Unrecognized or unsafe engine result');
   setGardenReceipt(result as typeof gardenReceipt);
   if(result.ledger_persisted===true){
    const latest=await gardenRequest('/garden/projection');
    if(latest.schema!=='rct.semantic-gardener-projection/v0.1'||
       latest.ledger_integrity!=='CONSISTENT'||
       !Array.isArray(latest.branches)||!Array.isArray(latest.events)||
       !Array.isArray(latest.relations))throw new Error('Research ledger refresh failed after execution');
    setGardenBranches(latest.branches as typeof gardenBranches);
    setGardenEvents(latest.events as typeof gardenEvents);
    setGardenRelations(latest.relations as typeof gardenRelations);
   }
   setGardenStatus('Engine executed: '+String(result.status)+
     '. Research only; '+(result.ledger_persisted?'ledger updated.':'not persisted.'));
  }catch(e){setGardenStatus('Garden run failed: '+String(e))}
  finally{setGardenBusy(false)}
 }
 const [semanticToken,setSemanticToken]=useState('');
 const [semanticStatus,setSemanticStatus]=useState('Not connected');
 const [semanticNamespace,setSemanticNamespace]=useState('local');
 const [semanticDirectory,setSemanticDirectory]=useState('');
 const [semanticTerm,setSemanticTerm]=useState('Cyrille');
 const [semanticRunning,setSemanticRunning]=useState(false);
 const [semanticCoverage,setSemanticCoverage]=useState<Record<string,number>|null>(null);
 type SemanticHit={source_id:string;revision:string;format:string;anchor:{kind:string;row_number?:number;pointer?:string;start_ms?:number;end_ms?:number;page_number?:number;paragraph_number?:number;line_number?:number};field:string;matched_text:string};
 const [semanticHits,setSemanticHits]=useState<SemanticHit[]>([]);
 const [semanticTruncated,setSemanticTruncated]=useState(false);
 const [visualReference,setVisualReference]=useState('');
 type VisualResult={source_id:string;format:string;distance:number;revision:string;identity_status:string;anchor:{kind:string;timestamp_ms?:number}};
 const [visualResults,setVisualResults]=useState<VisualResult[]>([]);
 const [visualStatus,setVisualStatus]=useState('');
 const [sceneReady,setSceneReady]=useState(false);
 const [scenePrompt,setScenePrompt]=useState('someone presenting in a conference room');
 const [sceneStatus,setSceneStatus]=useState('');
 type SceneHit={source_id:string;revision:string;anchor:{kind:string;timestamp_ms?:number};similarity:number;match_type:string};
 const [sceneHits,setSceneHits]=useState<SceneHit[]>([]);
 async function sceneIndex(){
  setSemanticRunning(true);
  try {
   const r=await semanticRequest('/semantic/scenes/index',{});
   setSceneStatus('Encoded '+r.indexed_sources+' visual sources; '+r.skipped_sources+' skipped; '+r.failed_sources+' failed.'+(r.truncated?' Index truncated.':''));
  }catch(e){setSceneStatus(String(e))}finally{setSemanticRunning(false)}
 }
 async function sceneFind(){
  setSemanticRunning(true);
  try {
   const r=await semanticRequest('/semantic/scenes/find',{prompt:scenePrompt});
   setSceneHits(r.results);
   setSceneStatus(r.results.length+' model-ranked scene candidates (uncalibrated; not verified facts).'+(r.truncated?' Results truncated.':''));
  }catch(e){setSceneStatus(String(e));setSceneHits([])}finally{setSemanticRunning(false)}
 }

 async function visualFind(){
  setSemanticRunning(true);
  try {
   const r=await semanticRequest('/semantic/visual-similar',
      {reference_source_id:visualReference});
   setVisualResults(r.results);
   setVisualStatus(r.results.length+' whole-frame appearance candidates. No person identity verification.');
  } catch(e){setVisualStatus(String(e));setVisualResults([])}
  finally{setSemanticRunning(false)}
 }

 const semanticRequest=async(path:string,data?:unknown)=>{
  const response=await fetch(path,{method:data===undefined?'GET':'POST',
   headers:{'Authorization':'Bearer '+semanticToken,'Content-Type':'application/json'},
   body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok)throw new Error(result.error||'Semantic workbench unavailable');
  return result;
 };
 async function semanticConnect(){
  setSemanticRunning(true);try{
   const status=await semanticRequest('/semantic/status');
   setSemanticNamespace(status.namespace);setSemanticDirectory(status.directory);setSceneReady(Boolean(status.scene_model_ready));
   setSemanticStatus('Connected: local directory '+status.directory+' (CSV, JSON, VTT, PDF, DOCX, HTML, TXT)');
  }catch(e){setSemanticStatus(String(e))}finally{setSemanticRunning(false)}
 }
 async function semanticIndex(){
  setSemanticRunning(true);try{
   const r=await semanticRequest('/semantic/index',{});
   setSemanticCoverage(r.coverage);
   setSemanticStatus('Index complete'+(r.truncated?' — file limit reached':'')+
    '. Unsupported, failed and denied files are excluded.');
  }catch(e){setSemanticStatus(String(e))}finally{setSemanticRunning(false)}
 }
 async function semanticFind(){
  setSemanticRunning(true);try{
   const escaped=semanticTerm.replace(/'/g,"''");
   const r=await semanticRequest('/semantic/find',
      {statement:"FIND '"+escaped+"' IN '"+semanticNamespace+"' LIMIT 50;"});
   setSemanticHits(r.result.hits);setSemanticTruncated(r.result.truncated);
   setSemanticStatus('Indexed text search: '+r.result.hits.length+' matches. No visual recognition performed.');
  }catch(e){setSemanticStatus(String(e));setSemanticHits([])}
  finally{setSemanticRunning(false)}
 }
 const anchorLabel=(a:SemanticHit['anchor'])=>a.kind==='csv_row'?'Row '+a.row_number:
  a.kind==='json_pointer'?'JSON '+(a.pointer||'/'):
  a.kind==='image_frame'?'Image pixels':
  a.kind==='video_frame'?'Video frame':
  a.kind==='pdf_page'?'Page '+a.page_number:
  a.kind==='docx_paragraph'?'Paragraph '+a.paragraph_number:
  a.kind==='html_line'||a.kind==='text_line'?'Line '+a.line_number:
  a.kind==='time_range'?
  ((a.start_ms||0)/1000).toFixed(3)+'s–'+((a.end_ms||0)/1000).toFixed(3)+'s':'Source anchor';
 const headers=()=>({'Authorization':'Bearer '+token,'Content-Type':'application/json'});
 async function request(path:string,method='GET',data?:unknown){
  const response=await fetch(path,{method,headers:headers(),body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok)throw new Error(result.error||'Request failed');
  return result;
 }
 async function refresh(){try{setState(await request('/v1/state'));setMessage('Registry loaded')}catch(e){setMessage(String(e))}}
 async function run(operation:()=>Promise<unknown>){try{await operation();await refresh()}catch(e){setMessage(String(e))}}
 useEffect(()=>{if(token)refresh()},[]); // Authentication is deliberately supplied by the operator; not persisted.
 return <main>
   <header><span className="logo">◈</span><div><h1>QualityRag Studio</h1><p>APX-inspired policy workbench · service registry · governed bindings</p></div></header>
   <section className="notice"><strong>Local development preview.</strong> This UI accepts an operator token in local mode or an OIDC bearer token when the registry enables OIDC. Authentication occurs at the registry. The UI has no interactive OIDC login flow, tenant isolation or production multi-user state.</section>
   <section className="panel"><h2>Connect to registry</h2><div className="line"><label>Registry bearer token<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} placeholder="Development token or OIDC access token"/></label><button onClick={refresh} disabled={!token}>Connect / refresh</button></div><p className="status" role="status">{message}</p></section>
   <div className="columns"><section className="panel"><h2>1. Register service</h2><p>Identify the application that will consume an approved policy.</p><label>Service ID<input value={serviceId} onChange={e=>setServiceId(e.target.value)}/></label><label>Display name<input value={name} onChange={e=>setName(e.target.value)}/></label><button disabled={!token} onClick={()=>run(()=>request('/v1/services','POST',{id:serviceId,displayName:name}))}>Register service</button><ul>{state.services.map(s=><li key={s.id}>{s.displayName} <code>{s.id}</code></li>)}</ul></section>
   <section className="panel"><h2>2. Draft and approve PackSpec</h2><p>Each version is immutable after creation; approve explicitly before binding.</p><label>PackSpec JSON<textarea spellCheck={false} value={editor} onChange={e=>setEditor(e.target.value)}/></label><button disabled={!token} onClick={()=>run(()=>request('/v1/policies/drafts','POST',JSON.parse(editor)))}>Save draft</button><ul>{state.policies.map(p=><li key={p.sha256}><code>{p.policy.id}@{p.policy.version}</code><span>{p.status}</span>{p.status==='DRAFT'&&<button disabled={!token} onClick={()=>run(()=>request('/v1/policies/'+encodeURIComponent(p.policy.id)+'/'+encodeURIComponent(p.policy.version)+'/approve','POST'))}>Approve</button>}</li>)}</ul></section></div>
   <section className="panel"><h2>3. Assign policy to environment</h2><p>Services resolve only approved versions. Application SDKs enforce the resolved requirements locally.</p><div className="line"><label>Service<input value={serviceId} onChange={e=>setServiceId(e.target.value)}/></label><label>Environment<input value={environment} onChange={e=>setEnvironment(e.target.value)}/></label><label>Policy ID<input value={policyId} onChange={e=>setPolicyId(e.target.value)}/></label><label>Version<input value={version} onChange={e=>setVersion(e.target.value)}/></label></div><button disabled={!token} onClick={()=>run(()=>request('/v1/bindings','POST',{serviceId,environment,policyId,version}))}>Bind approved policy</button><ul>{state.bindings.map(b=><li key={b.serviceId+'@'+b.environment}><code>{b.serviceId}@{b.environment}</code> → {b.policyId}@{b.version}</li>)}</ul><p>Resolve endpoint: <code>GET /v1/resolve/{serviceId}/{environment}</code></p></section>
   <section className="panel"><h2>4. Signed policy promotion</h2>
   <p>Sign the full reviewed ConstraintIR outside Studio with a governance-controlled private key. The registry verifies the Ed25519 signature using a pinned public key, then enforces staged → approved → published status and monotonically increasing sequence numbers. In OIDC mode, author, approver and publisher must be distinct authenticated subjects. Use a different authorized bearer token for each action. The local development token retains the single-operator mode.</p>
   <label>Externally signed policy bundle JSON<textarea spellCheck={false} value={signedBundle} onChange={e=>setSignedBundle(e.target.value)} placeholder='{"schema":"qualityrag.signed-policy/v1","canonical":"QR-CJSON-1",...}'/></label>
   <button disabled={!token || !signedBundle.trim()} onClick={()=>run(()=>request('/v1/signed/promotions','POST',JSON.parse(signedBundle)))}>Stage signed bundle</button>
   <ul>{state.signedPromotions.map(p=><li key={p.serviceId+'@'+p.environment+'#'+p.sequence}>
    <code>{p.serviceId}@{p.environment} #{p.sequence}</code> <span>{p.status}</span>
    {p.status==='STAGED'&&<button disabled={!token} onClick={()=>run(()=>request('/v1/signed/promotions/'+encodeURIComponent(p.serviceId)+'/'+encodeURIComponent(p.environment)+'/'+p.sequence+'/approve','POST'))}>Approve signed version</button>}
    {p.status==='APPROVED'&&<button disabled={!token} onClick={()=>run(()=>request('/v1/signed/promotions/'+encodeURIComponent(p.serviceId)+'/'+encodeURIComponent(p.environment)+'/'+p.sequence+'/publish','POST'))}>Publish approved version</button>}
   </li>)}</ul>
   <p>Published versions:</p><ul>{state.signedBindings.map(p=><li key={p.serviceId+'@'+p.environment}><code>{p.serviceId}@{p.environment}</code> → signed sequence {p.sequence}</li>)}</ul>
   <p>For application verification: <code>GET /v1/signed/resolve/{serviceId}/{environment}</code>. Legacy unsigned policy bindings remain separate; the signed client must never silently downgrade.</p>
   </section>
   <section className="panel" aria-label="Semantic Store directory search">
   <h2>5. Semantic Store · Local directory</h2>
   <p>Search indexed documents and reference image appearance across supported photos and sampled video frames with a familiar FIND statement. Run the separate loopback-only workbench; the server's directory is fixed at startup. This interface does not access server paths directly.</p>
   <div className="line">
    <label>Local Semantic Workbench token<input type="password" autoComplete="off"
      value={semanticToken} onChange={e=>setSemanticToken(e.target.value)}
      placeholder="Separate semantic token (not registry token)"/></label>
    <button disabled={!semanticToken||semanticRunning} onClick={semanticConnect}>Connect directory</button>
    <button disabled={!semanticDirectory||semanticRunning} onClick={semanticIndex}>Index files</button>
   </div>
   {semanticDirectory&&<p>Configured folder: <code>{semanticDirectory}</code> · Namespace: <code>{semanticNamespace}</code></p>}
   <div className="line">
    <label>Find in indexed files<input value={semanticTerm} onChange={e=>setSemanticTerm(e.target.value)}
     placeholder="Cyrille" aria-label="Find text"/></label>
    <button disabled={!semanticDirectory||!semanticTerm.trim()||semanticRunning}
     onClick={semanticFind}>Find</button>
   </div>
   <p className="status" role="status">{semanticStatus}</p>
   {semanticCoverage&&<p>Indexed: {semanticCoverage.indexed} · Unchanged: {semanticCoverage.unchanged} ·
    Unsupported: {semanticCoverage.unsupported} · Failed: {semanticCoverage.failed} ·
    Access denied: {semanticCoverage.denied} · Symlinks skipped: {semanticCoverage.symlinks_skipped}</p>}
   <p><strong>Source-linked results</strong> · Indexed text only; partial document extraction without OCR, embedded media, visual matching, or identity verification.</p>
   {semanticTruncated&&<p role="alert">Results are truncated. Narrow the search or increase safe backend coverage.</p>}
   <ul>{semanticHits.map((hit,i)=><li key={hit.source_id+'#'+hit.revision+'#'+i}>
    <strong>{hit.source_id}</strong> <code>{hit.format}</code> · {anchorLabel(hit.anchor)} ·
    <span>{hit.field}: {hit.matched_text.slice(0,350)}</span>
   </li>)}</ul>
   <hr/>
   <h3>Find visually similar images and video frames</h3>
   <p>Select an indexed source image by its exact namespace-relative identifier
    (for example <code>local/reference.png</code>). Results describe whole-frame appearance similarity,
    <strong> not whether the same person appears in the images.</strong>
    Video sampling requires FFmpeg on the local worker.</p>
   <div className="line">
    <label>Indexed reference image ID<input value={visualReference}
      onChange={e=>setVisualReference(e.target.value)}
      placeholder="local/reference.png" aria-label="Indexed visual reference"/></label>
    <button disabled={!semanticDirectory||!visualReference.trim()||semanticRunning}
      onClick={visualFind}>Find similar media</button>
   </div>
   <p className="status" role="status">{visualStatus}</p>
   <ul>{visualResults.map((result,i)=><li key={result.source_id+result.revision+i}>
    <strong>{result.source_id}</strong> <code>{result.format}</code> ·
    Perceptual distance: {result.distance}/64 · {result.anchor.kind==='video_frame'?
      'At '+((result.anchor.timestamp_ms||0)/1000).toFixed(1)+'s':'Image'} · Identity: unknown
   </li>)}</ul>
   <hr/>
   <h3>Search visual scenes using a prompt</h3>
   <p>Optional local vision-language model. Uses sampled images/frames rather than captions; model rankings are unverified
   and do not identify named people. Enable the local model in the worker configuration.</p>
   <button disabled={!semanticDirectory||!sceneReady||semanticRunning} onClick={sceneIndex}>Build scene index</button>
   {!sceneReady&&<p>Scene model unavailable. Enable the local OpenCLIP model to search visual content with prompts.</p>}
   <div className="line">
    <label>Visual scene prompt<input value={scenePrompt} onChange={e=>setScenePrompt(e.target.value)}
      placeholder="someone presenting in a conference room"/></label>
    <button disabled={!semanticDirectory||!sceneReady||!scenePrompt.trim()||semanticRunning}
      onClick={sceneFind}>Find scenes</button>
   </div>
   <p className="status" role="status">{sceneStatus}</p>
   <ul>{sceneHits.map((hit,i)=><li key={hit.source_id+hit.revision+i}>
    <strong>{hit.source_id}</strong> · {hit.anchor.kind==='video_frame'?
     'At '+((hit.anchor.timestamp_ms||0)/1000).toFixed(1)+'s':'Image'} ·
    Similarity: {hit.similarity.toFixed(3)} (not probability) · Unverified model candidate
   </li>)}</ul>
   </section>
   <section className="panel" aria-label="Semantic Garden research engine">
    <h2>6. Semantic Garden · Engine console</h2>
    <p>Connect to the real bounded research controller and read the existing append-only evidence ledger. No simulated engine results. Research findings are never automatically admitted or deployed.</p>
    <div className="line">
      <label>Local Garden engine token<input type="password" autoComplete="off"
        value={gardenToken} onChange={e=>{setGardenToken(e.target.value);setGardenConnected(false)}}
        placeholder="Separate Garden engine token"/></label>
      <button onClick={connectGarden} disabled={gardenBusy||!gardenToken.trim()}>
        {gardenBusy?'Connecting…':'Connect / refresh engine'}
      </button>
    </div>
    <p className="status" role="status">{gardenStatus}</p>
    {gardenConnected&&<>
     <p>Research branches: <strong>{gardenBranches.length}</strong> · Recorded events: <strong>{gardenEvents.length}</strong> · Lineage links: <strong>{gardenRelations.length}</strong> · Admission: <strong>NOT ESTABLISHED</strong></p>
     <h3>Research branches and assessments</h3>
     <ul>{gardenBranches.slice(0,25).map(b=><li key={b.id}><code>{b.id}</code> · <strong>{b.assessment}</strong> · {b.statement}</li>)}</ul>
     {gardenBranches.length>25&&<p>Showing first 25 branches. Full history available from the authenticated projection endpoint.</p>}
     <h3>Latest research events</h3>
     <ul>{gardenEvents.slice(-15).reverse().map(e=><li key={e.id}><code>{e.branch_id}</code> · {e.assessment} · {e.reason}</li>)}</ul>
     <h3>Run bounded grammar and activation investigation</h3>
     <p>Paste a research manifest containing training, examples, source, revised_source, workload, trials (2–3) and max_probes (0–3). Gold answers must not appear in the evaluation workload. The engine never fabricates missing probe evidence.</p>
     <label>Research experiment JSON<textarea spellCheck={false} value={gardenDraft}
       onChange={e=>setGardenDraft(e.target.value)}
       placeholder='{"training":{},"examples":[],"source":{},"revised_source":{},"workload":{"subjects":[]},"trials":2,"max_probes":0}'/></label>
     <button onClick={investigateGarden} disabled={gardenBusy||!gardenDraft.trim()}>Execute on connected Garden engine</button>
     {gardenReceipt&&<div role="status"><p><strong>Engine verdict:</strong> {gardenReceipt.status} · External observations: {gardenReceipt.external_probe_count}</p>
       <p>Policy admission: {gardenReceipt.qualityrag_admission} · Persisted: {gardenReceipt.ledger_persisted?'yes':'no'}{gardenReceipt.ledger_reason?' ('+gardenReceipt.ledger_reason+')':''}</p>
       {('ledger_claim_id' in gardenReceipt)&&<p>Recorded research claim: <code>{String(gardenReceipt.ledger_claim_id)}</code></p>}
       <p>Evaluated grammar/activation pairs: {gardenReceipt.investigation?.experiment?.results?.length??0}</p>
      </div>}
    </>}
   </section>
   <footer>QualityRag v0.1 · deterministic policy enforcement · policies are not proof of source truth</footer>
 </main>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><Studio/></React.StrictMode>);
