import React,{useEffect,useState} from 'react';

type State='checking'|'ready'|'missing'|'invalid'|'unreachable';
type Result={state:State;detail:string};

/** Informational probe only. Readiness does not grant authorization. */
export function RegistryReadiness(){
 const [result,setResult]=useState<Result>({state:'checking',detail:'Checking same-origin Registry readiness…'});
 const [attempt,setAttempt]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();
  setResult({state:'checking',detail:'Checking same-origin Registry readiness…'});
  fetch('/ready',{cache:'no-store',redirect:'error',signal:controller.signal,
   headers:{Accept:'application/json'}})
  .then(async response=>{
   if(response.status===404){
    setResult({state:'missing',detail:'No Registry /ready route is deployed on this origin. Studio is frontend-only.'});
    return;
   }
   if(!response.ok){
    setResult({state:'unreachable',detail:'Registry readiness returned HTTP '+response.status+'. The gateway/backend is not ready.'});
    return;
   }
   const type=response.headers.get('content-type')||'';
   if(!type.toLowerCase().includes('application/json')){
    setResult({state:'invalid',detail:'The readiness URL returned HTML or another non-JSON response, not a Registry readiness contract.'});
    return;
   }
   const raw=await response.text();
   if(raw.length>8192)throw Error('Unexpectedly large readiness response');
   let data:unknown;
   try{data=JSON.parse(raw)}catch{throw Error('Invalid readiness JSON')}
   if(!data||typeof data!=='object'||Array.isArray(data)||
      !Object.hasOwn(data,'ready')||typeof (data as {ready:unknown}).ready!=='boolean'){
    setResult({state:'invalid',detail:'The endpoint did not return the Registry readiness contract.'});
    return;
   }
   if((data as {ready:boolean}).ready!==true){
    setResult({state:'unreachable',detail:'The Registry is reporting not ready. No connection is authorized.'});
    return;
   }
   setResult({state:'ready',detail:'Same-origin Registry readiness endpoint responded. Authentication, OAuth, and authorization remain unverified.'});
  }).catch(e=>{
   if(controller.signal.aborted)return;
   setResult({state:'unreachable',detail:'Could not verify Registry readiness ('+
    (e instanceof Error?e.message:'network failure')+').'});
  });
  return()=>controller.abort();
 },[attempt]);
 return <section className="panel" aria-label="Registry API connectivity diagnostic">
  <h2>Registry connectivity</h2>
  <p role="status"><strong>{result.state==='ready'?'Endpoint responding':
    result.state==='checking'?'Checking…':'Not connected'}</strong> — {result.detail}</p>
  <p style={{fontSize:13}}>
   The Studio is a static frontend. A successful website deploy does not deploy
   the Registry. Readiness is a connectivity probe, not proof of a trusted
   gateway, signed-in identity, Google OAuth grant, or permission to ingest files.
  </p>
  <button type="button" onClick={()=>setAttempt(v=>v+1)}
    disabled={result.state==='checking'}>Recheck Registry connectivity</button>
 </section>;
}
