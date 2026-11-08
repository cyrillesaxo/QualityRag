import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {buildSourceGroundedAnswer} from '../src/source-grounded-answer.js';

const digest=x=>createHash('sha256').update(x,'utf8').digest('hex');
const source='google_drive/'+'a'.repeat(32);
const primary='Reimbursement requires prior approval.';
const exception='Except emergencies, which must be reported within 24 hours.';
const policy={id:'claims-policy',version:'1',requirements:[
 {id:'primary',min_independent_sources:1},
 {id:'exception',min_independent_sources:1}
]};
const witnesses=[
 {sourceId:source,requirementId:'primary',lineNumber:1,
  lineSha256:digest(primary),status:'SUPPORTS'},
 {sourceId:source,requirementId:'exception',lineNumber:2,
  lineSha256:digest(exception),status:'SUPPORTS'}
];
const verifiedLines=[
 {sourceId:source,requirementId:'primary',lineNumber:1,
  lineSha256:digest(primary),text:primary,
  context:[{lineNumber:2,text:exception}]},
 {sourceId:source,requirementId:'exception',lineNumber:2,
  lineSha256:digest(exception),text:exception,
  context:[{lineNumber:1,text:primary}]}
];
const build=(changes={})=>buildSourceGroundedAnswer({
 policy,witnesses,verifiedLines,...changes
});

test('all signed requirements and exception text appear unchanged, without AI paraphrase',()=>{
 const result=build();
 assert.equal(result.schema,'qualityrag.source-grounded-extract/v1');
 assert.ok(result.answer.includes(primary));
 assert.ok(result.answer.includes(exception));
 assert.ok(result.answer.indexOf('Requirement: primary')<
   result.answer.indexOf('Requirement: exception'));
 assert.equal(result.coverage.requiredPolicyObligations,2);
 assert.equal(result.coverage.humanSignedSupports,2);
 assert.equal(result.coverage.allSignedAnchorsIncluded,true);
 assert.equal(result.coverage.fullDocumentExaminedForExceptions,false);
 assert.equal(result.assertions.freeFormAnswerEntailmentVerified,false);
 assert.equal(result.assertions.documentWideCompletenessVerified,false);
 assert.equal(result.assertions.modelGeneratedParaphrase,false);
 assert.equal(result.sections[0].adjacentContext[0].semantics,'UNREVIEWED_ADJACENT_CONTEXT');
});
test('omitted exception obligation fails closed',()=>{
 assert.throws(()=>build({witnesses:witnesses.slice(0,1),
  verifiedLines:verifiedLines.slice(0,1)}),
  /PROTECTED_GROUNDED_REVIEW_INCOMPLETE/);
});
test('contradicted and unknown obligations cannot be presented as reviewed supports',()=>{
 for(const status of ['CONTRADICTS','UNKNOWN'])
   assert.throws(()=>build({witnesses:[
     witnesses[0],{...witnesses[1],status}
   ]}),/PROTECTED_GROUNDED_REVIEW_INCOMPLETE/);
});
test('tampered, invented, duplicate and missing source anchors fail closed',()=>{
 const changed=structuredClone(verifiedLines);
 changed[1].text='No emergency exception applies.';
 assert.throws(()=>build({verifiedLines:changed}),/PROTECTED_GROUNDED_SOURCE_CHANGED/);
 const injected=structuredClone(verifiedLines);
 injected[1].sourceId='google_drive/'+'b'.repeat(32);
 assert.throws(()=>build({verifiedLines:injected}),/PROTECTED_GROUNDED_UNAPPROVED_ANCHOR/);
 const duplicate=structuredClone(verifiedLines);
 duplicate[1]={...duplicate[0]};
 assert.throws(()=>build({verifiedLines:duplicate}),/PROTECTED_GROUNDED_UNAPPROVED_ANCHOR/);
 const displaced=structuredClone(verifiedLines);
 displaced[1].context[0].lineNumber=300;
 assert.throws(()=>build({verifiedLines:displaced}),/PROTECTED_GROUNDED_CONTEXT_INVALID/);
 const missing=structuredClone(verifiedLines);
 missing.pop();
 assert.throws(()=>build({verifiedLines:missing}),/PROTECTED_GROUNDED_COVERAGE_INVALID/);
});
test('excessive lines refuse rather than truncate exceptions',()=>{
 const long='x'.repeat(1150);
 const eightPolicy={id:'many',version:'1',requirements:
   Array.from({length:8},(_,i)=>({id:'r'+i,min_independent_sources:1}))};
 const eightWitnesses=Array.from({length:8},(_,i)=>({
   sourceId:source,requirementId:'r'+i,lineNumber:i+1,
   lineSha256:digest(long),status:'SUPPORTS'
 }));
 const eightLines=eightWitnesses.map(w=>({
   ...w,text:long,context:[
     {lineNumber:w.lineNumber===1?2:w.lineNumber-1,text:long},
     {lineNumber:w.lineNumber+1,text:long}
   ]
 }));
 // The first line has one neighbor to keep context well-formed.
 eightLines[0].context=[{lineNumber:2,text:long}];
 assert.throws(()=>buildSourceGroundedAnswer({
   policy:eightPolicy,witnesses:eightWitnesses,verifiedLines:eightLines
 }),/PROTECTED_GROUNDED_OUTPUT_TOO_LARGE/);
});
