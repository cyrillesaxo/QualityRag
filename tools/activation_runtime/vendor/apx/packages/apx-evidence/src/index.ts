import type {Witness} from '@apx/contracts'

export type DeceptionSeverity='critical'|'high'|'medium'|'low'
export type DeceptionRule={
  id:string; distortion:string; severity:DeceptionSeverity; blockedScopes:string[];
  why:string; licensedClaim:string; probe:{id:string;goal:string};
}
export const DECEPTION_RULES:Readonly<Record<string,DeceptionRule>>=Object.freeze({
  NATIVE_PASS_AS_REGIME_PASS:{
    id:'NATIVE_PASS_AS_REGIME_PASS',distortion:'NATIVE_SUCCESS_LAUNDERING',severity:'high',
    blockedScopes:['business-admission','regulatory-use','decision-use'],
    why:'A successful native execution establishes that the platform completed the operation, not that governing business constraints survived.',
    licensedClaim:'The native platform operation completed under its own execution semantics.',
    probe:{id:'PROBE_GOVERNING_CONSTRAINTS',goal:'Evaluate the result against the consumer-scoped governing constraints.'},
  },
  SHARED_ORIGIN_AS_CORROBORATION:{
    id:'SHARED_ORIGIN_AS_CORROBORATION',distortion:'DEPENDENCE_LAUNDERING',severity:'high',
    blockedScopes:['independent-corroboration'],
    why:'Multiple observations derived from one unresolved origin do not provide independent corroboration.',
    licensedClaim:'The shared origin emitted multiple observations.',
    probe:{id:'PROBE_INDEPENDENT_CHANNEL',goal:'Obtain a proposition-relevant witness from an independent authority or channel.'},
  },
  STRUCTURE_AS_SEMANTICS:{
    id:'STRUCTURE_AS_SEMANTICS',distortion:'SEMANTIC_TYPE_ERASURE',severity:'high',
    blockedScopes:['business-admission','semantic-equivalence'],
    why:'Structural compatibility does not establish that business meaning, units, population or policy semantics are unchanged.',
    licensedClaim:'The compared artifacts are structurally compatible under the checked representation.',
    probe:{id:'PROBE_SEMANTIC_CONTRACT',goal:'Compare authoritative business definitions and scoped consumer requirements.'},
  },
  NARROW_SCOPE_AS_GLOBAL:{
    id:'NARROW_SCOPE_AS_GLOBAL',distortion:'SCOPE_INFLATION',severity:'medium',
    blockedScopes:['global-coverage','business-admission'],
    why:'Evidence from a narrow population cannot establish a broader population claim without a licensed transport argument.',
    licensedClaim:'The proposition held in the observed scope.',
    probe:{id:'PROBE_SCOPE_COVERAGE',goal:'Check the unobserved partitions, populations or segments required by the target scope.'},
  },
  STALE_AS_CURRENT:{
    id:'STALE_AS_CURRENT',distortion:'TEMPORAL_LAUNDERING',severity:'high',
    blockedScopes:['current-state','business-admission'],
    why:'A previously valid witness cannot establish the current state after its validity horizon or governing regime changes.',
    licensedClaim:'The proposition was supported at the witness observation time.',
    probe:{id:'PROBE_CURRENT_STATE',goal:'Re-observe the proposition under the current governing version and time window.'},
  },
})
export type DeceptionRisk={id:keyof typeof DECEPTION_RULES|string;severity?:DeceptionSeverity}
export type WitnessAudit={
  witnessId:string;requestedScope:string;
  classification:'CLEAN_WITNESS'|'WEAKENED_WITNESS'|'DECEPTIVE_WITNESS_CANDIDATE'|'UNKNOWN_WITNESS'|'ANTIWITNESS';
  distortions:Array<{id:string;distortion:string;severity:DeceptionSeverity;blocksRequestedScope:boolean;why:string;licensedClaim:string}>;
  recommendedProbe:(DeceptionRule['probe']&{triggeredBy:string})|null;
}
const severityWeight:Record<DeceptionSeverity,number>={critical:4,high:3,medium:2,low:1}
export function inspectWitness(input:{witness:Witness;requestedScope:string;risks?:DeceptionRisk[]}):WitnessAudit{
  const matched=(input.risks??[])
    .map(risk=>{const rule=DECEPTION_RULES[risk.id];return rule?{risk,rule}:null})
    .filter((entry):entry is {risk:DeceptionRisk;rule:DeceptionRule}=>entry!==null)
  const blocking=matched.filter(({rule})=>rule.blockedScopes.includes(input.requestedScope))
  const state=input.witness.state
  const classification:WitnessAudit['classification']=
    state==='contradicting'?'ANTIWITNESS':
    state==='unknown'?'UNKNOWN_WITNESS':
    blocking.length>0?'DECEPTIVE_WITNESS_CANDIDATE':
    matched.length>0?'WEAKENED_WITNESS':'CLEAN_WITNESS'
  const probeSource=[...(blocking.length?blocking:matched)].sort(
    (a,b)=>severityWeight[b.risk.severity??b.rule.severity]-severityWeight[a.risk.severity??a.rule.severity]
  )[0]
  return {
    witnessId:input.witness.id,requestedScope:input.requestedScope,classification,
    distortions:matched.map(({risk,rule})=>({
      id:rule.id,distortion:rule.distortion,severity:risk.severity??rule.severity,
      blocksRequestedScope:rule.blockedScopes.includes(input.requestedScope),
      why:rule.why,licensedClaim:rule.licensedClaim,
    })),
    recommendedProbe:probeSource?{...probeSource.rule.probe,triggeredBy:probeSource.rule.id}:null,
  }
}
export type WitnessGraph={nodes:Witness[];dependentGroups:Array<{key:string;witness_ids:string[];independence_credit:'withheld'}>}
export function buildWitnessGraph(witnesses:Witness[]):WitnessGraph{
  const groups=new Map<string,string[]>()
  for(const witness of witnesses){
    const key=witness.independence_key
    if(!key)continue
    const ids=groups.get(key)??[]
    ids.push(witness.id); groups.set(key,ids)
  }
  return {
    nodes:[...witnesses],
    dependentGroups:[...groups.entries()]
      .filter(([,ids])=>ids.length>1)
      .map(([key,ids])=>({key,witness_ids:[...ids].sort(),independence_credit:'withheld' as const}))
      .sort((a,b)=>a.key.localeCompare(b.key)),
  }
}

