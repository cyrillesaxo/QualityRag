export const G_CODES=Object.freeze(
  Array.from({length:12},(_,index)=>`G${index+1}`),
)

export const SEMANTIC_MOVEMENTS=Object.freeze([
  'NOT_APPLICABLE',
  'INTRODUCED',
  'REMOVED_FROM_OBSERVED_CHART',
  'TOWARD_ADMITTED_REGIME',
  'AWAY_FROM_ADMITTED_REGIME',
  'STABLE',
  'UNMEASURED',
] as const)

export type SemanticMovement=typeof SEMANTIC_MOVEMENTS[number]

export type SemanticCoordinate={
  id?:string
  code?:string
  applicable?:boolean
  deltaRef?:number|null
  referenceDisplacement?:number|null
  pHat?:number|null
  entropy?:number|null
  risk?:number|null
}

export type SemanticAssuranceSnapshot={
  schema:'apx.semantic-assurance-snapshot/v0.1'
  revision?:string|null
  journey?:string|null
  coordinates:SemanticCoordinate[]
  witnessGraph?:{
    deceptiveWitnessIds?:string[]
    dependentGroups?:Array<{key:string}>
  }
  term?:{
    scenarios?:Array<{scenarioId:string;status:string;touched?:string[]}>
  }
}

export type RcocDiffOptions={
  transformationOrder?:string[]
}

const EPSILON=1e-6

export function finiteSemanticValue(value:unknown):number|null{
  return typeof value==='number'&&Number.isFinite(value)?value:null
}

export function semanticCoordinateCode(item:SemanticCoordinate={}):string|null{
  const raw=String(item.id??item.code??'').trim().toUpperCase()
  return G_CODES.includes(raw)?raw:null
}

function coordinateMap(values:SemanticCoordinate[]=[]){
  const map=new Map<string,SemanticCoordinate>()
  for(const item of values??[]){
    const code=semanticCoordinateCode(item)
    if(!code)continue
    if(map.has(code))throw new Error(`Duplicate semantic coordinate ${code}`)
    map.set(code,item)
  }
  return map
}

export function classifySemanticCoordinateMovement(
  before:SemanticCoordinate={},
  after:SemanticCoordinate={},
):SemanticMovement{
  if(!before?.applicable&&!after?.applicable)return 'NOT_APPLICABLE'
  if(!before?.applicable&&after?.applicable)return 'INTRODUCED'
  if(before?.applicable&&!after?.applicable)return 'REMOVED_FROM_OBSERVED_CHART'

  const beforeDelta=finiteSemanticValue(
    before?.deltaRef??before?.referenceDisplacement,
  )
  const afterDelta=finiteSemanticValue(
    after?.deltaRef??after?.referenceDisplacement,
  )
  if(beforeDelta===null||afterDelta===null)return 'UNMEASURED'

  const movement=afterDelta-beforeDelta
  if(movement>EPSILON)return 'TOWARD_ADMITTED_REGIME'
  if(movement<-EPSILON)return 'AWAY_FROM_ADMITTED_REGIME'
  return 'STABLE'
}

export function compareSemanticCoordinateVectors(
  beforeValues:SemanticCoordinate[]=[],
  afterValues:SemanticCoordinate[]=[],
){
  const before=coordinateMap(beforeValues)
  const after=coordinateMap(afterValues)

  return G_CODES.map(code=>{
    const b=before.get(code)??{id:code,applicable:false}
    const a=after.get(code)??{id:code,applicable:false}
    const deltaRefBefore=finiteSemanticValue(
      b.deltaRef??b.referenceDisplacement,
    )
    const deltaRefAfter=finiteSemanticValue(
      a.deltaRef??a.referenceDisplacement,
    )
    const pHatBefore=finiteSemanticValue(b.pHat)
    const pHatAfter=finiteSemanticValue(a.pHat)
    const entropyBefore=finiteSemanticValue(b.entropy)
    const entropyAfter=finiteSemanticValue(a.entropy)
    const riskBefore=finiteSemanticValue(b.risk)
    const riskAfter=finiteSemanticValue(a.risk)

    return {
      id:code,
      beforeApplicable:Boolean(b.applicable),
      afterApplicable:Boolean(a.applicable),
      deltaRefBefore,
      deltaRefAfter,
      deltaRefChange:deltaRefBefore!==null&&deltaRefAfter!==null
        ?Number((deltaRefAfter-deltaRefBefore).toFixed(6))
        :null,
      pHatBefore,
      pHatAfter,
      entropyChange:entropyBefore!==null&&entropyAfter!==null
        ?Number((entropyAfter-entropyBefore).toFixed(6))
        :null,
      riskChange:riskBefore!==null&&riskAfter!==null
        ?Number((riskAfter-riskBefore).toFixed(6))
        :null,
      movement:classifySemanticCoordinateMovement(b,a),
    }
  })
}

