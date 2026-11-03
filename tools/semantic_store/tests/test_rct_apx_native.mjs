import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {loadNativeApx, APXUnavailable} from '../rct_apx_native.mjs';

test('missing canonical APX workspace fails without fallback', async () => {
  await assert.rejects(loadNativeApx(''), APXUnavailable);
  await assert.rejects(loadNativeApx('/definitely-not-present/qualityrag-apx'), APXUnavailable);
});

test('adapter validates bounded export interface with transport-only stubs', async () => {
  // These are interface stubs only. They DO NOT prove parity with APX algorithms.
  const root=await mkdtemp(join(tmpdir(),'rct-apx-interface-'));
  try {
    for (const [name,source] of Object.entries({
      'apx-wbc': `export const reduceToWMin = ({witnessIds, decisionFn}) =>
        ({w_min:witnessIds, referenceVerdict:decisionFn(witnessIds), eliminated:[]});
        export const verifyWMin = () => ({verdictPreserved:true,loadBearing:true});`,
      'apx-hcr': `export const recoverConstraintFiber = input =>
        ({schema:'apx.hcr/v0.1', engine:'HCR', subject_id:input.subjectId});`,
      'apx-rcoc': `export const compareSemanticAssuranceSnapshots = () =>
        ({schema:'apx.rcoc-semantic-diff/v0.1',status:'INCOMPARABLE'});`,
    })) {
      const dir=join(root,name);
      await mkdir(join(dir,'dist'),{recursive:true});
      await writeFile(join(dir,'package.json'),JSON.stringify({type:'module'}));
      await writeFile(join(dir,'dist','index.js'),source);
    }
    const adapter=await loadNativeApx(root);
    assert.equal(adapter.source,'CANONICAL_APX_WORKSPACE_BUILD');
    assert.equal(adapter.reduceWitnesses(['w1'],()=> 'INCONCLUSIVE').admission,'INCONCLUSIVE');
    assert.equal(adapter.recover({subjectId:'test'}).admission,'INCONCLUSIVE');
    assert.equal(adapter.compare({},{}).receipt.status,'INCOMPARABLE');
    assert.throws(()=>adapter.reduceWitnesses(['w1'],null),TypeError);
  } finally {
    await rm(root,{recursive:true,force:true});
  }
});
