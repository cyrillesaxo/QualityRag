import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash, generateKeyPairSync,sign as signEd25519} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {RegistryStore} from '../src/store.js';
import {canonical,verifySignedPolicy} from '../src/signed.js';
import {createHandler} from '../src/server.js';

const {publicKey,privateKey}=generateKeyPairSync('ed25519');
const trusted=new Map([['governance-v1',publicKey]]);
const start=new Date(Date.now()-5*60*1000).toISOString().replace('.000Z','Z');
const end=new Date(Date.now()+24*60*60*1000).toISOString().replace('.000Z','Z');
const now=new Date();
function fixture(sequence=1,service='tutor',environment='dev'){
 const source='a'.repeat(64);
 const node={
  node_id:'source',kind:'EVIDENCE_PRESENCE',status:'PROJECTION_ONLY',
  runtime:'METADATA_GATE_V0_1',parameters:{requirement_id:'record',min_independent_sources:1},
  source:{source_sha256:source,candidate_id:'C0001',location:'/rules/0',
    quotation:'A record must be present',quotation_sha256:'b'.repeat(64)},
  review:{approved:true,reviewed_by:'reviewer',rationale:'Require supporting evidence'}
 };
 const nodes=[node];
 const ir={schema:'qualityrag.constraint-ir/v1',
  source:{sha256:source,pack_id:'lesson',version:'1.0.0'},nodes,
  summary:{total:1,evidence_presence_projections:1,deferred_semantic_constraints:0,
    semantic_constraints_executed:0},
  scope:'INSPECTION_DERIVED_CANDIDATES_ONLY',assurance:'NO_AUTOMATIC_SEMANTIC_ENFORCEMENT'};
 ir.ir_sha256=createHash('sha256').update(canonical({source_sha256:source,nodes})).digest('hex');
 const payload={ir,service,environment,sequence,issued_at:start,expires_at:end};
 const signature=signEd25519(null,Buffer.concat([
  Buffer.from('QUALITYRAG/qualityrag.signed-policy/v1\0','ascii'),Buffer.from(canonical(payload),'utf8')
 ]),privateKey).toString('base64url');
 return {schema:'qualityrag.signed-policy/v1',canonical:'QR-CJSON-1',key_id:'governance-v1',
   payload,signature};
}
function storeWithService(folder){
 const store=new RegistryStore(path.join(folder,'state.json'));
 store.register({id:'tutor',displayName:'Tutor'},'operator');
 return store;
}
test('externally signed IR stages, approves, publishes and resolves with persistent monotonic version',()=>{
 const folder=mkdtempSync(path.join(tmpdir(),'qualityrag-signed-'));
 try{
  const s=storeWithService(folder),bundle=fixture(4);
  assert.equal(verifySignedPolicy(bundle,trusted,now).sequence,4);
  const staged=s.stageSigned(bundle,'operator',trusted);
  assert.equal(staged.status,'STAGED');
  assert.throws(()=>s.publishSigned('tutor','dev',4,'operator',trusted),/SIGNED_NOT_APPROVED/);
  assert.throws(()=>s.stageSigned(bundle,'operator',trusted),/SIGNED_SEQUENCE_EXISTS/);
  assert.equal(s.approveSigned('tutor','dev',4,'operator',trusted).status,'APPROVED');
  assert.equal(s.publishSigned('tutor','dev',4,'operator',trusted).status,'PUBLISHED');
  assert.deepEqual(s.resolveSigned('tutor','dev',trusted).signedPolicy,bundle);
  const restarted=new RegistryStore(path.join(folder,'state.json'));
  assert.equal(restarted.resolveSigned('tutor','dev',trusted).sequence,4);
  assert.throws(()=>restarted.stageSigned(fixture(3),'operator',trusted),/SIGNED_SEQUENCE_ROLLBACK/);
  restarted.stageSigned(fixture(5),'operator',trusted);
  assert.equal(restarted.resolveSigned('tutor','dev',trusted).sequence,4);
  restarted.approveSigned('tutor','dev',5,'operator',trusted);
  restarted.publishSigned('tutor','dev',5,'operator',trusted);
  assert.equal(restarted.resolveSigned('tutor','dev',trusted).sequence,5);
  assert.ok(restarted.data.audit.some(x=>x.action==='SIGNED_POLICY_PUBLISHED'));
 } finally {rmSync(folder,{recursive:true,force:true})}
});
test('tamper, bad key, expired, scope mismatch, unicode and float cannot be staged',()=>{
 const folder=mkdtempSync(path.join(tmpdir(),'qualityrag-signchecks-'));
 try {
  const s=storeWithService(folder);
  const modified=structuredClone(fixture());modified.payload.ir.nodes[0].parameters.requirement_id='changed';
  assert.throws(()=>s.stageSigned(modified,'operator',trusted),/POLICY_SIGNATURE_INVALID/);
  assert.throws(()=>s.stageSigned(fixture(),'operator',new Map()),/UNTRUSTED_SIGNING_KEY/);
  assert.throws(()=>verifySignedPolicy(fixture(),trusted,new Date(Date.now()+45*24*60*60*1000)),/SIGNED_POLICY_EXPIRED_OR_FUTURE/);
  assert.throws(()=>s.stageSigned(fixture(1,'other'),'operator',trusted),/UNKNOWN_SERVICE/);
  assert.throws(()=>canonical({test:'é'}),/SIGNED_ASCII_PROFILE_REQUIRED/);
  assert.throws(()=>canonical({value:1.1}),/SIGNED_NUMBER_UNSUPPORTED/);
  assert.equal(Object.keys(s.data.signedPromotions).length,0);
 }finally{rmSync(folder,{recursive:true,force:true})}
});
test('signed endpoints require registry bearer token and never expose signing private keys',async()=>{
 const folder=mkdtempSync(path.join(tmpdir(),'qualityrag-signed-http-'));
 const store=storeWithService(folder);
 const server=http.createServer(createHandler(store,'operator-token',{trustedPolicyKeys:trusted}));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const url='http://127.0.0.1:'+server.address().port;
 const request=async(route,method='GET',value,token='operator-token')=>{
  const res=await fetch(url+route,{method,
   headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
   body:value===undefined?undefined:JSON.stringify(value)});
  return {status:res.status,body:await res.json()};
 };
 try{
  assert.equal((await request('/v1/signed/resolve/tutor/dev','GET',undefined,'wrong')).status,401);
  const bundle=fixture(1);
  assert.equal((await request('/v1/signed/promotions','POST',bundle)).status,201);
  assert.equal((await request('/v1/signed/resolve/tutor/dev')).status,404);
  assert.equal((await request('/v1/signed/promotions/tutor/dev/1/approve','POST')).status,200);
  assert.equal((await request('/v1/signed/promotions/tutor/dev/1/publish','POST')).status,200);
  const response=await request('/v1/signed/resolve/tutor/dev');
  assert.equal(response.status,200);
  assert.deepEqual(response.body.signedPolicy,bundle);
  assert.equal((await request('/v1/signed/promotions','POST',bundle)).status,409);
 }finally{
  await new Promise(resolve=>server.close(resolve));
  rmSync(folder,{recursive:true,force:true});
 }
});
