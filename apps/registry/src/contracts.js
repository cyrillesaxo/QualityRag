// Data contracts (ADR-0002): each resource's signed declaration of how its data is classified,
// what may leave it, to whom, for which purpose and operation, and who may detokenize.
// Mirrors tools/activation_runtime/protection.py validate_contract; the Python runtime re-verifies
// every published contract, so this registry is a distribution point, never the only check.
import {createHash, verify as verifyEd25519} from 'node:crypto';
import {canonical} from './signed.js';

export const CONTRACT_SCHEMA='qualityrag.data-contract/v1';
export const ENVELOPE_SCHEMA='qualityrag.signed-observations/v1';
const CANONICAL='QR-CJSON-1';
const MAX_VALIDITY_MS=30*24*3600*1000;
const ID=/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const KEY_ID=/^[A-Za-z0-9._-]{1,128}$/;
const CLASS=/^[A-Z][A-Z0-9_]{1,31}$/;
const HOST=/^[a-z0-9.-]{1,253}$/;
const DERIVED={PAN:new Set(['brand','last4'])};
function demand(ok,code){if(!ok)throw new Error(code);}
const exact=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join('|')===[...keys].sort().join('|');
const ids=(v,max=256)=>Array.isArray(v)&&v.length<=max&&new Set(v).size===v.length&&v.every(x=>typeof x==='string'&&ID.test(x));
const classes=(v)=>Array.isArray(v)&&new Set(v).size===v.length&&v.every(x=>typeof x==='string'&&CLASS.test(x));

function rule(r,keys){
 demand(exact(r,keys),'INVALID_CONTRACT_RULE');
 demand(typeof r.destination==='string'&&ID.test(r.destination),'INVALID_CONTRACT_RULE');
 demand(ids(r.purposes)&&r.purposes.length>0&&ids(r.operations)&&r.operations.length>0,'INVALID_CONTRACT_RULE');
 return r;
}

export function validateContract(c){
 demand(c&&typeof c==='object'&&c.schema===CONTRACT_SCHEMA&&['source','destination'].includes(c.kind),'UNKNOWN_CONTRACT');
 demand(typeof c.id==='string'&&ID.test(c.id)&&typeof c.tenant==='string'&&ID.test(c.tenant),'INVALID_CONTRACT_ID');
 if(c.kind==='source'){
  demand(exact(c,['schema','kind','id','tenant','publisher_key_id','fields','text','scan','derive','release','detokenize']),'INVALID_SOURCE_CONTRACT');
  demand(typeof c.publisher_key_id==='string'&&ID.test(c.publisher_key_id),'INVALID_SOURCE_CONTRACT');
  demand(exact(c.fields,['public','sensitive'])&&ids(c.fields.public)&&Array.isArray(c.fields.sensitive)&&c.fields.sensitive.length<=64,'INVALID_FIELD_CLASSIFICATION');
  const names=new Set(c.fields.public);
  for(const s of c.fields.sensitive){
   demand(exact(s,['field','class','token'])&&typeof s.field==='string'&&ID.test(s.field)&&!names.has(s.field)&&
     typeof s.class==='string'&&CLASS.test(s.class)&&['deterministic','random'].includes(s.token),'INVALID_FIELD_CLASSIFICATION');
   names.add(s.field);
  }
  demand(['OWNER_CLASSIFIED','UNCLASSIFIED'].includes(c.text),'INVALID_TEXT_CLASSIFICATION');
  demand(classes(c.scan)&&c.scan.every(x=>x==='PAN'),'UNSUPPORTED_SCAN_CLASS');
  demand(c.derive&&typeof c.derive==='object'&&!Array.isArray(c.derive)&&Object.entries(c.derive).every(([k,v])=>
    DERIVED[k]&&Array.isArray(v)&&v.every(a=>DERIVED[k].has(a))),'UNAPPROVED_DERIVED_ATTRIBUTE');
  demand(Array.isArray(c.release)&&Array.isArray(c.detokenize),'INVALID_CONTRACT_RULE');
  const released=new Map();
  for(const r of c.release){rule(r,['destination','purposes','operations']);released.set(r.destination,r);}
  for(const r of c.detokenize){
   rule(r,['class','destination','purposes','operations']);
   demand(typeof r.class==='string'&&CLASS.test(r.class),'INVALID_CONTRACT_RULE');
   const base=released.get(r.destination);
   demand(base&&r.purposes.every(p=>base.purposes.includes(p))&&r.operations.every(o=>base.operations.includes(o)),
     'DETOKENIZE_BROADER_THAN_RELEASE');
  }
 }else{
  demand(exact(c,['schema','kind','id','tenant','channel','accepts','link_hosts','max_bytes','requires_review','review_classes']),'INVALID_DESTINATION_CONTRACT');
  demand(typeof c.channel==='string'&&ID.test(c.channel),'INVALID_DESTINATION_CONTRACT');
  demand(exact(c.accepts,['sources','classes','operations'])&&ids(c.accepts.sources)&&classes(c.accepts.classes)&&ids(c.accepts.operations),'INVALID_DESTINATION_ACCEPTANCE');
  demand(Array.isArray(c.link_hosts)&&c.link_hosts.every(h=>typeof h==='string'&&HOST.test(h)),'INVALID_LINK_HOSTS');
  demand(Number.isSafeInteger(c.max_bytes)&&c.max_bytes>=1&&c.max_bytes<=1000000&&typeof c.requires_review==='boolean','INVALID_DESTINATION_LIMITS');
  demand(classes(c.review_classes),'INVALID_DESTINATION_LIMITS');
 }
 return c;
}

