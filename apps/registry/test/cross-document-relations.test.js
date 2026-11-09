import test from 'node:test';
import assert from 'node:assert/strict';
import {scanRelationshipConflicts} from '../src/cross-document-relations.js';
const a='google_drive/'+'a'.repeat(32);
const b='google_drive/'+'b'.repeat(32);
const c='google_drive/'+'c'.repeat(32);
const base=[{sourceId:a,lines:['The insurer must pay the hospital.']},
 {sourceId:b,lines:['The hospital must pay the insurer.']}];
const witness={sourceId:a,lineNumber:1,status:'SUPPORTS'};
const run=(sources=base,witnesses=[witness],options={})=>
 scanRelationshipConflicts({sources,witnesses,...options});

test('detects a cross-file payer/payee reversal without leaking named parties',()=>{
 const result=run();
 assert.equal(result.status,'POTENTIAL_CROSS_SOURCE_CONFLICTS');
 assert.equal(result.candidateCount,1);
 assert.equal(result.findings[0].category,'INVERSE_PAYER_PAYEE');
 assert.equal(result.findings[0].left.sourceId,a);
 assert.equal(result.findings[0].right.sourceId,b);
 assert.equal(result.findings[0].left.signedSupportingWitness,true);
 assert.equal(result.findings[0].right.signedSupportingWitness,false);
 assert.equal(result.sourceTextIncluded,false);
 assert.equal(result.actorNamesIncluded,false);
 assert.equal(result.semanticCompletenessVerified,false);
 assert.equal(result.crossFileSemanticEntailmentVerified,false);
 assert.ok(!JSON.stringify(result).includes('insurer'));
 assert.ok(!JSON.stringify(result).includes('hospital'));
});

test('opposite polarity for same direction is an unresolved candidate',()=>{
 const result=run([
   {sourceId:a,lines:['The insurer shall pay the hospital.']},
   {sourceId:b,lines:['The insurer shall not pay the hospital.']}
 ]);
 assert.equal(result.candidateCount,1);
 assert.equal(result.findings[0].category,'POLARITY_CONFLICT');
});

test('signing both incompatible lines does not silently resolve the relationship',()=>{
 const result=run(base,[witness,{sourceId:b,lineNumber:1,status:'SUPPORTS'}]);
 assert.equal(result.candidateCount,1);
 assert.equal(result.bothSignedConflicts,1);
 assert.equal(result.findings[0].reviewState,
   'NEEDS_EXPLICIT_CROSS_SOURCE_ADJUDICATION');
});

test('unreviewed and UNKNOWN sources still produce candidates',()=>{
 const result=run(base,[{...witness,status:'UNKNOWN'}]);
 assert.equal(result.candidateCount,1);
 assert.equal(result.findings[0].left.signedSupportingWitness,false);
});

test('same file, unsupported syntax, and distinct legitimate directions are not asserted inconsistent',()=>{
 const same=run([{sourceId:a,lines:[
   'The insurer pays the hospital.','The hospital pays the insurer.'
 ]}],[witness]);
 assert.equal(same.candidateCount,0);
 const inconclusive=run([
   {sourceId:a,lines:['The insurer transfers funds to the hospital.']},
   {sourceId:b,lines:['The hospital transfers funds to the insurer.']}
 ]);
 assert.equal(inconclusive.candidateCount,0);
 assert.equal(inconclusive.semanticCompletenessVerified,false);
 const different=run([
   {sourceId:a,lines:['The insurer pays the hospital.']},
   {sourceId:b,lines:['The hospital pays the vendor.']}
 ]);
 assert.equal(different.candidateCount,0);
});

test('candidate pagination counts omitted matches and does not weaken release denial',()=>{
 const docs=[
   {sourceId:a,lines:Array(5).fill('The insurer pays the hospital.')},
   {sourceId:b,lines:Array(5).fill('The hospital pays the insurer.')}
 ];
 const result=run(docs,[witness],{maxFindings:3});
 assert.equal(result.candidateCount,25);
 assert.equal(result.findings.length,3);
 assert.equal(result.findingsTruncated,true);
});

test('explicit graph-size limit and missing or duplicate indexed sources fail closed',()=>{
 assert.throws(()=>run([
   {sourceId:a,lines:Array(257).fill('The insurer pays the hospital.')}
 ]),/PROTECTED_RELATION_EDGE_LIMIT/);
 assert.throws(()=>run([{sourceId:a,lines:['The insurer pays the hospital.']}],
   [{sourceId:b,lineNumber:1,status:'SUPPORTS'}]),
   /PROTECTED_RELATION_SOURCE_INVALID/);
 assert.throws(()=>run([null]),/PROTECTED_RELATION_SOURCE_INVALID/);
 assert.throws(()=>run([base[0],base[0]]),/PROTECTED_RELATION_SOURCE_INVALID/);
});

test('functional-sister receive form normalizes to payer and payee roles',()=>{
 const result=run([
   {sourceId:a,lines:['The insurer must pay the hospital.']},
   {sourceId:b,lines:['The insurer receives payment from the hospital.']}
 ]);
 assert.equal(result.candidateCount,1);
 assert.equal(result.findings[0].category,'INVERSE_PAYER_PAYEE');
 assert.equal(result.grammar,'BOUNDED_ENGLISH_PAYMENT_ROLE_NORMALIZATION_V2');
 assert.ok(!JSON.stringify(result).includes('insurer'));
 assert.ok(!JSON.stringify(result).includes('hospital'));
});

test('negative payment-from construction conflicts with positive payment role',()=>{
 const result=run([
   {sourceId:a,lines:['The insurer pays the hospital.']},
   {sourceId:b,lines:['Payment from insurer to hospital is prohibited.']}
 ]);
 assert.equal(result.candidateCount,1);
 assert.equal(result.findings[0].category,'POLARITY_CONFLICT');
});

test('equivalent receive construction is not a conflict',()=>{
 const result=run([
   {sourceId:a,lines:['The insurer pays the hospital.']},
   {sourceId:b,lines:['The hospital receives payment from the insurer.']}
 ]);
 assert.equal(result.candidateCount,0);
 assert.equal(result.semanticCompletenessVerified,false);
});

test('unsupported transfer paraphrase and conditional receipt remain explicitly unproven',()=>{
 const result=run([
   {sourceId:a,lines:['The insurer transfers funds to the hospital.']},
   {sourceId:b,lines:['The hospital may receive payment from the insurer.']}
 ]);
 assert.equal(result.candidateCount,0);
 assert.equal(result.semanticCompletenessVerified,false);
 assert.equal(result.supportedPatternCoverageOnly,true);
});
