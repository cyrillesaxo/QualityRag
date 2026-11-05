// Host-owned runner; only pinned canonical source is compiled, never input text.
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {stripTypeScriptTypes} from 'node:module';

const pinned = {
  'packages/apx-wbc/src/index.ts': 'd25ab8317bfd37407fa68a711985e567317faf89f97fd3aadc65d2cd26217898',
  'packages/apx-rcoc/src/index.ts': '33bf9a1ffe7e18ac28e859de514bf1a3beb8e39f9c4014c6764cd32d224f110a',
  'packages/apx-rcoc/src/canonical-taxonomy.ts': '315588fd9efaf20b8021e7ca4da19066bfd86c3d22b82a40f088f0e5908eee97',
};
function source(name) {
  const bytes = readFileSync(resolve(process.argv[2], name));
  if (createHash('sha256').update(bytes).digest('hex') !== pinned[name]) throw Error('Source mismatch');
  return bytes.toString('utf8');
}
function compiled(text) {
  return 'data:text/javascript;base64,' + Buffer.from(stripTypeScriptTypes(text)).toString('base64');
}
let raw = '';
try {
  for await (const chunk of process.stdin) {
    raw += chunk.toString('utf8');
    if (Buffer.byteLength(raw) > 524288) throw Error('Input budget');
  }
  const input = JSON.parse(raw);
  let result;
  if (input.operation === 'WBC') {
    if (Object.keys(input).sort().join(',') !== 'decisions,operation,witnessIds'
        || !Array.isArray(input.witnessIds) || input.witnessIds.length > 8
        || !input.witnessIds.every(x => typeof x === 'string' && /^[A-Za-z0-9._-]{1,64}$/.test(x))
        || new Set(input.witnessIds).size !== input.witnessIds.length
        || !input.decisions || typeof input.decisions !== 'object' || Array.isArray(input.decisions)) throw Error('Witness input');
    const ids = [...input.witnessIds].sort();
    // Complete finite decision table: no implicit "unknown" default for omitted subsets.
    const expected = new Set();
    for (let mask=0; mask<(1<<ids.length); mask++) {
      expected.add(ids.filter((_, i) => mask & (1<<i)).join(','));
    }
    if (Object.keys(input.decisions).length !== expected.size
        || !Object.entries(input.decisions).every(([key,value]) => expected.has(key) && ['SAT','UNSAT','UNKNOWN'].includes(value))) throw Error('Incomplete decision table');
    const wbc = await import(compiled(source('packages/apx-wbc/src/index.ts')));
    const decisionFn = active => input.decisions[[...active].sort().join(',')];
    const reduced = wbc.reduceToWMin({witnessIds: ids, decisionFn});
    result = {...reduced, verification: wbc.verifyWMin({wMin: reduced.w_min, referenceVerdict: reduced.referenceVerdict, decisionFn})};
  } else if (input.operation === 'RCOC') {
    if (Object.keys(input).sort().join(',') !== 'after,before,operation') throw Error('RCOC input');
    for (const snap of [input.before,input.after]) {
      if (snap?.schema !== 'apx.semantic-assurance-snapshot/v0.1' || !Array.isArray(snap.coordinates) || snap.coordinates.length !== 12) throw Error('Complete coordinates required');
      const codes = new Set();
      for (const c of snap.coordinates) {
        const code = c.id ?? c.code;
        if (!/^G([1-9]|1[0-2])$/.test(code) || codes.has(code) || typeof c.applicable !== 'boolean') throw Error('Unknown coordinate applicability');
        codes.add(code);
        if (c.deltaRef !== undefined && c.deltaRef !== null && (typeof c.deltaRef !== 'number' || !Number.isFinite(c.deltaRef))) throw Error('Invalid displacement');
      }
    }
    const taxonomy = compiled(source('packages/apx-rcoc/src/canonical-taxonomy.ts'));
    // Change module resolution only; the canonical implementation is not rewritten.
    const text = source('packages/apx-rcoc/src/index.ts').replaceAll("'./canonical-taxonomy.js'", JSON.stringify(taxonomy));
    const rcoc = await import(compiled(text));
    result = rcoc.compareSemanticAssuranceSnapshots(input.before,input.after);
  } else throw Error('Unsupported native operation');
  process.stdout.write(JSON.stringify(result));
} catch {
  process.stderr.write('Canonical APX input or runtime unavailable.\n');
  process.exitCode = 2;
}
