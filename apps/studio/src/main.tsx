import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Service={id:string;displayName:string};
type Policy={policy:{id:string;version:string;requirements:unknown[]};status:string;sha256:string};
type Binding={serviceId:string;environment:string;policyId:string;version:string};
const starter={id:'eligibility',version:'1.0.0',requirements:[{id:'governing-rule',min_independent_sources:2,max_age_seconds:86400}]};
function Studio(){
 const [token,setToken]=useState(''),[state,setState]=useState<{services:Service[];policies:Policy[];bindings:Binding[]}>({services:[],policies:[],bindings:[]});
 const [serviceId,setServiceId]=useState('claims-api'),[name,setName]=useState('Claims API'),[environment,setEnvironment]=useState('dev');
 const [policyId,setPolicyId]=useState('eligibility'),[version,setVersion]=useState('1.0.0'),[editor,setEditor]=useState(JSON.stringify(starter,null,2)),[message,setMessage]=useState('');
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
   <section className="notice"><strong>Local development preview.</strong> This app uses an operator token in memory. No OIDC, tenant isolation or production RBAC yet.</section>
   <section className="panel"><h2>Connect to registry</h2><div className="line"><label>Local registry token<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} placeholder="QUALITYRAG_REGISTRY_TOKEN"/></label><button onClick={refresh} disabled={!token}>Connect / refresh</button></div><p className="status" role="status">{message}</p></section>
   <div className="columns"><section className="panel"><h2>1. Register service</h2><p>Identify the application that will consume an approved policy.</p><label>Service ID<input value={serviceId} onChange={e=>setServiceId(e.target.value)}/></label><label>Display name<input value={name} onChange={e=>setName(e.target.value)}/></label><button disabled={!token} onClick={()=>run(()=>request('/v1/services','POST',{id:serviceId,displayName:name}))}>Register service</button><ul>{state.services.map(s=><li key={s.id}>{s.displayName} <code>{s.id}</code></li>)}</ul></section>
   <section className="panel"><h2>2. Draft and approve PackSpec</h2><p>Each version is immutable after creation; approve explicitly before binding.</p><label>PackSpec JSON<textarea spellCheck={false} value={editor} onChange={e=>setEditor(e.target.value)}/></label><button disabled={!token} onClick={()=>run(()=>request('/v1/policies/drafts','POST',JSON.parse(editor)))}>Save draft</button><ul>{state.policies.map(p=><li key={p.sha256}><code>{p.policy.id}@{p.policy.version}</code><span>{p.status}</span>{p.status==='DRAFT'&&<button disabled={!token} onClick={()=>run(()=>request('/v1/policies/'+encodeURIComponent(p.policy.id)+'/'+encodeURIComponent(p.policy.version)+'/approve','POST'))}>Approve</button>}</li>)}</ul></section></div>
   <section className="panel"><h2>3. Assign policy to environment</h2><p>Services resolve only approved versions. Application SDKs enforce the resolved requirements locally.</p><div className="line"><label>Service<input value={serviceId} onChange={e=>setServiceId(e.target.value)}/></label><label>Environment<input value={environment} onChange={e=>setEnvironment(e.target.value)}/></label><label>Policy ID<input value={policyId} onChange={e=>setPolicyId(e.target.value)}/></label><label>Version<input value={version} onChange={e=>setVersion(e.target.value)}/></label></div><button disabled={!token} onClick={()=>run(()=>request('/v1/bindings','POST',{serviceId,environment,policyId,version}))}>Bind approved policy</button><ul>{state.bindings.map(b=><li key={b.serviceId+'@'+b.environment}><code>{b.serviceId}@{b.environment}</code> → {b.policyId}@{b.version}</li>)}</ul><p>Resolve endpoint: <code>GET /v1/resolve/{serviceId}/{environment}</code></p></section>
   <footer>QualityRag v0.1 · deterministic policy enforcement · policies are not proof of source truth</footer>
 </main>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><Studio/></React.StrictMode>);