export const contractSha256=(c)=>createHash('sha256').update(canonical(c)).digest('hex');

function instant(value){
 demand(typeof value==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value),'INVALID_CONTRACT_TIMESTAMP');
 const ms=Date.parse(value);demand(Number.isFinite(ms),'INVALID_CONTRACT_TIMESTAMP');return ms;
}

export function verifySignedContract(env,keys,now=new Date()){
 demand(exact(env,['schema','canonical','key_id','payload','signature']),'INVALID_SIGNED_CONTRACT');
 demand(env.schema===ENVELOPE_SCHEMA&&env.canonical===CANONICAL,'UNSUPPORTED_SIGNED_FORMAT');
 demand(KEY_ID.test(env.key_id||'')&&keys instanceof Map&&keys.has(env.key_id),'UNTRUSTED_CONTRACT_KEY');
 demand(typeof env.signature==='string'&&/^[A-Za-z0-9_-]{86}$/.test(env.signature),'INVALID_SIGNATURE_ENCODING');
 const sig=Buffer.from(env.signature,'base64url');
 demand(sig.length===64&&sig.toString('base64url')===env.signature,'INVALID_SIGNATURE_ENCODING');
 const domain=Buffer.from('QUALITYRAG/'+ENVELOPE_SCHEMA+'\x00','ascii');
 demand(verifyEd25519(null,Buffer.concat([domain,Buffer.from(canonical(env.payload),'utf8')]),keys.get(env.key_id),sig),'CONTRACT_SIGNATURE_INVALID');
 const p=env.payload;
 demand(exact(p,['data_contract','sequence','issued_at','expires_at']),'WRONG_ATTESTATION_PURPOSE');
 demand(Number.isSafeInteger(p.sequence)&&p.sequence>0,'INVALID_CONTRACT_SEQUENCE');
 const start=instant(p.issued_at),end=instant(p.expires_at);
 demand(start<end&&end-start<=MAX_VALIDITY_MS,'INVALID_CONTRACT_WINDOW');
 demand(now instanceof Date&&now.valueOf()>=start&&now.valueOf()<end,'CONTRACT_EXPIRED_OR_FUTURE');
 const c=validateContract(p.data_contract);
 return {contractId:c.id,kind:c.kind,tenant:c.tenant,sequence:p.sequence,keyId:env.key_id,
   sha256:contractSha256(c),issuedAt:p.issued_at,expiresAt:p.expires_at};
}
