import test from 'node:test';
import assert from 'node:assert/strict';
import {loadNativeSemanticComparator,CanonicalSemanticEngineUnavailable}
  from '../rct_apx_source_spans_native.mjs';

test('native semantic extractor never silently falls back', async () => {
  await assert.rejects(loadNativeSemanticComparator(''),
                       CanonicalSemanticEngineUnavailable);
  await assert.rejects(loadNativeSemanticComparator('/nonexistent/apx/packages'),
                       CanonicalSemanticEngineUnavailable);
});
