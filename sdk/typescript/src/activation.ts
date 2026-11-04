/** Wire SDK for Node 24+. The server remains the canonical decision engine. */
export type SignedEnvelope={schema:string;canonical:string;key_id:string;payload:Record<string,unknown>;signature:string};
export type FiniteReceipt={finite_constraint_result:'SAT'|'UNSAT'|'UNKNOWN';qualityrag_admission:'INCONCLUSIVE'|'REFUSE';can_generate:false;trace:unknown[];[key:string]:unknown};
function base64(bytes:Uint8Array):string {return btoa(Array.from(bytes,value=>String.fromCharCode(value)).join(""));}
export class ActivationClient {
  private baseUrl:string;
  private bearer:string;
  constructor(baseUrl:string,token:SignedEnvelope){
    if(!baseUrl.startsWith('http://127.0.0.1:')&&!baseUrl.startsWith('https://'))throw Error('Trusted HTTPS or loopback endpoint required');
    this.baseUrl=baseUrl.replace(/\/$/,'');
    this.bearer=base64(new TextEncoder().encode(JSON.stringify(token))).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
  }
  async request(route:string,payload:Record<string,unknown>):Promise<any>{
    if(!['validate','evaluate','fallback','source','status','gardener/state','gardener/proposals','gardener/event','gardener/outcome'].includes(route))throw Error('Unsupported SDK route');
    const response=await fetch(this.baseUrl+'/api/'+route,{method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+this.bearer},
      body:JSON.stringify(payload),signal:AbortSignal.timeout(10000)});
    const body=await response.json();
    if(!response.ok)throw Error('Activation request refused: '+body.error);
    return body;
  }
  validate(schema:string,value:unknown){return this.request('validate',{schema,value});}
  evaluate(input:Record<string,unknown>):Promise<FiniteReceipt>{return this.request('evaluate',input);}
  async trace(input:Record<string,unknown>){return (await this.evaluate(input)).trace;}
  fallback(source_sha256:string){return this.request('fallback',{source_sha256});}
  upload(raw:Uint8Array){return this.request('source',{base64:base64(raw)});}
}
