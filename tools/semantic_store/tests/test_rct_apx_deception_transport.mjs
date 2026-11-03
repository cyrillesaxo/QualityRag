import test from 'node:test';
import assert from 'node:assert/strict';
import {loadNativeDeceptionCensus,NativeDeceptionUnavailable}
  from '../rct_apx_deception_native.mjs';

test('native D15 cannot be silently replaced by a stub',async()=>{
  await assert.rejects(loadNativeDeceptionCensus(''),
                       NativeDeceptionUnavailable);
  await assert.rejects(loadNativeDeceptionCensus('/missing/original/apx'),
                       NativeDeceptionUnavailable);
});
