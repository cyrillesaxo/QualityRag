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
   <footer>QualityRag v0.1 · deterministic policy enforcement · policies are not proof of source truth</footer>
 </main>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><Studio/></React.StrictMode>);