function compareWitnessGraphs(
  before:SemanticAssuranceSnapshot,
  after:SemanticAssuranceSnapshot,
){
  const beforeDw=new Set(before.witnessGraph?.deceptiveWitnessIds??[])
  const afterDw=new Set(after.witnessGraph?.deceptiveWitnessIds??[])
  const added=[...afterDw].filter(id=>!beforeDw.has(id))
  const removed=[...beforeDw].filter(id=>!afterDw.has(id))

  const beforeGroups=new Set(
    (before.witnessGraph?.dependentGroups??[]).map(group=>group.key),
  )
  const afterGroups=new Set(
    (after.witnessGraph?.dependentGroups??[]).map(group=>group.key),
  )

  return {
    newDeceptiveWitnesses:added,
    resolvedDeceptiveWitnesses:removed,
    newUnresolvedIndependenceGroups:[...afterGroups].filter(
      key=>!beforeGroups.has(key),
    ),
    resolvedIndependenceGroups:[...beforeGroups].filter(
      key=>!afterGroups.has(key),
    ),
    boundary:'Witness changes compare declared graph identity only. Added or removed witness IDs do not by themselves establish causal change.',
  }
}

function compareTerm(
  before:SemanticAssuranceSnapshot,
  after:SemanticAssuranceSnapshot,
){
  const beforeMap=new Map(
    (before.term?.scenarios??[]).map(item=>[item.scenarioId,item]),
  )
  const afterMap=new Map(
    (after.term?.scenarios??[]).map(item=>[item.scenarioId,item]),
  )
  const scenarioIds=[...new Set([...beforeMap.keys(),...afterMap.keys()])]
  const scenarios=scenarioIds.map(scenarioId=>({
    scenarioId,
    before:beforeMap.get(scenarioId)?.status??null,
    after:afterMap.get(scenarioId)?.status??null,
    changed:(beforeMap.get(scenarioId)?.status??null)
      !==(afterMap.get(scenarioId)?.status??null),
    touched:afterMap.get(scenarioId)?.touched??[],
  }))

  return {
    scenarios,
    newlyReactivated:scenarios
      .filter(item=>
        item.after==='REACTIVATED'&&item.before!=='REACTIVATED',
      )
      .map(item=>item.scenarioId),
    newlyUnknownImpact:scenarios
      .filter(item=>
        item.after==='UNKNOWN_IMPACT'&&item.before!=='UNKNOWN_IMPACT',
      )
      .map(item=>item.scenarioId),
    boundary:'TERM status is interpreted only within dependency/change provenance recorded by the snapshots.',
  }
}

function orderedDeparture(
  coordinates:ReturnType<typeof compareSemanticCoordinateVectors>,
  order:string[]=[],
){
  const away=new Set(
    coordinates
      .filter(item=>item.movement==='AWAY_FROM_ADMITTED_REGIME')
      .map(item=>item.id),
  )

  if(away.size===0){
    return {
      status:'NO_AWAY_MOVEMENT_OBSERVED',
      coordinate:null as string|null,
      candidates:[] as string[],
    }
  }

  if(order.length===0){
    return {
      status:'UNMEASURED_ORDER',
      coordinate:null,
      candidates:[...away],
      boundary:'Two semantic snapshots do not establish which coordinate departed first. Supply a registered transformation order/trace to make an ordering claim.',
    }
  }

  const normalizedOrder=order
    .map(item=>String(item).trim().toUpperCase())
    .filter(item=>G_CODES.includes(item))
  const first=normalizedOrder.find(id=>away.has(id))

  if(!first){
    return {
      status:'ORDER_DOES_NOT_COVER_DEPARTURE',
      coordinate:null,
      candidates:[...away],
    }
  }

  return {
    status:'ORDERED_WITHIN_SUPPLIED_TRACE',
    coordinate:first,
    candidates:[...away],
    boundary:'First departure is conditional on the supplied transformation order; it is not inferred from file order or timestamps.',
  }
}

