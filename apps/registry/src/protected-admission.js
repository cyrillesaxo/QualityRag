// Offline signer approvals + read-only live Google byte verification for a
// narrow protected-source admission pilot. The server never holds private keys.
// Reuses QualityRAG's QR-CJSON-1 / signed-observations/v1 wire format for an
// ASCII-only, strictly bounded subset, not arbitrary cross-language JSON.
import fs from 'node:fs';
import {createPublicKey, createHash, verify as edVerify} from 'node:crypto';
import {evaluateEvidence} from './evidence-ledger.js';

const SCHEMA='qualityrag.signed-observations/v1';
const CANONICAL='QR-CJSON-1';
const KIND='qualityrag.protected-drive-human-review/v1';
const DOMAIN=Buffer.from('QUALITYRAG/'+SCHEMA+'\0','ascii');
const POLICY_PREFIX='UNSIGNED-V0.1-PACK-SHA256:';
const ID=/^[A-Za-z0-9._-]{1,128}$/;
const SOURCE=/^google_drive\/[a-f0-9]{32}$/;
const HEX=/^[a-f0-9]{64}$/;
const ORIGIN=/^org_[a-f0-9]{24,64}$/;
const ASCII=/^[\x20-\x7e]*$/;
const sha=value=>createHash('sha256').update(value).digest('hex');
function check(condition,reason){if(!condition)throw Error(reason)}
function only(value,keys,reason){
 check(value&&typeof value==='object'&&!Array.isArray(value)&&
  Object.keys(value).length===keys.length&&keys.every(k=>Object.hasOwn(value,k)),reason);
}
function ascii(value,max=200){
 return typeof value==='string'&&value.length>0&&value.length<=max&&ASCII.test(value);
}
function allowed(value,depth=0){
 check(depth<=12,'PROTECTED_NONCANONICAL_REVIEW');
 if(Array.isArray(value)){check(value.length<=50,'PROTECTED_NONCANONICAL_REVIEW');
   value.forEach(x=>allowed(x,depth+1));return}
 if(value!==null&&typeof value==='object'){
   check(Object.keys(value).length<=20,'PROTECTED_NONCANONICAL_REVIEW');
   for(const [k,v] of Object.entries(value)){
     check(ascii(k,160),'PROTECTED_NONCANONICAL_REVIEW');
     allowed(v,depth+1);
   }return
 }
 check(value===null||typeof value==='boolean'||
   (Number.isSafeInteger(value))||typeof value==='string'&&ascii(value,256),
   'PROTECTED_NONCANONICAL_REVIEW');
}
export function reviewCanonical(value){
 allowed(value);
 const sorted=(x)=>Array.isArray(x)?x.map(sorted):
   x!==null&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort()
     .map(key=>[key,sorted(x[key])])):x;
 const raw=Buffer.from(JSON.stringify(sorted(value)),'utf8');
 check(raw.length<=32768,'PROTECTED_NONCANONICAL_REVIEW');
 return raw;
}
export function loadProtectedReviewTrust(file){
 check(typeof file==='string'&&file,'PROTECTED_REVIEW_KEYS_REQUIRED');
 const stat=fs.lstatSync(file);
 check(stat.isFile()&&!stat.isSymbolicLink()&&stat.size<16384,
  'INVALID_PROTECTED_REVIEW_KEYS');
 const json=JSON.parse(fs.readFileSync(file,'utf8'));
 only(json,['custodian','meaningReviewer'],'INVALID_PROTECTED_REVIEW_KEYS');
 const keys={};
 for(const role of ['custodian','meaningReviewer']){
   const value=json[role];
   only(value,['keyId','publicKeyPem'],'INVALID_PROTECTED_REVIEW_KEYS');
   check(ID.test(value.keyId)&&typeof value.publicKeyPem==='string'&&
     value.publicKeyPem.length<=2048,'INVALID_PROTECTED_REVIEW_KEYS');
   const key=createPublicKey(value.publicKeyPem);
   check(key.asymmetricKeyType==='ed25519','INVALID_PROTECTED_REVIEW_KEYS');
   keys[role]={keyId:value.keyId,key};
 }
 check(keys.custodian.keyId!==keys.meaningReviewer.keyId&&
   keys.custodian.key.export({type:'spki',format:'der'}).toString('hex')!==
   keys.meaningReviewer.key.export({type:'spki',format:'der'}).toString('hex'),
   'PROTECTED_REVIEW_SIGNERS_MUST_DIFFER');
 return keys;
}
function verifyEnvelope(envelope,trust,role){
 only(envelope,['schema','canonical','key_id','payload','signature'],
  'INVALID_PROTECTED_REVIEW_ENVELOPE');
 check(envelope.schema===SCHEMA&&envelope.canonical===CANONICAL&&
   envelope.key_id===trust[role].keyId,'UNTRUSTED_PROTECTED_REVIEW_KEY');
 check(typeof envelope.signature==='string'&&
   /^[A-Za-z0-9_-]{86}$/.test(envelope.signature),
   'INVALID_PROTECTED_REVIEW_SIGNATURE');
 const bytes=Buffer.from(envelope.signature,'base64url');
 check(bytes.length===64&&bytes.toString('base64url')===envelope.signature,
   'INVALID_PROTECTED_REVIEW_SIGNATURE');
 const signed=Buffer.concat([DOMAIN,reviewCanonical(envelope.payload)]);
 check(edVerify(null,signed,trust[role].key,bytes),
   'INVALID_PROTECTED_REVIEW_SIGNATURE');
 return envelope.payload;
}
export function verifyHumanReviewAttestations(custody,meaning,trust,
 {serviceId,environment,policySha256,subject,folderId,now=Date.now()}){
 check(trust?.custodian?.key&&trust?.meaningReviewer?.key,
   'PROTECTED_REVIEW_KEYS_NOT_CONFIGURED');
 const a=verifyEnvelope(custody,trust,'custodian');
 const b=verifyEnvelope(meaning,trust,'meaningReviewer');
 check(reviewCanonical(a).equals(reviewCanonical(b)),
  'PROTECTED_REVIEW_SIGNERS_DISAGREE');
 only(a,['service','environment','policy_signature','nonce','issued_at',
   'expires_at','witnesses','observations'],'INVALID_PROTECTED_REVIEW_PAYLOAD');
 check(a.service===serviceId&&a.environment===environment&&
   a.policy_signature===POLICY_PREFIX+policySha256,
   'PROTECTED_REVIEW_POLICY_MISMATCH');
 check(typeof a.nonce==='string'&&ID.test(a.nonce)&&a.nonce.length>=16,
   'PROTECTED_REVIEW_NONCE_INVALID');
 const issued=Date.parse(a.issued_at),expires=Date.parse(a.expires_at);
 check(Number.isFinite(issued)&&Number.isFinite(expires)&&
   a.issued_at===new Date(issued).toISOString()&&
   a.expires_at===new Date(expires).toISOString()&&
   issued<=now+30000&&issued>=now-10*60000&&
   issued<expires&&expires-issued<=10*60000&&now<expires,
   'PROTECTED_REVIEW_EXPIRED');
 only(a.observations,['kind','owner_binding','folder_id','review_basis',
   'origin_basis'],'INVALID_PROTECTED_REVIEW_CONTEXT');
 check(a.observations.kind===KIND&&
   a.observations.owner_binding===sha('qualityrag.review-owner/v1:'+subject)&&
   a.observations.folder_id===folderId&&
   a.observations.review_basis==='HUMAN_SEMANTIC_APPROVAL'&&
   a.observations.origin_basis==='CUSTODIAN_ATTESTED',
   'PROTECTED_REVIEW_OWNER_OR_SCOPE_MISMATCH');
 check(Array.isArray(a.witnesses)&&a.witnesses.length>=1&&a.witnesses.length<=8,
   'PROTECTED_REVIEW_WITNESS_LIMIT');
 const seen=new Set();
 for(const row of a.witnesses){
   only(row,['sourceId','revision','requirementId','lineNumber',
     'lineSha256','origin','status'],'INVALID_PROTECTED_REVIEW_WITNESS');
   check(SOURCE.test(row.sourceId)&&HEX.test(row.revision)&&HEX.test(row.lineSha256)&&
     ascii(row.requirementId,80)&&ORIGIN.test(row.origin)&&
     Number.isSafeInteger(row.lineNumber)&&row.lineNumber>=1&&
     row.lineNumber<=6000&&
     ['SUPPORTS','CONTRADICTS','UNKNOWN'].includes(row.status),
     'INVALID_PROTECTED_REVIEW_WITNESS');
   const identity=row.sourceId+':'+row.requirementId+':'+row.lineNumber;
   check(!seen.has(identity),'PROTECTED_REVIEW_DUPLICATE_WITNESS');
   seen.add(identity);
 }
 return {payload:a,signerIds:[trust.custodian.keyId,trust.meaningReviewer.keyId],
   signedPayloadSha256:sha(reviewCanonical(a)),
   custodySignatureSha256:sha(custody.signature),
   reviewSignatureSha256:sha(meaning.signature)};
}
export function humanReviewDecision(pack,policySha256,witnesses,asOf){
 check(pack&&Array.isArray(pack.requirements)&&pack.requirements.length>0,
   'INVALID_PROTECTED_POLICY');
 // The local Drive bridge does not know original publication timestamps,
 // and cannot justify independence of multiple distinct declared origins.
 check(pack.requirements.every(r=>
   (r.min_independent_sources??1)===1&&r.max_age_seconds===undefined),
   'PROTECTED_POLICY_REQUIRES_UNSUPPORTED_PROOF');
 const valid=new Set(pack.requirements.map(r=>r.id));
 check(witnesses.every(x=>valid.has(x.requirementId)),
   'PROTECTED_REVIEW_UNKNOWN_REQUIREMENT');
 const evidence=witnesses.map((w,i)=>({
   id:'ev_'+sha('human-attested:'+i+':'+w.sourceId+':'+w.lineNumber).slice(0,32),
   requirement_id:w.requirementId,
   origin:w.origin,
   source_ref:'src_'+sha(w.sourceId).slice(0,32),
   status:w.status,observed_at:asOf
 }));
 const result=evaluateEvidence(pack,evidence,asOf);
 // Never turn a human signature into a claim of independently proven source
 // truth. Admission means authorized to use these signed assertions only.
 return {result,evidence,policySha256,meaning:'HUMAN_SIGNED_NOT_FACTUALLY_PROVEN',
   origin:'CUSTODIAN_SIGNED_NOT_INDEPENDENTLY_PROVEN'};
}
