import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync('apps/studio/src/RegistryReadiness.tsx','utf8');
const app=readFileSync('apps/studio/src/main.tsx','utf8');
test('pilot diagnostic checks only same-origin readiness without credentials',()=>{
 assert.match(source,/fetch\('\/ready'/);
 assert.match(source,/cache:'no-store'/);
 assert.match(source,/redirect:'error'/);
 assert.doesNotMatch(source,/Authorization|Bearer|localStorage|sessionStorage/);
 assert.match(source,/response\.status===404/);
 assert.match(source,/application\/json/);
 assert.match(source,/typeof \(data as \{ready:unknown\}\)\.ready!=='boolean'/);
 assert.match(source,/Authentication, OAuth, and authorization remain unverified/);
});
const login=readFileSync('apps/studio/src/StudioLogin.tsx','utf8');
test('no public bearer-token form: sign-in first, manual tokens only behind an explicit operator flag',()=>{
 // The dashboard is unreachable without a verified token; the login page comes first.
 assert.match(app,/if\(!token\)return <StudioLogin onAuthenticated=\{setToken\}\/>/);
 assert.doesNotMatch(app,/Registry bearer token/);
 // A manual token field exists only when the operator flag is set, with its own warning.
 assert.match(login,/VITE_QUALITYRAG_ALLOW_MANUAL_TOKEN==='true'/);
 assert.match(login,/\{manualAllowed&&<details/);
 assert.match(login,/Never paste production credentials into an unverified deployment/);
 assert.match(login,/type="password" autoComplete="off"/);
 // The readiness diagnostic is shown on the login page, before any credential is entered.
 assert.ok(login.indexOf('<RegistryReadiness/>')>0);
});
