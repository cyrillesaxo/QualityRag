import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=path=>readFileSync(path,'utf8');

test('experimental signed admission is mounted only inside the existing opt-in UI',()=>{
 const main=read('apps/studio/src/main.tsx');
 assert.match(main,/VITE_QUALITYRAG_EXPERIMENTAL_STUDIO==='true'/);
 assert.match(main,/<ProtectedAdmissionAvailability token=\{token\}/);
 assert.match(main,/<CloudDrives/);
 assert.match(main,/<EnterpriseEngines/);
});
test('protected admission requires live scoped server enforcement and handles disabled states',()=>{
 const gate=read('apps/studio/src/ProtectedAdmissionAvailability.tsx');
 assert.match(gate,/\/v1\/evidence\/enforcement/);
 assert.match(gate,/data\.protected===true/);
 assert.match(gate,/readiness==='unavailable'/);
 assert.match(gate,/readiness==='unprotected'/);
 assert.match(gate,/signal:abort\.signal/);
});
test('unsupported preview, governance and freeform delivery controls are not interactable',()=>{
 const protectedUI=read('apps/studio/src/ProtectedAdmission.tsx');
 assert.match(protectedUI,/const standalonePreviewAvailable=false/);
 assert.match(protectedUI,/const freeformGatewayAvailable=false/);
 assert.match(protectedUI,/disabled=\{!standalonePreviewAvailable\|\|busy\|\|revoked\}/);
 assert.match(protectedUI,/outcome\.verdict==='ADMIT'&&freeformGatewayAvailable/);
 const drive=read('apps/studio/src/DriveTrustControls.tsx');
 assert.match(drive,/const governedChallengeAvailable=false/);
 assert.match(drive,/if\(!governedChallengeAvailable\)/);
 assert.match(drive,/disabled=\{!governedChallengeAvailable/);
});
