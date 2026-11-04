export type DecisionReductionResult<TVerdict extends string>={
  referenceVerdict:TVerdict;w_min:string[];eliminated:string[];
}
export function reduceToWMin<TVerdict extends string>(input:{
  witnessIds:string[];decisionFn:(activeWitnessIds:string[])=>TVerdict
}):DecisionReductionResult<TVerdict>{
  const unique=[...new Set(input.witnessIds)].sort()
  const referenceVerdict=input.decisionFn(unique)
  let active=[...unique]; const eliminated:string[]=[]
  let changed=true
  while(changed){
    changed=false
    for(const candidate of [...active]){
      const next=active.filter(id=>id!==candidate)
      if(input.decisionFn(next)===referenceVerdict){
        active=next; eliminated.push(candidate); changed=true
      }
    }
  }
  return {referenceVerdict,w_min:active.sort(),eliminated:eliminated.sort()}
}
export function verifyWMin<TVerdict extends string>(input:{
  wMin:string[];referenceVerdict:TVerdict;decisionFn:(activeWitnessIds:string[])=>TVerdict
}):{verdictPreserved:boolean;loadBearing:boolean;removable:string[]}{
  const verdictPreserved=input.decisionFn(input.wMin)===input.referenceVerdict
  const removable=input.wMin.filter(candidate=>input.decisionFn(input.wMin.filter(id=>id!==candidate))===input.referenceVerdict)
  return {verdictPreserved,loadBearing:verdictPreserved&&removable.length===0,removable}
}
