// Public-client OIDC Authorization Code + PKCE.
// The configured OIDC provider must offer Google as an upstream sign-in option and
// issue QualityRAG audience/role-scoped access tokens. Google ID tokens alone are
// not QualityRAG API credentials.
const CLIENT_ID=import.meta.env.VITE_QUALITYRAG_OIDC_CLIENT_ID||'';
const AUTH_URL=import.meta.env.VITE_QUALITYRAG_OIDC_AUTHORIZATION_ENDPOINT||'';
const TOKEN_URL=import.meta.env.VITE_QUALITYRAG_OIDC_TOKEN_ENDPOINT||'';
const AUDIENCE=import.meta.env.VITE_QUALITYRAG_OIDC_AUDIENCE||'';
const KEY='qualityrag-oidc-pkce-transaction-v1';
const TIMEOUT_MS=10*60*1000;
type LoginConfig={clientId:string;authorizationEndpoint:string;tokenEndpoint:string;audience:string};
type Transaction={state:string;verifier:string;started:number;redirectUri:string};
export function loginConfig():LoginConfig|null{
 if(!CLIENT_ID||!AUTH_URL||!TOKEN_URL)return null;
 if(CLIENT_ID.length>256||!/^[A-Za-z0-9._~-]{1,256}$/.test(CLIENT_ID))return null;
 try{
  const a=new URL(AUTH_URL),t=new URL(TOKEN_URL);
  if(a.protocol!=='https:'||t.protocol!=='https:'||a.origin!==t.origin||
     a.username||a.password||a.hash||t.username||t.password||t.hash||
     !a.pathname||!t.pathname||a.search||t.search)return null;
  return {clientId:CLIENT_ID,authorizationEndpoint:a.href,tokenEndpoint:t.href,audience:AUDIENCE};
 }catch{return null}
}
function base64url(input:Uint8Array){
 let s='';
 input.forEach(b=>{s+=String.fromCharCode(b)});
 return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function randomValue(){
 const bytes=new Uint8Array(32);
 crypto.getRandomValues(bytes);
 return base64url(bytes);
}
const callbackUrl=()=>location.origin+'/';
export async function beginGoogleLogin(config:LoginConfig){
 // Explicit user gesture only. No credentials or tokens in browser URLs.
 const state=randomValue(),verifier=randomValue();
 const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
 const challenge=base64url(new Uint8Array(hash));
 const redirectUri=callbackUrl();
 const tx:Transaction={state,verifier,started:Date.now(),redirectUri};
 sessionStorage.setItem(KEY,JSON.stringify(tx));
 const url=new URL(config.authorizationEndpoint);
 url.searchParams.set('client_id',config.clientId);
 url.searchParams.set('redirect_uri',redirectUri);
 url.searchParams.set('response_type','code');
 url.searchParams.set('scope','openid profile email');
 url.searchParams.set('state',state);
 url.searchParams.set('code_challenge',challenge);
 url.searchParams.set('code_challenge_method','S256');
 if(config.audience)url.searchParams.set('audience',config.audience);
 location.assign(url.href);
}
function readTransaction():Transaction|null{
 const raw=sessionStorage.getItem(KEY);
 sessionStorage.removeItem(KEY);
 if(!raw)return null;
 try{
  const tx=JSON.parse(raw) as Transaction;
  if(!tx||typeof tx.state!=='string'||typeof tx.verifier!=='string'||
     typeof tx.started!=='number'||typeof tx.redirectUri!=='string'||
     tx.redirectUri!==callbackUrl()||Date.now()-tx.started>TIMEOUT_MS||
     Date.now()<tx.started||!tx.state||!tx.verifier)return null;
  return tx;
 }catch{return null}
}
export async function finishGoogleLogin(config:LoginConfig):Promise<string|null>{
 const url=new URL(location.href);
 const hasCallback=url.searchParams.has('code')||url.searchParams.has('error')||
  url.searchParams.has('state');
 if(!hasCallback)return null;
 const codes=url.searchParams.getAll('code');
 const states=url.searchParams.getAll('state');
 const errors=url.searchParams.getAll('error');
 // Strip authorization response before network operations, logging or UI rendering.
 history.replaceState(null,'',location.pathname);
 const tx=readTransaction();
 if(!tx||states.length!==1||states[0]!==tx.state||
    codes.length>1||errors.length>1)throw Error('Google sign-in state is invalid or expired. Retry from Studio.');
 if(errors.length)throw Error('Google sign-in was cancelled or denied.');
 if(codes.length!==1||!codes[0]||codes[0].length>4096)
  throw Error('The identity provider did not return a valid authorization code.');
 const form=new URLSearchParams({grant_type:'authorization_code',client_id:config.clientId,
  code:codes[0],code_verifier:tx.verifier,redirect_uri:tx.redirectUri});
 const response=await fetch(config.tokenEndpoint,{
  method:'POST',redirect:'error',cache:'no-store',
  headers:{'Content-Type':'application/x-www-form-urlencoded',Accept:'application/json'},
  body:form.toString()});
 if(!response.ok)throw Error('The identity provider rejected the code exchange.');
 if(!(response.headers.get('content-type')||'').includes('application/json'))
  throw Error('Invalid identity provider response format.');
 const raw=await response.text();
 if(raw.length>16000)throw Error('Identity provider response is too large.');
 const result=JSON.parse(raw);
 if(typeof result.access_token!=='string'||result.access_token.length<16||
    result.access_token.length>8192||result.token_type?.toLowerCase()!=='bearer'||
    !Number.isFinite(result.expires_in)||result.expires_in<=0)
  throw Error('No valid QualityRAG bearer access token was returned.');
 return result.access_token;
}
export async function verifyRegistryToken(token:string):Promise<void>{
 // Authorization is entirely enforced by Registry. No client-side role claims trusted.
 // A Drive-only user may lack policy.reader, so validate either of the scoped reads.
 let challenged=false;
 for(const path of ['/v1/drives/google/status','/v1/state']){
  const res=await fetch(path,{headers:{Authorization:'Bearer '+token,Accept:'application/json'},
   cache:'no-store',redirect:'error'});
  if(res.status===401||res.status===403){challenged=true;continue}
  if(!res.ok)throw Error('QualityRAG Registry is unavailable (HTTP '+res.status+').');
  if(!(res.headers.get('content-type')||'').includes('application/json'))
   throw Error('Registry returned an HTML page instead of an authenticated API response.');
  const raw=await res.text();
  if(raw.length>100000)throw Error('Unexpected Registry response size.');
  const data=JSON.parse(raw);
  if(!data||typeof data!=='object'||Array.isArray(data))
   throw Error('Registry returned an invalid response.');
  return;
 }
 throw Error(challenged?'Your Google identity lacks assigned QualityRAG Registry roles.':
  'The Registry did not verify the session.');
}
