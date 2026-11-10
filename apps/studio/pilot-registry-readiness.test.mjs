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
test('operator gets explicit credential safety warning and diagnostic ahead of token form',()=>{
 const diag=app.indexOf('<RegistryReadiness/>');
 const input=app.indexOf('Registry bearer token');
 assert.ok(diag>0&&input>diag);
 assert.match(app,/Do not paste an OIDC token or customer secrets/);
});