export const DECEPTION_CENSUS_FAMILIES=['DW','DD','DS'] as const
export const DECEPTION_CENSUS_AXES=['DEPTH','BREADTH','CHANNEL','FRAME','IMPLICATURE'] as const

export type DeceptionCensusFamily=typeof DECEPTION_CENSUS_FAMILIES[number]
export type DeceptionCensusAxis=typeof DECEPTION_CENSUS_AXES[number]
export type DeceptionCellStatus='PASS'|'FAIL'|'UNTESTED'|'INCONCLUSIVE'
export type DeceptionGateStatus='ADMITTED'|'REFUSED'|'INCONCLUSIVE'|'UNTESTED'

export type DeceptionCellEvidence={
  id?:string
  family?:string
  axis?:string
  mechanism?:string
  status?:string
  passed?:boolean
  evidenceRefs?:string[]
  evidence_refs?:string[]
  reason?:string
}

export type DeceptionCell={
  id:string
  family:DeceptionCensusFamily
  axis:DeceptionCensusAxis
  status:DeceptionCellStatus
  evidenceRefs:string[]
  reason:string
}

export type Deception15Gate={
  schema:'apx.deception-census/v0.1'
  subject_id:string
  status:DeceptionGateStatus
  require_all_cells:boolean
  cells:DeceptionCell[]
  passed_cells:string[]
  failed_cells:string[]
  inconclusive_cells:string[]
  untested_cells:string[]
  coverage:number
  allow_compression:boolean
}

const DECEPTION_MECHANISM_AXIS:Readonly<Record<string,DeceptionCensusAxis>>=Object.freeze({
  untraceable_depth:'DEPTH',
  inflated_scope:'BREADTH',
  loaded_channel:'CHANNEL',
  loaded_frame:'FRAME',
  unstated_implication:'IMPLICATURE',
})

const CELL_STATUS_PRIORITY:Readonly<Record<DeceptionCellStatus,number>>=Object.freeze({
  PASS:0,
  UNTESTED:1,
  INCONCLUSIVE:2,
  FAIL:3,
})

function cleanText(value:unknown):string{
  return String(value??'').replace(/\s+/g,' ').trim()
}

function normalizeCellStatus(value:unknown,passed?:boolean):DeceptionCellStatus{
  const status=cleanText(value).toUpperCase()
  if(status==='PASS'||status==='FAIL'||status==='UNTESTED'||status==='INCONCLUSIVE'){
    return status
  }
  if(passed===true)return 'PASS'
  if(passed===false)return 'FAIL'
  return 'UNTESTED'
}

