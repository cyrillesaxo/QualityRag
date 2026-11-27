// Versioned, server-side verification foundation. No endpoint or key enrollment.
import {createHash, verify, KeyObject} from 'node:crypto';
export const SCHEMA='qualityrag.guided-question-review/v1';
const DOMAIN=Buffer.from('QUALITYRAG/'+SCHEMA+'\0','ascii');
const HEX=/^[a-f0-9]{64}$/;
const ID=/^[A-Za-z0-9._:-]{1,128}$/;
const digest=b=>createHash('sha256').update(b).digest('hex');
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const id=v=>typeof v==='string'&&ID.test(v);
const hex=v=>typeof v==='string'&&HEX.test(v);
const fail=reason=>({verdict:'INCONCLUSIVE',reason,answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'});
// Fixed ordered tuples, UTF-8 JSON, no arbitrary object key ordering. Text is
// represented by server-computed digests. Cross-language conformance pending.
export function questionReviewBytes(p){
 if(!exact(p,['schema','ownerBinding','service','environment','policyDigest','targetDigest','nonce','issuedAt','expiresAt','decision','reviewerId'])||
 p.schema!==SCHEMA||![p.ownerBinding,p.policyDigest,p.targetDigest].every(hex)||
 ![p.service,p.environment,p.nonce,p.reviewerId].every(id)||p.nonce.length<16||
 !Number.isSafeInteger(p.issuedAt)||!Number.isSafeInteger(p.expiresAt)||
 !['ADMIT','REFUSE','INCONCLUSIVE'].includes(p.decision))throw Error('INVALID_REVIEW_PAYLOAD');
 return Buffer.concat([DOMAIN,Buffer.from(JSON.stringify([p.schema,p.ownerBinding,p.service,p.environment,p.policyDigest,p.targetDigest,p.nonce,p.issuedAt,p.expiresAt,p.decision,p.reviewerId]),'utf8')]);
}
export function questionTargetDigest({ownerBinding,service,environment,policyDigest,source,concept,goalId,evidence,operatorId,relation=null}={}){
 if(![ownerBinding,policyDigest].every(hex)||![service,environment].every(id))throw Error('INVALID_SCOPE');
 const text=source?.text;
 const str=v=>typeof v==='string'&&v.length>0&&v.length<=1024;
 if(typeof text!=='string'||text.length>100000||![source?.id,source?.revision,concept?.id,concept?.revision,concept?.label,goalId,evidence?.id,evidence?.obligationId,evidence?.kind,evidence?.consequence,operatorId].every(str))throw Error('INVALID_TARGET');
 if(evidence.sourceId!==source.id||evidence.revision!==source.revision||evidence.conceptId!==concept.id||evidence.semanticRevision!==concept.revision)throw Error('SCOPE_MISMATCH');
 const span=(a,lo=0,hi=text.length)=>{
  if(!Number.isInteger(a?.start)||!Number.isInteger(a?.end)||a.start<lo||a.end>hi||a.end<=a.start||typeof a.quote!=='string'||text.slice(a.start,a.end)!==a.quote)throw Error('INVALID_SOURCE_SPAN');
  return [a.start,a.end,a.quote];
 };
 const anchor=span(evidence);
 const t=evidence.questionTarget;
 let args=null;
 if(t!=null){
  if(t.operatorId!==operatorId||t.obligationId!==evidence.obligationId||!Array.isArray(t.arguments)||t.arguments.length<1||t.arguments.length>2)throw Error('INVALID_TYPED_TARGET');
  const seen=new Set();
  args=t.arguments.map(a=>{if(!id(a?.role)||seen.has(a.role))throw Error('INVALID_ROLE');seen.add(a.role);return [a.role,...span(a,evidence.start,evidence.end)];});
 }
 let rel=null;
 if(relation!==null){
  if(![relation.id,relation.type].every(str))throw Error('INVALID_RELATION');
  rel=[relation.id,relation.type,span(relation.from,evidence.start,evidence.end),span(relation.cue,evidence.start,evidence.end),span(relation.to,evidence.start,evidence.end)];
 }
 return digest(Buffer.from(JSON.stringify([SCHEMA,ownerBinding,service,environment,policyDigest,source.id,source.revision,digest(Buffer.from(text,'utf8')),concept.id,concept.revision,concept.label,goalId,evidence.id,evidence.obligationId,evidence.kind,evidence.consequence,operatorId,anchor,args,rel]),'utf8'));
}
// expected and trust must originate from authenticated server-side state.
// consumeNonce must atomically reserve a nonce in durable storage, never a
// client callback. No default implementation or automatic admission.
export async function verifyQuestionReview({envelope,expected,lookupReviewer,consumeNonce,now=Date.now()}={}){
 try{
  if(!exact(envelope,['payload','signature'])||typeof lookupReviewer!=='function'||typeof consumeNonce!=='function'||!Number.isSafeInteger(now))return fail('AUTHORITY_UNAVAILABLE');
  const p=envelope.payload,bytes=questionReviewBytes(p);
  if(!expected||!['ownerBinding','service','environment','policyDigest','targetDigest'].every(k=>p[k]===expected[k]))return fail('SCOPE_MISMATCH');
  if(p.issuedAt>now||p.expiresAt<=now||p.expiresAt<=p.issuedAt||p.expiresAt-p.issuedAt>600000)return fail('EXPIRED_OR_INVALID_TIME');
  const reviewer=await lookupReviewer(p.reviewerId,expected);
  if(!reviewer||reviewer.active!==true||reviewer.authorized!==true||!(reviewer.key instanceof KeyObject)||reviewer.key.type!=='public'||reviewer.key.asymmetricKeyType!=='ed25519')return fail('REVIEWER_NOT_AUTHORIZED');
  const sig=envelope.signature;
  if(typeof sig!=='string'||!/^[A-Za-z0-9_-]{86}$/.test(sig))return fail('INVALID_SIGNATURE');
  const raw=Buffer.from(sig,'base64url');
  if(raw.length!==64||raw.toString('base64url')!==sig||!verify(null,bytes,reviewer.key,raw))return fail('INVALID_SIGNATURE');
  if(await consumeNonce({reviewerId:p.reviewerId,nonce:p.nonce,expiresAt:p.expiresAt,expected})!==true)return fail('REPLAY_OR_STORAGE_UNAVAILABLE');
  return {verdict:p.decision,reason:'SIGNED_HUMAN_REVIEW',receiptDigest:digest(bytes),reviewerId:p.reviewerId,meaningVerifiedByMachine:false,answerStatus:'UNKNOWN',learnerStatus:'UNKNOWN'};
 }catch{return fail('INVALID_OR_UNAVAILABLE_REVIEW');}
}
