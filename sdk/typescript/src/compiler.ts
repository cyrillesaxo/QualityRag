import type {PackSpec, Evidence, Verdict} from "./index.js";

export type SemanticRequirement = PackSpec["requirements"][number] & {scope?:string; authority?:string};
export type SemanticPack = Omit<PackSpec,"requirements"> & {requirements:SemanticRequirement[]};
export type SemanticWitness = Evidence & {scope?:string; authority?:string};
export type Obligation = {requirement_id:string; min_origins:number; max_age_seconds:number|null; required_scope:string; required_authority:string|null};
export function compilePack(pack:SemanticPack):Obligation[] {
  if(!pack?.id?.trim()||!pack?.version?.trim()||!Array.isArray(pack.requirements)||!pack.requirements.length)throw new Error("Invalid pack");
  const ids=new Set<string>();
  return pack.requirements.map(r=>{
    if(!r?.id?.trim()||ids.has(r.id))throw new Error("Invalid/duplicate requirement");
    ids.add(r.id);
    const n=r.min_independent_sources??1, age=r.max_age_seconds??null,scope=r.scope??"global",authority=r.authority??null;
    if(!Number.isInteger(n)||n<1||(age!==null&&(!Number.isInteger(age)||age<0))||!scope.trim()||(authority!==null&&!authority.trim()))throw new Error("Invalid requirement");
    return {requirement_id:r.id,min_origins:n,max_age_seconds:age,required_scope:scope,required_authority:authority};
  });
}
export function evaluateCompiled(pack:SemanticPack,evidence:SemanticWitness[],asOf:string): {
  schema:string;pack_id:string;pack_version:string;verdict:Verdict;constraint_ir:Obligation[];
  findings:Array<{requirement_id:string;verdict:Verdict;independent_sources:number;missing_sources:number;reasons:string[]}>;
  witness_graph:{nodes:Array<{id:string;origin:string;requirement_id:string}>;dependent_groups:Array<{requirement_id:string;origin:string;witness_ids:string[]}>};
  wgap:Array<{requirement_id:string;missing_sources:number;reasons:string[]}>;
} {
  const obligations=compilePack(pack),now=Date.parse(asOf);
  if(!Number.isFinite(now)||!Array.isArray(evidence))throw new Error("Invalid evidence or time");
  const nodes:Array<{id:string;origin:string;requirement_id:string}>=[], groups=new Map<string,string[]>();
  const findings=obligations.map(o=>{
    const origins=new Set<string>(),reasons=new Set<string>();let conflict=false;
    for(const x of evidence.filter(x=>x?.requirement_id===o.requirement_id)){
      if(!x.id?.trim()||!x.origin?.trim()||!x.source_ref?.trim()||!x.observed_at?.trim()||!["SUPPORTS","CONTRADICTS","UNKNOWN"].includes(x.status)){reasons.add("INVALID_WITNESS");continue;}
      if(!/([zZ]|[+-]\d\d:\d\d)$/.test(x.observed_at)||!Number.isFinite(Date.parse(x.observed_at))){reasons.add("INVALID_WITNESS");continue;}
      const age=(now-Date.parse(x.observed_at))/1000;
      nodes.push({id:x.id,origin:x.origin,requirement_id:o.requirement_id});
      const key=JSON.stringify([o.requirement_id,x.origin]);groups.set(key,[...(groups.get(key)??[]),x.id]);
      if(age<0){reasons.add("FUTURE_WITNESS");continue;}
      if(o.max_age_seconds!==null&&age>o.max_age_seconds){reasons.add("STALE_WITNESS");continue;}
      if((x.scope??"global")!==o.required_scope){reasons.add("SCOPE_MISMATCH");continue;}
      if(o.required_authority!==null&&x.authority!==o.required_authority){reasons.add("AUTHORITY_MISMATCH");continue;}
      if(x.status==="CONTRADICTS")conflict=true;
      else if(x.status==="SUPPORTS")origins.add(x.origin);
      else reasons.add("UNKNOWN_WITNESS");
    }
    const verdict:Verdict=conflict?"REFUSE":origins.size<o.min_origins?"INCONCLUSIVE":"ADMIT";
    if(conflict)reasons.add("CONTRADICTION");
    else if(origins.size<o.min_origins)reasons.add("INSUFFICIENT_INDEPENDENT_EVIDENCE");
    return {requirement_id:o.requirement_id,verdict,independent_sources:origins.size,missing_sources:Math.max(0,o.min_origins-origins.size),reasons:[...reasons].sort()};
  });
  const verdict:Verdict=findings.some(x=>x.verdict==="REFUSE")?"REFUSE":findings.some(x=>x.verdict==="INCONCLUSIVE")?"INCONCLUSIVE":"ADMIT";
  const dependent_groups=[...groups.entries()].filter(([,ids])=>ids.length>1).map(([k,ids])=>{const [requirement_id,origin]=JSON.parse(k) as [string,string];return {requirement_id,origin,witness_ids:ids.sort()};}).sort((a,b)=>a.requirement_id.localeCompare(b.requirement_id)||a.origin.localeCompare(b.origin));
  return {schema:"qualityrag.compiled-result/v0.1",pack_id:pack.id,pack_version:pack.version,verdict,constraint_ir:obligations,findings,witness_graph:{nodes,dependent_groups},wgap:findings.filter(x=>x.verdict!=="ADMIT").map(x=>({requirement_id:x.requirement_id,missing_sources:x.missing_sources,reasons:x.reasons}))};
}
