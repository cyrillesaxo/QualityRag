/** Optional canonical APX semantic-source comparator bridge.
 *
 * Loads the ORIGINAL separately compiled APX source-span implementation.
 * No copy of the compiler, regex rules, or fingerprints in QualityRag.
 * Never returns raw source text, HMAC key, matched quotes or fingerprints.
 */
import {createHash} from 'node:crypto';
import {realpath} from 'node:fs/promises';
import {relative, isAbsolute, join} from 'node:path';
import {pathToFileURL} from 'node:url';

export class CanonicalSemanticEngineUnavailable extends Error {
  constructor(message) {
    super(message);
    this.name='CanonicalSemanticEngineUnavailable';
  }
}

export async function loadNativeSemanticComparator(
  baseDir=process.env.APX_PACKAGES_ROOT
) {
  if (!baseDir || !isAbsolute(baseDir))
    throw new CanonicalSemanticEngineUnavailable(
      'Absolute APX_PACKAGES_ROOT path to original compiled APX packages required');
  let root, target;
  try {
    root=await realpath(baseDir);
    target=await realpath(join(root,'apx-epistemic','dist','semantic-source-spans.js'));
  } catch {
    throw new CanonicalSemanticEngineUnavailable(
      'Native APX semantic-source-spans package is not compiled');
  }
  const relativePath=relative(root,target);
  if (relativePath.startsWith('..') || isAbsolute(relativePath))
    throw new CanonicalSemanticEngineUnavailable(
      'APX source comparator escaped trusted package root');
  let implementation;
  try {
    implementation=await import(pathToFileURL(target).href);
  } catch {
    throw new CanonicalSemanticEngineUnavailable(
      'Original APX semantic-source comparator could not load');
  }
  if (typeof implementation.inspectSemanticTextTransition !== 'function')
    throw new CanonicalSemanticEngineUnavailable(
      'Original APX semantic-source export missing');
  return Object.freeze({
    engine:'ORIGINAL_APX_EPISTEMIC_SOURCE_SPANS',
    inspect: ({beforeText,afterText,hmacKey}) => {
      if (typeof beforeText!=='string' || typeof afterText!=='string' ||
          !(hmacKey instanceof Uint8Array) || hmacKey.byteLength<32)
        throw new TypeError('Exact texts and host-owned HMAC key required');
      const beforeDigest=createHash('sha256').update(beforeText,'utf8').digest('hex');
      const afterDigest=createHash('sha256').update(afterText,'utf8').digest('hex');
      const result=implementation.inspectSemanticTextTransition({
        beforeText,afterText,beforeDigest,afterDigest,hmacKey});
      if (result.schema!=='apx.semantic-text-transition/v0.1' ||
          !['REFUSE','INCONCLUSIVE'].includes(result.decision) ||
          result.sourceAuthority!=='UNVERIFIED_HEURISTIC' ||
          result.disclosure!=='NOT_AUTHORIZED')
        throw new Error('Canonical comparator contract mismatch');
      return Object.freeze({
        schema:'qualityrag.native-semantic-transition/v1',
        original_engine_schema:result.schema,
        source_sha256:beforeDigest,
        candidate_sha256:afterDigest,
        verdict:result.decision,
        observed_changes:result.changes.map(c=>({
          kind:c.kind,status:c.status})),
        source_authority:'UNVERIFIED_HEURISTIC',
        source_coverage:'BOUNDED_ENGLISH_PATTERNS',
        semantic_completeness:'UNKNOWN',
        qualityrag_admission:'INCONCLUSIVE',
        can_generate:false,
      });
    },
  });
}
