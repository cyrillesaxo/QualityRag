/** Optional direct adapter to the canonical APX TypeScript packages.
 *
 * Built APX packages must be installed/mounted by the host. No internal
 * substitute executes when they are unavailable. This bridge does not grant
 * QualityRag admission or assess source/PackSpec authority.
 */
import {access, realpath} from 'node:fs/promises';
import {join, isAbsolute} from 'node:path';
import {pathToFileURL} from 'node:url';

export class APXUnavailable extends Error {
  constructor(message) { super(message); this.name = 'APXUnavailable'; }
}

async function importEngine(root, folder) {
  const filename = join(root, folder, 'dist', 'index.js');
  try {
    await access(filename);
    const resolved = await realpath(filename);
    if (!resolved.startsWith(root + '/')) {
      throw new APXUnavailable('APX package resolves outside configured root');
    }
    return await import(pathToFileURL(resolved).href);
  } catch (error) {
    if (error instanceof APXUnavailable) throw error;
    throw new APXUnavailable('Canonical APX engine not available: ' + folder +
      ' (build the original APX workspace and configure APX_PACKAGES_ROOT)');
  }
}

export async function loadNativeApx(baseDir = process.env.APX_PACKAGES_ROOT) {
  if (!baseDir || !isAbsolute(baseDir)) {
    throw new APXUnavailable('An absolute APX_PACKAGES_ROOT is required');
  }
  const root = await realpath(baseDir).catch(() => {
    throw new APXUnavailable('Configured APX workspace does not exist');
  });
  const [wbc, hcr, rcoc] = await Promise.all([
    importEngine(root, 'apx-wbc'),
    importEngine(root, 'apx-hcr'),
    importEngine(root, 'apx-rcoc'),
  ]);
  if (typeof wbc.reduceToWMin !== 'function' ||
      typeof wbc.verifyWMin !== 'function' ||
      typeof hcr.recoverConstraintFiber !== 'function' ||
      typeof rcoc.compareSemanticAssuranceSnapshots !== 'function') {
    throw new APXUnavailable('Canonical APX export contract mismatch');
  }
  return Object.freeze({
    source: 'CANONICAL_APX_WORKSPACE_BUILD',
    reduceWitnesses: (witnessIds, decisionFn) => {
      if (!Array.isArray(witnessIds) || typeof decisionFn !== 'function')
        throw new TypeError('WBC needs an authenticated host decision oracle');
      const result = wbc.reduceToWMin({witnessIds, decisionFn});
      const verified = wbc.verifyWMin({
        wMin: result.w_min, referenceVerdict: result.referenceVerdict, decisionFn,
      });
      if (!verified.verdictPreserved || !verified.loadBearing)
        throw new Error('Canonical WBC verdict preservation failed');
      return {result, verified, admission: 'INCONCLUSIVE'};
    },
    recover: (input) => ({
      receipt: hcr.recoverConstraintFiber(input), admission: 'INCONCLUSIVE',
    }),
    compare: (before, after, options = {}) => ({
      receipt: rcoc.compareSemanticAssuranceSnapshots(before, after, options),
      admission: 'INCONCLUSIVE',
    }),
  });
}
