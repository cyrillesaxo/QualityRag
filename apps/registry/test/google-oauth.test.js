import test from 'node:test';
import assert from 'node:assert/strict';
import {googleOAuthConfig,createGoogleAuthorization,validateGoogleCallback,exchangeGoogleCode,GOOGLE_DRIVE_READ_SCOPE} from '../src/google-oauth.js';
const cfg=googleOAuthConfig({clientId:'client',clientSecret:'secret',redirectUri:'https://example.org/oauth/google/callback'});
test('authorization uses state, PKCE S256 and read-only scope',()=>{
 const r=createGoogleAuthorization(cfg,{tenantId:'t',principalId:'p',now:1000});const u=new URL(r.authorization_url);
 assert.equal(u.searchParams.get('scope'),GOOGLE_DRIVE_READ_SCOPE);
 assert.equal(u.searchParams.get('code_challenge_method'),'S256');
 assert.equal(u.searchParams.get('state').length>=32,true);
 assert.equal(r.pending.expires_at,601000);
 assert.equal(r.pending.state_hash.includes(u.searchParams.get('state')),false);
 const valid=validateGoogleCallback({state:u.searchParams.get('state'),code:'authcode'},r.pending,{tenantId:'t',principalId:'p',now:2000});
 assert.equal(valid.code,'authcode');
 assert.throws(()=>validateGoogleCallback({state:u.searchParams.get('state'),code:'authcode'},{...r.pending,consumed:true},{tenantId:'t',principalId:'p',now:2000}),/USED/);
 assert.throws(()=>validateGoogleCallback({state:u.searchParams.get('state'),code:'authcode'},r.pending,{tenantId:'wrong',principalId:'p',now:2000}),/ACTOR/);
 assert.throws(()=>validateGoogleCallback({state:'a'.repeat(43),code:'authcode'},r.pending,{tenantId:'t',principalId:'p',now:2000}),/MISMATCH/);
});
test('rejects non HTTPS redirect',()=>assert.throws(()=>googleOAuthConfig({clientId:'a',clientSecret:'b',redirectUri:'http://evil.example/cb'}),/HTTPS/));
test('exchanges authorization code and enforces scope',async()=>{
 const result=await exchangeGoogleCode(cfg,{code:'abc',code_verifier:'verifier'},async(url,opts)=>{
  assert.equal(url,'https://oauth2.googleapis.com/token');assert.equal(opts.body.get('code_verifier'),'verifier');
  return {ok:true,json:async()=>({access_token:'access',scope:GOOGLE_DRIVE_READ_SCOPE})};
 });assert.equal(result.access_token,'access');
 await assert.rejects(exchangeGoogleCode(cfg,{code:'abc',code_verifier:'v'},async()=>({ok:true,json:async()=>({access_token:'a',scope:'openid'})})),/SCOPE/);
});
