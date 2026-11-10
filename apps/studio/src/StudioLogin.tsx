import React,{useEffect,useRef,useState} from 'react';
import {RegistryReadiness} from './RegistryReadiness';
import {beginGoogleLogin,finishGoogleLogin,loginConfig,verifyRegistryToken} from './google-login';

type Props={onAuthenticated:(token:string)=>void};
export function StudioLogin({onAuthenticated}:Props){
 const config=loginConfig();
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [manualToken,setManualToken]=useState('');
 const attempted=useRef(false);
 const manualAllowed=import.meta.env.VITE_QUALITYRAG_ALLOW_MANUAL_TOKEN==='true';
 useEffect(()=>{
  if(attempted.current)return;
  attempted.current=true;
  const params=new URLSearchParams(location.search);
  if(!params.has('code')&&!params.has('state')&&!params.has('error'))return;
  if(!config){
   history.replaceState(null,'',location.pathname);
   setError('Google sign-in is not configured for this Studio deployment.');
   return;
  }
  setBusy(true);
  finishGoogleLogin(config).then(async token=>{
   if(!token)throw Error('No identity token exchange took place.');
   await verifyRegistryToken(token);
   onAuthenticated(token);
  }).catch(e=>setError(e instanceof Error?e.message:'Google sign-in failed.'))
   .finally(()=>setBusy(false));
 },[config,onAuthenticated]);
 async function startLogin(){
  if(!config||busy)return;
  setBusy(true);setError('');
  try{await beginGoogleLogin(config)}
  catch(e){setError(e instanceof Error?e.message:'Google sign-in could not start.');setBusy(false)}
 }
 async function useManual(){
  if(!manualAllowed||busy||!manualToken)return;
  setBusy(true);setError('');
  try{await verifyRegistryToken(manualToken);onAuthenticated(manualToken);setManualToken('')}
  catch(e){setError(e instanceof Error?e.message:'The Registry rejected this token.')}
  finally{setBusy(false)}
 }
 return <main style={{maxWidth:760,margin:'0 auto'}}>
  <header><span className="logo">◈</span><div>
   <h1>QualityRAG Studio</h1>
   <p>Evidence governance · Visibility and control</p>
  </div></header>
  <section className="panel" aria-label="QualityRAG Studio login" style={{
    maxWidth:520,margin:'28px auto',padding:26}}>
   <h2 style={{marginTop:0}}>Sign in to Studio</h2>
   <p>Use your organization's Google account to sign in. Access to policies,
     customer documents and evidence review still requires assigned QualityRAG roles.</p>
   <button type="button" onClick={startLogin} disabled={!config||busy}
     style={{width:'100%',padding:13,fontWeight:600}}>
     {busy?'Verifying sign-in…':'Continue with Google'}
   </button>
   {!config&&<p role="status" style={{fontSize:13}}>
     Google sign-in is not configured yet. The operator must connect a trusted
     OIDC provider with Google as an upstream identity, a public PKCE client,
     and a secured Registry API. This button remains disabled until then.
   </p>}
   {config&&<p style={{fontSize:12}}>
     Your browser is redirected to the configured identity provider. Tokens are
     kept only in the current page's memory, not in local storage.
   </p>}
   {error&&<p role="alert" style={{color:'#a83224'}}>{error}</p>}
   {manualAllowed&&<details style={{marginTop:15}}>
     <summary>Operator diagnostic sign-in (test roles only)</summary>
     <p>Manual bearer tokens are for a separately authorized development pilot.
       Never paste production credentials into an unverified deployment.</p>
     <label>Registry scoped access token
       <input type="password" autoComplete="off" value={manualToken}
         onChange={e=>setManualToken(e.target.value)} />
     </label>
     <button type="button" disabled={busy||!manualToken} onClick={useManual}>
       Verify with Registry
     </button>
   </details>}
  </section>
  <RegistryReadiness/>
  <p style={{fontSize:12,textAlign:'center'}}>
   Google login and Google Drive authorization are separate permissions.
   No Drive content is downloaded by signing in.
  </p>
 </main>;
}
