// Server-side composition only. No public route until a current-source
// resolver and authenticated owner/actor authorization are available.
import {questionTargetDigest,verifyQuestionReview} from './guided-question-review.js';
import {createQuestionReviewAuthority} from './guided-question-authority.js';
import {createQuestionReceiptLifecycle} from './guided-question-receipt-lifecycle.js';
import {createGuidedQuestionRequestStore} from './guided-question-request-store.js';
const id=v=>typeof v==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(v);
const hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const unknown=()=>({state:'UNKNOWN',eligibleAtCheck:false,releasePermitted:false,answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'});
export function createGuidedQuestionService({pool,resolveAuthorizedTarget}={}){
 if(typeof resolveAuthorizedTarget!=='function')throw Error('AUTHORIZED_TARGET_RESOLVER_REQUIRED');
 const authority=createQuestionReviewAuthority(pool);
 const lifecycle=createQuestionReceiptLifecycle(pool);
 const requests=createGuidedQuestionRequestStore(pool);
 async function resolve(identity,selector,action){
  // The injected resolver must check tenant, owner, actor, service, current
  // policy and current source revision, and enforce access for this action.
  if(!identity||typeof identity.subject!=='string'||!identity.subject||!(identity.roles instanceof Set)||!identity.roles.has((action==='submit'||action==='register')?'evidence.ingest':'evidence.reader')||!id(selector?.service)||!id(selector?.environment)||!id(selector?.targetId)||!(identity.evidenceServices instanceof Set)||!identity.evidenceServices.has(selector.service+'@'+selector.environment))return null;
  const current=await resolveAuthorizedTarget(identity,{service:selector.service,environment:selector.environment,targetId:selector.targetId},action);
  if(!current||current.service!==selector.service||current.environment!==selector.environment||!hex(current.ownerBinding)||!hex(current.policyDigest))return null;
  return {ownerBinding:current.ownerBinding,service:current.service,environment:current.environment,policyDigest:current.policyDigest,targetDigest:questionTargetDigest(current)};
 }
 async function submit(identity,selector,envelope){
  try{
   const expected=await resolve(identity,selector,'submit');
   if(!expected)return {verdict:'INCONCLUSIVE',reason:'AUTHORITY_UNAVAILABLE',answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'};
   return await verifyQuestionReview({envelope,expected,lookupReviewer:authority.lookupReviewer,consumeNonce:authority.consumeNonce});
  }catch{return {verdict:'INCONCLUSIVE',reason:'AUTHORITY_UNAVAILABLE',answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'};}
 }
 async function eligibility(identity,selector,receiptDigest){
  try{
   if(!hex(receiptDigest))return unknown();
   const expected=await resolve(identity,selector,'read');
   if(!expected)return unknown();
   const status=await lifecycle.resolveEligibility(receiptDigest,expected);
   // Echo only independently resolved binding, never a client-provided digest.
   return status.state==='ACTIVE'&&status.eligibleAtCheck===true
    ? {...status,schema:'qualityrag.guided-question-eligibility/v1',receiptDigest,targetDigest:expected.targetDigest}
    : status;
  }catch{return unknown();}
 }
 // Registration is an explicit write, not a side effect of receipt discovery.
 async function register(identity,selector){
  try{
   const selected=structuredClone(selector);
   const expected=await resolve(identity,selected,'register');
   return expected?await requests.enqueue(expected,selected.targetId):null;
  }catch{return null;}
 }
 async function findCurrentReview(identity,selector){
  try{
   const selected=structuredClone(selector);
   const expected=await resolve(identity,selected,'read');
   if(!expected)return unknown();
   const record=await requests.latestReceipt(expected,selected.targetId);
   if(!record)return unknown();
   // Re-resolve current authority before eligibility; never return historical
   // metadata as approval or fall back to an older positive decision.
   const status=await eligibility(identity,selected,record.receiptDigest);
   if(status.state!=='ACTIVE'||status.targetDigest!==expected.targetDigest)return unknown();
   return {...status,targetId:selected.targetId};
  }catch{return unknown();}
 }
 return {submit,eligibility,register,findCurrentReview};
}
