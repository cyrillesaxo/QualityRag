export type Status = "SUPPORTS" | "CONTRADICTS" | "UNKNOWN";
export type Verdict = "ADMIT" | "REFUSE" | "INCONCLUSIVE";
export interface Requirement { id:string; min_independent_sources?:number; max_age_seconds?:number }
export interface PackSpec { id:string; version:string; requirements:Requirement[] }
export interface Evidence { id:string; requirement_id:string; origin:string; source_ref:string; status:Status; observed_at:string }
export interface Finding { requirement_id:string; verdict:Verdict; independent_sources:number; reasons:string[] }
export interface Evaluation { schema:"qualityrag.result/v0.1"; pack_id:string; pack_version:string; verdict:Verdict; findings:Finding[] }
export function evaluate(pack:PackSpec, evidence:Evidence[], asOf:string = new Date().toISOString()):Evaluation {
  const now = Date.parse(asOf);
  if (!Number.isFinite(now)) throw new Error("Invalid asOf");
  if (!pack?.id || !pack.version || !Array.isArray(pack.requirements) || pack.requirements.length===0 || !Array.isArray(evidence)) throw new Error("Invalid policy or evidence");
  const ids=pack.requirements.map(x=>x.id);
  if (ids.some(x=>!x) || new Set(ids).size!==ids.length) throw new Error("Duplicate or invalid requirement IDs");
  const findings:Finding[]=pack.requirements.map(req=>{
    const minimum=req.min_independent_sources??1, maxAge=req.max_age_seconds;
    if(!Number.isInteger(minimum)||minimum<1||(maxAge!==undefined&&(!Number.isInteger(maxAge)||maxAge<0))) throw new Error("Invalid thresholds");
    const reasons=new Set<string>(), origins=new Set<string>(); let contradicted=false;
    for(const x of evidence.filter(x=>x.requirement_id===req.id)){
      if(!x.id || !x.origin || !x.source_ref || !x.observed_at || !["SUPPORTS","CONTRADICTS","UNKNOWN"].includes(x.status)){reasons.add("INVALID_EVIDENCE");continue;}
      const when=Date.parse(x.observed_at);
      if(!Number.isFinite(when)||!/([zZ]|[+-]\d\d:\d\d)$/.test(x.observed_at)){reasons.add("INVALID_EVIDENCE");continue;}
      const age=(now-when)/1000;
      if(age<0){reasons.add("FUTURE_EVIDENCE");continue;}
      if(maxAge!==undefined&&age>maxAge){reasons.add("STALE_EVIDENCE");continue;}
      if(x.status==="CONTRADICTS")contradicted=true;
      else if(x.status==="SUPPORTS")origins.add(x.origin);
      else reasons.add("UNKNOWN_EVIDENCE");
    }
    const verdict:Verdict=contradicted?"REFUSE":origins.size<minimum?"INCONCLUSIVE":"ADMIT";
    if(contradicted) reasons.add("CONTRADICTION");
    else if(origins.size<minimum)reasons.add("INSUFFICIENT_INDEPENDENT_EVIDENCE");
    return {requirement_id:req.id,verdict,independent_sources:origins.size,reasons:[...reasons].sort()};
  });
  const verdict:Verdict=findings.some(x=>x.verdict==="REFUSE")?"REFUSE":findings.some(x=>x.verdict==="INCONCLUSIVE")?"INCONCLUSIVE":"ADMIT";
  return {schema:"qualityrag.result/v0.1",pack_id:pack.id,pack_version:pack.version,verdict,findings};
}
