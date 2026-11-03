import test from 'node:test';
import assert from 'node:assert/strict';
import {loadNativeSemanticComparator} from '../rct_apx_source_spans_native.mjs';

if (!process.env.APX_PACKAGES_ROOT)
  throw new Error('Actual APX package build required; no native test skip');

const comparator=await loadNativeSemanticComparator();
const key=new Uint8Array(32).fill(41);
const inspect=(beforeText,afterText)=>comparator.inspect({
  beforeText,afterText,hmacKey:key});

test('canonical APX detects nursing NOT deletion', () => {
  const result=inspect(
    'The nurse must NOT administer the medication.',
    'The nurse must administer the medication.');
  assert.equal(result.verdict,'REFUSE');
  assert.ok(result.observed_changes.some(x=>x.kind==='NEGATION'));
  assert.equal(result.qualityrag_admission,'INCONCLUSIVE');
  assert.equal(result.can_generate,false);
});

test('canonical APX detects HVAC exception deletion', () => {
  const result=inspect(
    'Disconnect power before servicing unless the system requires a live diagnostic.',
    'Disconnect power before servicing.');
  assert.equal(result.verdict,'REFUSE');
  assert.ok(result.observed_changes.some(x=>x.kind==='SCOPE'));
});

test('canonical APX detects altered permit duration', () => {
  const result=inspect(
    'The applicant must wait at least 12 months before the test.',
    'The applicant must wait at least 6 months before the test.');
  assert.equal(result.verdict,'REFUSE');
  assert.ok(result.observed_changes.some(x=>x.kind==='NUMBER'));
});

test('identical source remains inconclusive, not admitted', () => {
  const text='Refunds are allowed only if submitted within 30 days.';
  const result=inspect(text,text);
  assert.equal(result.verdict,'INCONCLUSIVE');
  assert.equal(result.source_authority,'UNVERIFIED_HEURISTIC');
  assert.equal(result.semantic_completeness,'UNKNOWN');
});

test('invalid host key and source input do not leak content', () => {
  assert.throws(()=>comparator.inspect({
    beforeText:'must not',afterText:'must',hmacKey:new Uint8Array(1)}),
    TypeError);
  const result=inspect('The nurse must not proceed.',
                       'The nurse must proceed.');
  assert.ok(!Object.prototype.hasOwnProperty.call(result,'beforeText'));
  assert.ok(!Object.prototype.hasOwnProperty.call(result,'hmacKey'));
  assert.ok(!Object.prototype.hasOwnProperty.call(result,'sourceFingerprint'));
  assert.equal(JSON.stringify(result).includes('The nurse'),false);
});