function classifyDiff(
  coordinates:ReturnType<typeof compareSemanticCoordinateVectors>,
  witnessGraph:ReturnType<typeof compareWitnessGraphs>,
  term:ReturnType<typeof compareTerm>,
){
  const away=coordinates.some(
    item=>item.movement==='AWAY_FROM_ADMITTED_REGIME',
  )
  const toward=coordinates.some(
    item=>item.movement==='TOWARD_ADMITTED_REGIME',
  )
  const newRisk=
    witnessGraph.newDeceptiveWitnesses.length>0
    ||witnessGraph.newUnresolvedIndependenceGroups.length>0
    ||term.newlyReactivated.length>0
    ||term.newlyUnknownImpact.length>0

  if(away||newRisk)return 'REVIEW_REQUIRED' as const
  if(toward)return 'IMPROVED_WITHIN_OBSERVED_RECEIPTS' as const
  return 'NO_MATERIAL_SEMANTIC_MOVEMENT_ESTABLISHED' as const
}

export type RcocDiffResult={
  schema:'apx.rcoc-semantic-diff/v0.1'
  status:
    |'INCOMPARABLE'
    |'REVIEW_REQUIRED'
    |'IMPROVED_WITHIN_OBSERVED_RECEIPTS'
    |'NO_MATERIAL_SEMANTIC_MOVEMENT_ESTABLISHED'
  reason?:string
  model?:string
  before?:{revision:string|null;journey:string|null}
  after?:{revision:string|null;journey:string|null}
  coordinates?:ReturnType<typeof compareSemanticCoordinateVectors>
  changedCoordinates?:ReturnType<typeof compareSemanticCoordinateVectors>
  witnessGraph?:ReturnType<typeof compareWitnessGraphs>
  term?:ReturnType<typeof compareTerm>
  firstDeparture?:ReturnType<typeof orderedDeparture>
  admission?:{
    status:'INCONCLUSIVE'|'BOUNDED_DIFF'
    reason:string
  }
  boundary:string
}

function validSnapshot(input:unknown):input is SemanticAssuranceSnapshot{
  if(!input||typeof input!=='object')return false
  const value=input as Partial<SemanticAssuranceSnapshot>
  return value.schema==='apx.semantic-assurance-snapshot/v0.1'
    &&Array.isArray(value.coordinates)
}

export function compareSemanticAssuranceSnapshots(
  before:SemanticAssuranceSnapshot,
  after:SemanticAssuranceSnapshot,
  options:RcocDiffOptions={},
):RcocDiffResult{
  if(!validSnapshot(before)||!validSnapshot(after)){
    return {
      schema:'apx.rcoc-semantic-diff/v0.1',
      status:'INCOMPARABLE',
      reason:'Both inputs must be apx.semantic-assurance-snapshot/v0.1 snapshots.',
      boundary:'No semantic movement is inferred from malformed or non-APX semantic snapshots.',
    }
  }

  const coordinates=compareSemanticCoordinateVectors(
    before.coordinates,
    after.coordinates,
  )
  const witnessGraph=compareWitnessGraphs(before,after)
  const term=compareTerm(before,after)
  const firstDeparture=orderedDeparture(
    coordinates,
    options.transformationOrder??[],
  )
  const status=classifyDiff(coordinates,witnessGraph,term)
  const changedCoordinates=coordinates.filter(
    item=>!['STABLE','NOT_APPLICABLE'].includes(item.movement),
  )

  return {
    schema:'apx.rcoc-semantic-diff/v0.1',
    model:'RCOC receipt-to-receipt semantic transformation projection',
    before:{
      revision:before.revision??null,
      journey:before.journey??null,
    },
    after:{
      revision:after.revision??null,
      journey:after.journey??null,
    },
    status,
    coordinates,
    changedCoordinates,
    witnessGraph,
    term,
    firstDeparture,
    admission:{
      status:status==='REVIEW_REQUIRED'?'INCONCLUSIVE':'BOUNDED_DIFF',
      reason:status==='REVIEW_REQUIRED'
        ?'Observed semantic movement or evidence-freshness risk requires a discriminating review/probe before stronger admission.'
        :'Diff is bounded to the evidence and dependency scope encoded in the two snapshots.',
    },
    boundary:'This compares evidence-bounded semantic snapshots by canonical G coordinate. It does not infer semantic change directly from raw Git text, claim causal origin, or establish chronology without an ordered transformation trace.',
  }
}

export {CANONICAL_G_TAXONOMY} from './canonical-taxonomy.js'
export type {CanonicalGCode} from './canonical-taxonomy.js'
