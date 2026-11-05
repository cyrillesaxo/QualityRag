/** Wire SDK for Node 24+. The server remains the canonical decision engine. */
export type SignedEnvelope={schema:string;canonical:string;key_id:string;payload:Record<string,unknown>;signature:string};
export type FiniteReceipt={finite_constraint_result:'SAT'|'UNSAT'|'UNKNOWN';qualityrag_admission:'INCONCLUSIVE'|'REFUSE';can_generate:false;trace:string[];[key:string]:unknown};
export type ReviewedActivationResult={schema:'qualityrag.reviewed-activation/v1';tenant:string;source_sha256:string;artifact_sha256:string;contract_sha256:string;policy_ir_sha256:string;action:'REQUIRES_REVIEW'|'REFUSE'|'FALLBACK';finite_constraint_result:'SAT'|'UNSAT'|'UNKNOWN';output:Record<string,string|number|boolean|null>|null;qualityrag_admission:'INCONCLUSIVE';can_generate:false;execution:Record<string,unknown>;candidate_audit:Record<string,unknown>;preservation_review:Record<string,unknown>;compatibility:Record<string,unknown>;canonical_candidate:FiniteReceipt;fallback_authority:'DISABLED'|'SAME_SIGNED_SOURCE_AND_REVIEWED_CONTRACT';evidence_boundary:string};
export type ObservationGraphResult={schema:'qualityrag.observation-result/v1';ast:Record<string,unknown>;transition:Record<string,unknown>|null;source_sha256:string;type_status:'WELL_TYPED';domain_validity:'UNKNOWN';canonical_apx_parity:'NOT_ESTABLISHED';can_generate:false};
export type ValidationResult={valid:true;semantic_admission:'INCONCLUSIVE'};
export type FallbackResult={source_sha256:string;base64:string;fallback:'AUTHORIZED_ORIGINAL_BYTES'};
export type GardenOperation='PROPOSE'|'CHALLENGE'|'TEST'|'SYNTHESIZE'|'PRUNE'|'REOPEN';
export type GardenEvent={event_id:string;operation:GardenOperation;branch:string;source_sha256:string;source_ref:string;statement:string;parents:string[];evidence_ids?:string[]};
export type GardenQuery={text?:string;evidence_status?:string;open_challenge?:boolean;active?:boolean;lineage_of?:string;depends_on?:string;since?:number;limit?:number};
export type GardenBranchSummary={branch:string;statement:string;active:boolean;evidence_status:string;parents:string[];children:string[];open_challenge:boolean;events:number;created_sequence:number;last_sequence:number;source_ref:string;source_sha256:string;dependency?:'direct'|'inherited'};
export type GardenQueryResult={schema:'qualityrag.gardener-query/v1';branches:GardenBranchSummary[];total:number;truncated:boolean;events:Record<string,unknown>[];since:number;head_sequence:number;events_truncated:boolean;independent_validation:'NOT_ESTABLISHED'};
function base64(bytes:Uint8Array):string {return btoa(Array.from(bytes,value=>String.fromCharCode(value)).join(""));}
function endpoint(value:string):string {
  if(typeof value!=='string'||value.includes('\\')||/[\u0000-\u0020\u007f]/.test(value)||!/^[a-z][a-z0-9+.-]*:\/\/[^/?#]/i.test(value))throw Error('Trusted HTTPS or loopback endpoint required');
  const url=new URL(value);
  if(!['http:','https:'].includes(url.protocol)||!url.hostname||url.username||url.password||url.search||url.hash
      ||(url.protocol==='http:'&&(!/^http:\/\/127\.0\.0\.1(?::[0-9]+)?(?:\/|$)/i.test(value)||url.hostname!=='127.0.0.1'))||url.port==='0')throw Error('Trusted HTTPS or loopback endpoint required');
  return url.toString().replace(/\/$/,'');
}
function wireJson(value:unknown):string {
  return JSON.stringify(value,(_key,item)=>{
    if(['undefined','function','symbol','bigint'].includes(typeof item)||(typeof item==='number'&&(!Number.isFinite(item)||(Number.isInteger(item)&&!Number.isSafeInteger(item)))))
      throw Error('Unsupported JSON value');
    return item;
  });
}
export class ActivationClient {
  private baseUrl:string;
  private bearer:string;
  constructor(baseUrl:string,token:SignedEnvelope){
    this.baseUrl=endpoint(baseUrl);
    this.bearer=base64(new TextEncoder().encode(wireJson(token))).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
  }
  async request(route:string,payload:Record<string,unknown>):Promise<any>{
    if(!['validate','evaluate','activate-plan','reviewed-run','observations','fallback','source','status','gardener/state','gardener/proposals','gardener/event','gardener/outcome','gardener/query','policy/example','policy/test','policy/advise','policy/replay','policy/siblings'].includes(route))throw Error('Unsupported SDK route');
    const response=await fetch(this.baseUrl+'/api/'+route,{method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+this.bearer},
      body:wireJson(payload),redirect:'error',signal:AbortSignal.timeout(10000)});
    const body=JSON.parse(await response.text(),(_key,item)=>{
      if(typeof item==='number'&&(!Number.isFinite(item)||(Number.isInteger(item)&&!Number.isSafeInteger(item))))
        throw Error('Unsupported JSON number in activation response');
      return item;
    });
    if(!response.ok)throw Error('Activation request refused: '+body.error);
    return body;
  }
  validate(schema:string,value:unknown):Promise<ValidationResult>{return this.request('validate',{schema,value});}
  evaluate(input:Record<string,unknown>):Promise<FiniteReceipt>{return this.request('evaluate',input);}
  activatePlan(input:Record<string,unknown>):Promise<ReviewedActivationResult>{return this.request('activate-plan',input);}
  runReviewed(raw:Uint8Array,request:Record<string,unknown>):Promise<ReviewedActivationResult>{return this.request('reviewed-run',{base64:base64(raw),request});}
  observations(input:Record<string,unknown>):Promise<ObservationGraphResult>{return this.request('observations',input);}
  async trace(input:Record<string,unknown>):Promise<string[]>{return (await this.evaluate(input)).trace;}
  fallback(source_sha256:string):Promise<FallbackResult>{return this.request('fallback',{source_sha256});}
  upload(raw:Uint8Array){return this.request('source',{base64:base64(raw)});}
  /** Semantic Gardener. The server sets actor and time from the token; prune/reopen/synthesize need review scope. */
  policyExample():Promise<Record<string,unknown>>{return this.request('policy/example',{});}
  /** Run the gate on retrieved chunks and explain which spans it counted. Read scope; writes nothing. */
  policyTest(body:{pack:Record<string,unknown>;documents:unknown[];retrieved:string[];question?:string;as_of?:string}):Promise<Record<string,unknown>>{return this.request('policy/test',body as Record<string,unknown>);}
  /** Governance findings. Suggestions only: none changes a verdict. */
  policyAdvise(body:{pack?:Record<string,unknown>;test?:Record<string,unknown>;benchmark?:Record<string,unknown>;far_limit?:number}={}):Promise<Record<string,unknown>>{return this.request('policy/advise',body as Record<string,unknown>);}
  /** Re-evaluate recorded cases under two packs. */
  policyReplay(body:{base:Record<string,unknown>;branch:Record<string,unknown>;cases:unknown[];as_of?:string}):Promise<Record<string,unknown>>{return this.request('policy/replay',body as Record<string,unknown>);}
  /** Feasible(s,F,C) per contract (SAT/UNSAT/UNKNOWN), functional siblings, regime boundaries and probes. */
  policySiblings(body:{function:string;contracts:Record<string,Record<string,unknown>>;candidates:unknown[];as_of?:string}):Promise<Record<string,unknown>>{return this.request('policy/siblings',body as Record<string,unknown>);}
  gardenState():Promise<Record<string,unknown>>{return this.request('gardener/state',{});}
  gardenQuery(filters:GardenQuery={}):Promise<GardenQueryResult>{return this.request('gardener/query',filters as Record<string,unknown>);}
  gardenSuggestions():Promise<Record<string,unknown>>{return this.request('gardener/proposals',{});}
  gardenEvent(event:GardenEvent):Promise<Record<string,unknown>>{return this.request('gardener/event',event as unknown as Record<string,unknown>);}
}
