import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=path=>readFileSync(path,'utf8');
const auth=read('apps/studio/src/google-login.ts');
const login=read('apps/studio/src/StudioLogin.tsx');
const main=read('apps/studio/src/main.tsx');
test('login is presented before Studio dashboard and token input is disabled by default',()=>{
 assert.match(main,/if\(!token\)return <StudioLogin onAuthenticated=\{setToken\}\/>/);
 assert.doesNotMatch(main,/Registry bearer token<input/);
 assert.match(login,/Continue with Google/);
 assert.match(login,/disabled=\{!config\|\|busy\}/);
 assert.match(login,/VITE_QUALITYRAG_ALLOW_MANUAL_TOKEN==='true'/);
});
test('OIDC login uses PKCE S256, one-time state, no client secret or persisted access token',()=>{
 assert.match(auth,/crypto\.getRandomValues/);
 assert.match(auth,/crypto\.subtle\.digest\('SHA-256'/);
 assert.match(auth,/code_challenge_method','S256'/);
 assert.match(auth,/response_type','code'/);
 assert.match(auth,/sessionStorage\.removeItem\(KEY\)/);
 assert.match(auth,/history\.replaceState\(null,'',location\.pathname\)/);
 assert.match(auth,/code_verifier:tx\.verifier/);
 assert.match(auth,/url\.searchParams\.set\('state',state\)/);
 assert.doesNotMatch(auth,/client_secret|localStorage\./);
});
test('Google identity is never implicitly accepted as QualityRAG authorization',()=>{
 assert.match(auth,/verifyRegistryToken/);
 assert.match(auth,/\/v1\/drives\/google\/status/);
 assert.match(auth,/\/v1\/state/);
 assert.match(auth,/res\.status===401\|\|res\.status===403/);
 assert.match(login,/await verifyRegistryToken\(token\)/);
 assert.match(login,/Your organization's Google account|organization's Google account/);
});
