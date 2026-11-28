import test from 'node:test';
import assert from 'node:assert/strict';
import {questionTargetDigest} from '../src/guided-question-review.js';
// Shared independently computed Python SHA-256 vector. UTF-16 offsets.
const text='A😀B only if ready';
const target={ownerBinding:'a'.repeat(64),service:'lexyread',environment:'test',policyDigest:'b'.repeat(64),source:{id:'s',revision:'r',text},concept:{id:'c',revision:'v',label:'accept'},goalId:'g',operatorId:'boundary',evidence:{id:'e',obligationId:'o',kind:'boundary',consequence:'Preserve condition',proposedPremise:'Acceptance requires readiness.',sourceId:'s',revision:'r',conceptId:'c',semanticRevision:'v',start:0,end:18,quote:text,questionTarget:{operatorId:'boundary',obligationId:'o',arguments:[{role:'condition',start:13,end:18,quote:'ready'}]}},relation:{id:'rel',type:'requires',from:{start:0,end:4,quote:'A😀B'},cue:{start:5,end:12,quote:'only if'},to:{start:13,end:18,quote:'ready'}}};
const golden='98d39c11bd320cdecf9f6980e7921cb4bb5f0b1e51d1ca1a90b9cfff0deec576';
test('v2 target matches shared independently computed golden digest',()=>assert.equal(questionTargetDigest(target),golden));
test('premise changes, role substitution and relation reversal change digest',()=>{
 for(const mutate of [x=>{x.evidence.proposedPremise='Readiness is optional.';},x=>{x.evidence.questionTarget.arguments[0].role='alternative';},x=>{[x.relation.from,x.relation.to]=[x.relation.to,x.relation.from];}]){
  const copy=structuredClone(target);mutate(copy);assert.notEqual(questionTargetDigest(copy),golden);
 }
});
test('missing or blank premise cannot produce a digest',()=>{
 for(const premise of [undefined,'','  ']){const copy=structuredClone(target);copy.evidence.proposedPremise=premise;assert.throws(()=>questionTargetDigest(copy),/PROPOSED_PREMISE_REQUIRED/);}
});
