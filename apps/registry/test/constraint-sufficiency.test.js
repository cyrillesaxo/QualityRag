import test from 'node:test';
import assert from 'node:assert/strict';
import {scanReviewedSourceConstraints} from '../src/constraint-sufficiency.js';

const source='google_drive/'+'a'.repeat(32);
const other='google_drive/'+'b'.repeat(32);
const basic={sourceId:source,lineNumber:1,status:'SUPPORTS'};
const lines=[
 'Prior approval is required.',
 'Payment is processed on Tuesdays.',
 'The claim requires a completed form.',
 'The reviewer validates the amount.',
 'Managers verify the department.',
 'A second approval might be necessary.',
 'The document is stored for six months.',
 'Except emergencies, which must be reported within 24 hours.'
];
const scan=(values=lines,reviews=[basic],extras={})=>
 scanReviewedSourceConstraints({sources:[{sourceId:source,lines:values}],
   witnesses:reviews,...extras});

test('flags a distant exception outside the one-line context, with no source text',()=>{
 const r=scan();
 assert.equal(r.schema,'qualityrag.constraint-signal-scan/v1');
 assert.equal(r.status,'UNREVIEWED_LEXICAL_SIGNALS');
 assert.equal(r.candidateCount,1);
 assert.deepEqual(r.candidates,[{sourceId:source,lineNumber:8,
   category:'EXCEPTION',reviewStatus:'NOT_SIGNED_FOR_THIS_SOURCE_LINE'}]);
 assert.equal(r.linesScanned,8);
 assert.equal(r.sourcesScanned,1);
 assert.equal(r.wholeFolderScanned,false);
 assert.equal(r.documentWideSemanticCompletenessVerified,false);
 assert.equal(r.sourceTextIncluded,false);
 assert.ok(!JSON.stringify(r).includes(lines[7]));
});
test('reviewed signed exception is no longer an unreviewed lexical signal',()=>{
 const r=scan(lines,[basic,{sourceId:source,lineNumber:8,status:'SUPPORTS'}]);
 assert.equal(r.status,'NO_UNREVIEWED_LEXICAL_SIGNALS');
 assert.equal(r.candidateCount,0);
 assert.equal(r.reviewedSignalCount,1);
 assert.equal(r.documentWideSemanticCompletenessVerified,false);
});
test('UNKNOWN and CONTRADICTS are not misrepresented as an approved source review',()=>{
 for(const status of ['UNKNOWN','CONTRADICTS']){
   const r=scan(lines,[basic,{sourceId:source,lineNumber:8,status}]);
   assert.equal(r.candidateCount,1);
 }
});
test('conditional, override, and negative language are candidates, not proven contradictions',()=>{
 const testLines=['Unless the patient is hospitalized, authorization is required.',
   'Notwithstanding the preceding clause, renewal may be required.',
   'Service is subject to prior authorization.',
   'This does not apply to emergency claims.'];
 const r=scan(testLines,[basic]);
 assert.deepEqual(r.candidates.map(x=>x.category),
   ['CONDITIONAL','OVERRIDE','CONDITIONAL','NEGATION']);
 assert.equal(r.signalIsProvenException,false);
});
test('multiple files are scanned only when explicitly supplied, with bounded metadata',()=>{
 const r=scanReviewedSourceConstraints({sources:[
   {sourceId:other,lines:['Subject to bank approval']},
   {sourceId:source,lines:['Except during holidays']}
 ],witnesses:[{sourceId:source,lineNumber:1,status:'SUPPORTS'}]});
 assert.equal(r.sourcesScanned,2);
 assert.equal(r.reviewedSignalCount,1);
 assert.equal(r.candidateCount,1);
 assert.equal(r.candidates[0].sourceId,other);
 assert.equal(r.otherFilesMayContainUnknownConstraints,true);
});
test('many candidates are counted and truncation is made explicit',()=>{
 const r=scan(Array(70).fill('Unless a separate approval applies'),
   [basic],{maxCandidates:5});
 assert.equal(r.candidateCount,69);
 assert.equal(r.candidates.length,5);
 assert.equal(r.candidatesTruncated,true);
 assert.equal(r.status,'UNREVIEWED_LEXICAL_SIGNALS');
});
test('invalid and incomplete source records fail closed',()=>{
 assert.throws(()=>scanReviewedSourceConstraints({
   sources:[{sourceId:source,lines:[]}],witnesses:[basic]
 }),/PROTECTED_SUFFICIENCY_SOURCE_UNAVAILABLE/);
 assert.throws(()=>scanReviewedSourceConstraints({
   sources:[{sourceId:source,lines:['value']}],
   witnesses:[{sourceId:other,lineNumber:1,status:'SUPPORTS'}]
 }),/PROTECTED_SUFFICIENCY_SOURCE_UNAVAILABLE/);
 assert.throws(()=>scanReviewedSourceConstraints({
   sources:[{sourceId:source,lines:['value']},
     {sourceId:source,lines:['duplicated source']}],
   witnesses:[basic]
 }),/PROTECTED_SUFFICIENCY_SOURCE_UNAVAILABLE/);
 assert.throws(()=>scanReviewedSourceConstraints({
   sources:[{sourceId:source,lines:['value'.repeat(500)]}],
   witnesses:[basic]
 }),/PROTECTED_SUFFICIENCY_SOURCE_UNAVAILABLE/);
});
test('negative result is retained: a payer/payee swap has no signal and is not proven safe',()=>{
 const r=scan(['The hospital pays the insurer.'],[basic]);
 assert.equal(r.candidateCount,0);
 assert.equal(r.documentWideSemanticCompletenessVerified,false);
 assert.equal(r.signalIsProvenException,false);
});
