import {randomBytes,createHash,timingSafeEqual} from 'node:crypto';

const AUTH='https://accounts.google.com/o/oauth2/v2/auth';
const TOKEN='https://oauth2.googleapis.com/token';
const SCOPE='https://www.googleapis.com/auth/drive.readonly';
const ID_RE=/^[A-Za-z0-9_-]{20,256}$/;
const b64url=buf=>Buffer.from(buf).toString('base64url');
const sha256=s=>createHash('sha256').update(s).digest();
const required=(s,name)=>{if(typeof s!=='string'||!s.trim())throw new Error(name+'_REQUIRED');return s;};
export function googleOAuthConfig({clientId,clientSecret,redirectUri}){
 required(clientId,'GOOGLE_CLIENT_ID');required(clientSecret,'GOOGLE_CLIENT_SECRET');
 const u=new URL(required(redirectUri,'GOOGLE_REDIRECT_URI'));
 if(u.protocol!=='https:'&&!(['localhost','127.0.0.1'].includes(u.hostname)&&u.protocol==='http:'))throw new Error('HTTPS_REDIRECT_REQUIRED');
 if(u.username||u.password||u.hash)throw new Error('INVALID_REDIRECT_URI');
 return {clientId,clientSecret,redirectUri:u.toString()};
}
// Caller MUST persist hashed state, verifier, tenant, principal and expiry in an
// atomic one-time-use server-side store before redirecting the browser.
export function createGoogleAuthorization(config,{tenantId,principalId,now=Date.now()}={}){
 required(tenantId,'TENANT_ID');required(principalId,'PRINCIPAL_ID');
 const state=b64url(randomBytes(32));const verifier=b64url(randomBytes(32));
 const challenge=b64url(sha256(verifier));
 const url=new URL(AUTH);
 for(const [k,v] of Object.entries({client_id:config.clientId,redirect_uri:config.redirectUri,response_type:'code',scope:SCOPE,
  state,code_challenge:challenge,code_challenge_method:'S256',access_type:'offline',prompt:'consent',include_granted_scopes:'false'}))url.searchParams.set(k,v);
 return {authorization_url:url.toString(),state_issued:true,
  pending:{state_hash:b64url(sha256(state)),code_verifier:verifier,tenant_id:tenantId,principal_id:principalId,expires_at:now+600_000,consumed:false}};
}
export function validateGoogleCallback({state,code,error},pending,{tenantId,principalId,now=Date.now()}={}){
 if(!pending||pending.consumed||now>=pending.expires_at)throw new Error('OAUTH_STATE_EXPIRED_OR_USED');
 if(pending.tenant_id!==tenantId||pending.principal_id!==principalId)throw new Error('OAUTH_ACTOR_MISMATCH');
 if(!ID_RE.test(state||''))throw new Error('OAUTH_STATE_INVALID');
 const got=sha256(state),expected=Buffer.from(pending.state_hash||'','base64url');
 if(got.length!==expected.length||!timingSafeEqual(got,expected))throw new Error('OAUTH_STATE_MISMATCH');
 if(error)throw new Error('GOOGLE_OAUTH_DENIED');
 if(typeof code!=='string'||!code.trim())throw new Error('GOOGLE_OAUTH_CODE_MISSING');
 return {code,code_verifier:pending.code_verifier};
}
// Never return token payloads to the browser. Encrypt and persist the refresh token
// in the server-side tenant-scoped credential store; require one-time state consumption.
export async function exchangeGoogleCode(config,{code,code_verifier},fetchImpl=fetch){
 const body=new URLSearchParams({client_id:config.clientId,client_secret:config.clientSecret,
  redirect_uri:config.redirectUri,grant_type:'authorization_code',code,code_verifier});
 const response=await fetchImpl(TOKEN,{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body});
 if(!response.ok)throw new Error('GOOGLE_TOKEN_EXCHANGE_FAILED');
 const result=await response.json();
 if(!result||typeof result.access_token!=='string'||!result.access_token||
   typeof result.scope!=='string'||!result.scope.split(' ').includes(SCOPE))throw new Error('GOOGLE_SCOPE_NOT_GRANTED');
 return result;
}
export const GOOGLE_DRIVE_READ_SCOPE=SCOPE;