function normalizeFamily(row:DeceptionCellEvidence):DeceptionCensusFamily|undefined{
  const declared=cleanText(row.family).toLowerCase()
  if(declared==='dw'||declared==='deceptive_witness')return 'DW'
  if(declared==='dd'||declared==='deceptive_divergence')return 'DD'
  if(declared==='ds'||declared==='deceptive_structural')return 'DS'

  const prefix=cleanText(row.id).toUpperCase().split(/[-_:]/)[0]
  if(prefix==='DW'||prefix==='DD'||prefix==='DS')return prefix
  return undefined
}

function normalizeAxis(row:DeceptionCellEvidence):DeceptionCensusAxis|undefined{
  const declared=cleanText(row.axis).toUpperCase()
  if((DECEPTION_CENSUS_AXES as readonly string[]).includes(declared)){
    return declared as DeceptionCensusAxis
  }

  const mechanism=cleanText(row.mechanism).toLowerCase()
  return DECEPTION_MECHANISM_AXIS[mechanism]
}

export function deceptionCellId(
  family:DeceptionCensusFamily,
  axis:DeceptionCensusAxis,
):string{
  return `${family}_${axis}`
}

export function deception15CellCatalog():Array<Pick<DeceptionCell,'id'|'family'|'axis'>>{
  return DECEPTION_CENSUS_FAMILIES.flatMap(family=>
    DECEPTION_CENSUS_AXES.map(axis=>({
      id:deceptionCellId(family,axis),
      family,
      axis,
    })),
  )
}

function mergeDeceptionCells(previous:DeceptionCell|undefined,next:DeceptionCell):DeceptionCell{
  if(!previous)return next

  const status=CELL_STATUS_PRIORITY[next.status]>CELL_STATUS_PRIORITY[previous.status]
    ? next.status
    : previous.status
  const evidenceRefs=[...new Set([...previous.evidenceRefs,...next.evidenceRefs])]
  const reasons=[...new Set([previous.reason,next.reason].filter(Boolean))]

  return {
    ...previous,
    status,
    evidenceRefs,
    reason:reasons.join(' | '),
  }
}

/**
 * Canonical APX 3x5 deception census.
 *
 * Verdict behavior is intentionally aligned with the mature LexyRead gate:
 * FAIL dominates, then INCONCLUSIVE, missing required cells remain UNTESTED,
 * and no evidence is ever inferred to PASS.
 */
export function buildDeception15Gate(input:{
  subjectId?:string
  evidence?:DeceptionCellEvidence[]
  requireAllCells?:boolean
}={}):Deception15Gate{
  const requireAllCells=input.requireAllCells!==false
  const byCell=new Map<string,DeceptionCell>()

  for(const row of input.evidence??[]){
    if(!row)continue
    const family=normalizeFamily(row)
    const axis=normalizeAxis(row)
    if(!family||!axis)continue

    const id=deceptionCellId(family,axis)
    const refs=(row.evidenceRefs??row.evidence_refs??[])
      .map(cleanText)
      .filter(Boolean)

    const next:DeceptionCell={
      id,
      family,
      axis,
      status:normalizeCellStatus(row.status,row.passed),
      evidenceRefs:[...new Set(refs)],
      reason:cleanText(row.reason),
    }

    byCell.set(id,mergeDeceptionCells(byCell.get(id),next))
  }

  const cells=deception15CellCatalog().map(cell=>
    byCell.get(cell.id)??{
      ...cell,
      status:'UNTESTED' as const,
      evidenceRefs:[],
      reason:'',
    },
  )

  const failed=cells.filter(cell=>cell.status==='FAIL')
  const inconclusive=cells.filter(cell=>cell.status==='INCONCLUSIVE')
  const untested=cells.filter(cell=>cell.status==='UNTESTED')
  const passed=cells.filter(cell=>cell.status==='PASS')

  let status:DeceptionGateStatus='ADMITTED'
  if(failed.length>0)status='REFUSED'
  else if(inconclusive.length>0)status='INCONCLUSIVE'
  else if(requireAllCells&&untested.length>0)status='UNTESTED'
  else if(passed.length===0)status='UNTESTED'

  return {
    schema:'apx.deception-census/v0.1',
    subject_id:cleanText(input.subjectId),
    status,
    require_all_cells:requireAllCells,
    cells,
    passed_cells:passed.map(cell=>cell.id),
    failed_cells:failed.map(cell=>cell.id),
    inconclusive_cells:inconclusive.map(cell=>cell.id),
    untested_cells:untested.map(cell=>cell.id),
    coverage:cells.length?passed.length/cells.length:0,
    allow_compression:status==='ADMITTED',
  }
}

