// QR-CJSON-1 signing verifier for the local Studio registry.
// This is a deliberately restricted ASCII-only interoperable subset of the
// Python signer, not RFC 8785 and not a production identity service.
import fs from 'node:fs';
import {createPublicKey, createHash, verify as verifyEd25519} from 'node:crypto';

export const SIGNED_SCHEMA='qualityrag.signed-policy/v1';
const CANONICAL='QR-CJSON-1';
const MAX_BYTES=524288;
const MAX_VALIDITY_MS=30*24*3600*1000;
const SAFE=/^[\x20-\x7e]*$/;
const IDENT=/^[A-Za-z0-9._-]{1,128}$/;
const HEX=/^[a-f0-9]{64}$/;
function demand(ok,code){if(!ok)throw new Error(code);}
export function canonical(value,depth=0){
 demand(depth<40,'SIGNED_JSON_DEPTH');
 if(value===null)return 'null';
 if(typeof value==='string'){
   demand(value.length<=50000 && SAFE.test(value),'SIGNED_ASCII_PROFILE_REQUIRED');
   return JSON.stringify(value);
 }
 if(typeof value==='number'){
   demand(Number.isSafeInteger(value),'SIGNED_NUMBER_UNSUPPORTED');
   return JSON.stringify(value);
 }
 if(typeof value==='boolean')return JSON.stringify(value);
 if(Array.isArray(value))return '['+value.map(x=>canonical(x,depth+1)).join(',')+']';
 demand(value && typeof value==='object' && Object.getPrototypeOf(value)===Object.prototype,'SIGNED_JSON_INVALID');
 const keys=Object.keys(value).sort();
 for(const key of keys)demand(key.length<=160 && SAFE.test(key),'SIGNED_KEY_INVALID');
 return '{'+keys.map(key=>JSON.stringify(key)+':'+canonical(value[key],depth+1)).join(',')+'}';
}
export function loadTrustedPolicyKeys(file){
 demand(typeof file==='string'&&file.length>0,'POLICY_TRUST_STORE_REQUIRED');
 const stat=fs.statSync(file);demand(stat.size<=200000,'POLICY_TRUST_STORE_TOO_LARGE');
 const parsed=JSON.parse(fs.readFileSync(file,'utf8'));
 demand(parsed && !Array.isArray(parsed) && typeof parsed==='object','INVALID_TRUST_STORE');
 const result=new Map();
 for(const [id,spki] of Object.entries(parsed)){
   demand(IDENT.test(id) && typeof spki==='string','INVALID_TRUST_KEY');
   const key=createPublicKey({key:Buffer.from(spki,'base64url'),format:'der',type:'spki'});
   demand(key.asymmetricKeyType==='ed25519','INVALID_TRUST_KEY_TYPE');
   result.set(id,key);
 }
 demand(result.size>0,'EMPTY_TRUST_STORE');
 return result;
}
function instant(value){
 demand(typeof value==='string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value),'INVALID_POLICY_TIMESTAMP');
 const millis=Date.parse(value);
 demand(Number.isFinite(millis),'INVALID_POLICY_TIMESTAMP');
 return millis;
}
export function verifySignedPolicy(bundle,keys,now=new Date()){
 demand(bundle && typeof bundle==='object' && !Array.isArray(bundle),'INVALID_SIGNED_BUNDLE');
 demand(Object.keys(bundle).sort().join('|')==='canonical|key_id|payload|schema|signature','INVALID_SIGNED_BUNDLE');
 demand(bundle.schema===SIGNED_SCHEMA && bundle.canonical===CANONICAL,'UNSUPPORTED_SIGNED_FORMAT');
 demand(IDENT.test(bundle.key_id||'') && keys instanceof Map && keys.has(bundle.key_id),'UNTRUSTED_SIGNING_KEY');
 demand(typeof bundle.signature==='string' && /^[A-Za-z0-9_-]{86}$/.test(bundle.signature),'INVALID_SIGNATURE_ENCODING');
 const sig=Buffer.from(bundle.signature,'base64url');
 demand(sig.length===64 && sig.toString('base64url')===bundle.signature,'INVALID_SIGNATURE_ENCODING');
 const body=Buffer.from(canonical(bundle.payload),'utf8');
 demand(body.length<=MAX_BYTES,'SIGNED_BUNDLE_TOO_LARGE');
 const domain=Buffer.from('QUALITYRAG/'+SIGNED_SCHEMA+'\x00','ascii');
 demand(verifyEd25519(null,Buffer.concat([domain,body]),keys.get(bundle.key_id),sig),'POLICY_SIGNATURE_INVALID');
 const p=bundle.payload;
 demand(p && typeof p==='object' && IDENT.test(p.service||'') && IDENT.test(p.environment||''),'INVALID_SIGNED_BINDING');
 demand(Number.isSafeInteger(p.sequence) && p.sequence>0,'INVALID_SIGNED_SEQUENCE');
 const start=instant(p.issued_at),end=instant(p.expires_at);
 demand(start<end && end-start<=MAX_VALIDITY_MS,'INVALID_SIGNED_WINDOW');
 demand(now instanceof Date && Number.isFinite(now.valueOf()) && now.valueOf()>=start && now.valueOf()<end,'SIGNED_POLICY_EXPIRED_OR_FUTURE');
 demand(p.ir && p.ir.schema==='qualityrag.constraint-ir/v1' && p.ir.source &&
        HEX.test(p.ir.source.sha256||'') && Array.isArray(p.ir.nodes) &&
        p.ir.nodes.length>0 && p.ir.nodes.length<=240,'INVALID_SIGNED_IR');
 const irDigest=createHash('sha256').update(canonical({source_sha256:p.ir.source.sha256,nodes:p.ir.nodes})).digest('hex');
 demand(irDigest===p.ir.ir_sha256,'SIGNED_IR_DIGEST_MISMATCH');
 demand(p.ir.nodes.every(n=>n?.review?.approved===true &&
        n?.source?.source_sha256===p.ir.source.sha256),'UNAPPROVED_SIGNED_IR');
 const nodeIds=new Set(),requirements=new Set();
 let evidenceCount=0,semanticCount=0;
 for(const node of p.ir.nodes){
   demand(node && typeof node.node_id==='string'&&node.node_id.length>0&&!nodeIds.has(node.node_id),'INVALID_SIGNED_NODE');
   nodeIds.add(node.node_id);
   if(node.kind==='EVIDENCE_PRESENCE'){
     demand(node.status==='PROJECTION_ONLY' && node.runtime==='METADATA_GATE_V0_1' &&
       typeof node.parameters?.requirement_id==='string'&&node.parameters.requirement_id.length>0 &&
       Number.isSafeInteger(node.parameters?.min_independent_sources) &&
       node.parameters.min_independent_sources>0 &&
       !requirements.has(node.parameters.requirement_id),'INVALID_SIGNED_EVIDENCE_NODE');
     requirements.add(node.parameters.requirement_id);evidenceCount++;
   }else{
     demand(['TEMPORAL','PROBE','AUTHORITY','PREDICATE'].includes(node.kind),'INVALID_SIGNED_NODE_KIND');
     semanticCount++;
   }
 }
 demand(p.ir.summary?.total===p.ir.nodes.length &&
        p.ir.summary.evidence_presence_projections===evidenceCount &&
        p.ir.summary.deferred_semantic_constraints===semanticCount &&
        p.ir.summary.semantic_constraints_executed===0,'SIGNED_IR_INVENTORY_MISMATCH');
 return {serviceId:p.service,environment:p.environment,sequence:p.sequence,issuedAt:p.issued_at,
         expiresAt:p.expires_at,irSha256:p.ir.ir_sha256,sourceSha256:p.ir.source.sha256,
         keyId:bundle.key_id};
}
