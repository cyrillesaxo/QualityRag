/** Real canonical APX engine behavior checks.
 *
 * Requires APX_PACKAGES_ROOT pointing to independently built original APX
 * packages. Never substitutes mock implementations or skips when unavailable.
 * A passing test attests exercised examples ONLY, not general APX parity.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {loadNativeApx} from '../rct_apx_native.mjs';

const root=process.env.APX_PACKAGES_ROOT;
if (!root) {
  throw new Error('APX_PACKAGES_ROOT required: native APX parity cannot silently skip');
}
const engines=await loadNativeApx(root);

test('real WBC retains the exact decision and checks load bearing set', () => {
  const adjudicator=(active) => {
    const set=new Set(active);
    return set.has('source-A') && set.has('source-B') ? 'INCONCLUSIVE' : 'REFUSE';
  };
  const w=engines.reduceWitnesses(
    ['source-A','source-B','source-C','source-C'], adjudicator);
  assert.equal(w.admission,'INCONCLUSIVE');
  assert.equal(w.result.referenceVerdict,'INCONCLUSIVE');
  assert.deepEqual(w.result.w_min,['source-A','source-B']);
  assert.deepEqual(w.result.eliminated,['source-C']);
  assert.equal(w.verified.verdictPreserved,true);
  assert.equal(w.verified.loadBearing,true);
});

test('real HCR identifies within finite registry on authorized observation', () => {
  const assessment=engines.recover({
    subjectId:'synthetic-hcr',
    hypotheses:[
      {id:'a',rules:[{claim:'condition-X',on:'ESTABLISHED',effect:'SUPPORT',
                      authorities:['authority-1']}]},
      {id:'b',rules:[{claim:'condition-X',on:'ESTABLISHED',effect:'ELIMINATE',
                      authorities:['authority-1']}]},
    ],
    observations:[{id:'witness-X',claim:'condition-X',status:'ESTABLISHED',
                   authority:'authority-1',source:'synthetic#hcr'}],
    probes:[],
  });
  assert.equal(assessment.admission,'INCONCLUSIVE');
  assert.equal(assessment.receipt.schema,'apx.hcr/v0.1');
  assert.equal(assessment.receipt.identifiability.status,
               'IDENTIFIED_WITHIN_REGISTRY');
  assert.deepEqual(assessment.receipt.fiber.map(item=>item.id),['a']);
  assert.deepEqual(assessment.receipt.eliminated.map(item=>item.id),['b']);
  assert.notEqual(assessment.receipt.admission.status,'ADMIT');
});

test('real HCR refuses unauthorized evidence effects', () => {
  const assessment=engines.recover({
    subjectId:'synthetic-untrusted-hcr',
    hypotheses:[{id:'a',rules:[{claim:'X',on:'ESTABLISHED',
                               effect:'ELIMINATE',authorities:['trusted']}]},
                {id:'b',rules:[]}],
    observations:[{claim:'X',status:'ESTABLISHED',authority:'unknown'}],
    probes:[],
  });
  assert.equal(assessment.receipt.fiber.length,2);
  assert.equal(assessment.admission,'INCONCLUSIVE');
});

test('real RCOC detects observed deterioration but never authorizes admission', () => {
  const before={
    schema:'apx.semantic-assurance-snapshot/v0.1',
    revision:'a',journey:'synthetic',
    coordinates:[{id:'G1',applicable:true,deltaRef:0.8}],
  };
  const after={
    schema:'apx.semantic-assurance-snapshot/v0.1',
    revision:'b',journey:'synthetic',
    coordinates:[{id:'G1',applicable:true,deltaRef:0.2}],
  };
  const evaluation=engines.compare(before,after,{transformationOrder:['G1']});
  assert.equal(evaluation.receipt.schema,'apx.rcoc-semantic-diff/v0.1');
  assert.equal(evaluation.receipt.status,'REVIEW_REQUIRED');
  assert.equal(evaluation.receipt.firstDeparture.coordinate,'G1');
  assert.equal(evaluation.admission,'INCONCLUSIVE');
});

test('real RCOC remains bounded on identical semantic receipts', () => {
  const snapshot={
    schema:'apx.semantic-assurance-snapshot/v0.1',
    revision:'a',coordinates:[{id:'G1',applicable:true,deltaRef:0.8}],
  };
  const evaluation=engines.compare(snapshot,snapshot);
  assert.equal(evaluation.receipt.status,'NO_MATERIAL_SEMANTIC_MOVEMENT_ESTABLISHED');
  assert.equal(evaluation.admission,'INCONCLUSIVE');
});
