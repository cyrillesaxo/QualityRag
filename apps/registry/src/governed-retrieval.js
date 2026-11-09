// Governed retrieval orchestration: retrieval never authorizes an answer.
// A caller-supplied PackSpec evaluator is mandatory; no permissive fallback.
export class GovernedRetrievalPipeline{
 constructor({index,evaluate,generate}){
  if(!index?.search||typeof evaluate!=='function')throw new Error('GOVERNANCE_EVALUATOR_REQUIRED');
  this.index=index;this.evaluate=evaluate;this.generate=generate;
 }
 async ask({tenantId,principalId,query,packSpec,limit=8}){
  if(!packSpec||typeof packSpec!=='object')throw new Error('PACKSPEC_REQUIRED');
  const evidence=await this.index.search({tenantId,principalId,query,limit});
  if(!Array.isArray(evidence))throw new Error('INVALID_RETRIEVAL_RESULT');
  const decision=await this.evaluate({packSpec,query,evidence,tenantId,principalId});
  // A verdict from another tenant or an unknown verdict must never admit.
  if(!decision||decision.verdict!=='ADMIT'||decision.tenant_id!==tenantId||decision.principal_id!==principalId)
   return {status:'WITHHELD',verdict:decision?.verdict??'INCONCLUSIVE',citations:[],reason:decision?.reason??'EVIDENCE_NOT_ADMITTED'};
  if(typeof this.generate!=='function')return {status:'ADMITTED_EVIDENCE',verdict:'ADMIT',evidence,citations:evidence.map(({source_id,revision,chunk_ordinal,start,end})=>({source_id,revision,chunk_ordinal,start,end}))};
  const answer=await this.generate({query,evidence,packSpec,tenantId,principalId});
  if(typeof answer!=='string'||!answer.trim())throw new Error('EMPTY_GENERATED_ANSWER');
  // Evidence citations are issued by the retrieval layer, not fabricated by the model.
  return {status:'ANSWER',verdict:'ADMIT',answer,citations:evidence.map(({source_id,revision,chunk_ordinal,start,end})=>({source_id,revision,chunk_ordinal,start,end}))};
 }
}
