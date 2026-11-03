/** QualityRag adapter around ORIGINAL APX 15-cell D15 census.
 *
 * No reimplementation of families, axes, normalizer, or gate priority. Only
 * built original apx-evidence module may supply a diagnostic. Even APX
 * "ADMITTED" is not QualityRag semantic admission or FF-RCT compression.
 */
import {realpath} from 'node:fs/promises';
import {isAbsolute,join,relative} from 'node:path';
import {pathToFileURL} from 'node:url';

export class NativeDeceptionUnavailable extends Error {
  constructor(message){super(message);this.name='NativeDeceptionUnavailable';}
}

export async function loadNativeDeceptionCensus(root=process.env.APX_PACKAGES_ROOT){
  if (!root || !isAbsolute(root))
    throw new NativeDeceptionUnavailable('Absolute trusted APX_PACKAGES_ROOT required');
  let trusted,filename;
  try {
    trusted=await realpath(root);
    filename=await realpath(join(trusted,'apx-evidence','dist','index.js'));
  } catch {
    throw new NativeDeceptionUnavailable('Original APX evidence package is not compiled');
  }
  const sub=relative(trusted,filename);
  if (sub.startsWith('..') || isAbsolute(sub))
    throw new NativeDeceptionUnavailable('Original APX evidence module escaped trust root');
  let engine;
  try {
    engine=await import(pathToFileURL(filename).href);
  } catch {
    throw new NativeDeceptionUnavailable('Original APX deception engine failed to load');
  }
  if (typeof engine.buildDeception15Gate !== 'function'
      || typeof engine.deception15CellCatalog !== 'function')
    throw new NativeDeceptionUnavailable('Original APX D15 exports are missing');
  const canonical=engine.deception15CellCatalog();
  if (!Array.isArray(canonical) || canonical.length!==15
      || new Set(canonical.map(c=>c.id)).size!==15)
    throw new NativeDeceptionUnavailable('Original D15 catalog violates 15-cell contract');

  return Object.freeze({
    engine:'ORIGINAL_APX_EVIDENCE_D15',
    inspect:({subjectId,evidence})=>{
      if (typeof subjectId!=='string' || !subjectId || subjectId.length>128
          || !Array.isArray(evidence) || evidence.length>100
          || evidence.some(row=>!row || typeof row!=='object'
            || !['PASS','FAIL','INCONCLUSIVE','UNTESTED'].includes(row.status)
            || !canonical.some(c=>c.id===row.id)
            || !Array.isArray(row.evidenceRefs)
            || row.evidenceRefs.some(ref=>typeof ref!=='string'||!ref||ref.length>128)))
        throw new TypeError('Bounded explicit canonical D15 evidence required');
      const declared=evidence.map(row=>{
        const cell=canonical.find(c=>c.id===row.id);
        return {
          family:cell.family,axis:cell.axis,status:row.status,
          evidenceRefs:row.evidenceRefs,
        };
      });
      const gate=engine.buildDeception15Gate({
        subjectId,evidence:declared,requireAllCells:true});
      if (gate.schema!=='apx.deception-census/v0.1' || gate.cells.length!==15
          || gate.require_all_cells!==true)
        throw new Error('Original APX D15 result violates full-census contract');
      return {
        schema:'qualityrag.native-d15-diagnostics/v1',
        original_engine_schema:gate.schema,
        cells:gate.cells.map(c=>({id:c.id,status:c.status,
          evidence_refs:c.evidenceRefs})),
        passed_cells:gate.passed_cells,
        failed_cells:gate.failed_cells,
        inconclusive_cells:gate.inconclusive_cells,
        untested_cells:gate.untested_cells,
        raw_apx_gate_status:gate.status,
        verdict:gate.failed_cells.length>0?'REFUSE':'INCONCLUSIVE',
        coverage:gate.coverage,
        compression_authorized:false,
        semantic_completeness:'UNKNOWN',
        qualityrag_admission:'INCONCLUSIVE',
        can_generate:false,
        boundary:'EVIDENCE_STATUS_DECLARED_BY_HOST_NOT_AUTHENTICATED_OR_PROBED',
      };
    },
  });
}
