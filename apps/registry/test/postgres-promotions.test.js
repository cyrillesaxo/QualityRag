import test from 'node:test';
import assert from 'node:assert/strict';
import {Pool} from 'pg';
import {createHash,generateKeyPairSync,sign as signEd25519} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {PgSignedRegistryStore} from '../src/pg-store.js';
import {canonical} from '../src/signed.js';

const url=process.env.PG_TEST_DATABASE_URL;
const {publicKey,privateKey}=generateKeyPairSync('ed25519');
const keys=new Map([['test-governance',publicKey]]);
function policy(sequence,service='pg-test',environment='dev'){
 const sha='b'.repeat(64);
 const nodes=[{node_id:'witness',kind:'EVIDENCE_PRESENCE',status:'PROJECTION_ONLY',
  runtime:'METADATA_GATE_V0_1',parameters:{requirement_id:'source',min_independent_sources:1},
  source:{source_sha256:sha,candidate_id:'C0001',location:'/evidence',
   quotation:'Primary source required',quotation_sha256:'a'.repeat(64)},
  review:{approved:true,reviewed_by:'reviewer',rationale:'Evidence witness requirement'}}];
 const ir={schema:'qualityrag.constraint-ir/v1',source:{sha256:sha,pack_id:'test',version:'1'},
  nodes,summary:{total:1,evidence_presence_projections:1,deferred_semantic_constraints:0,semantic_constraints_executed:0}};
 ir.ir_sha256=createHash('sha256').update(canonical({source_sha256:sha,nodes})).digest('hex');
 const issued_at=new Date(Date.now()-300000).toISOString().replace('.000Z','Z');
 const expires_at=new Date(Date.now()+3600000).toISOString().replace('.000Z','Z');
 const payload={ir,service,environment,sequence,issued_at,expires_at};
 const signature=signEd25519(null,Buffer.concat([Buffer.from('QUALITYRAG/qualityrag.signed-policy/v1\0'),Buffer.from(canonical(payload))]),privateKey).toString('base64url');
 return {schema:'qualityrag.signed-policy/v1',canonical:'QR-CJSON-1',key_id:'test-governance',payload,signature};
}
test('Postgres transactions serialize concurrent stages/publish and prohibit rollback', {skip:!url},async()=>{
 const pool=new Pool({connectionString:url,max:10});
 try{
  const ddl=readFileSync(fileURLToPath(new URL('../migrations/001_signed_postgres.sql',import.meta.url)),'utf8');
  await pool.query(ddl);
  await pool.query("DELETE FROM qr_governance_events WHERE service_id='pg-test'");
  await pool.query("DELETE FROM qr_signed_promotions WHERE service_id='pg-test'");
  await pool.query("DELETE FROM qr_governance_heads WHERE service_id='pg-test'");
  await pool.query("DELETE FROM qr_scopes WHERE service_id='pg-test'");
  await pool.query("DELETE FROM qr_services WHERE service_id='pg-test'");
  const a=new PgSignedRegistryStore(pool),b=new PgSignedRegistryStore(pool);
  await a.register({id:'pg-test',displayName:'Postgres signed tests'});
  const one=policy(1),two=policy(2);
  const first=await Promise.allSettled([a.stageSigned(one,'alice',keys),b.stageSigned(one,'alice',keys)]);
  assert.equal(first.filter(x=>x.status==='fulfilled').length,1);
  assert.equal(first.filter(x=>x.status==='rejected').length,1);
  assert.match(first.find(x=>x.status==='rejected').reason.message,/SIGNED_SEQUENCE_EXISTS/);
  await a.approveSigned('pg-test','dev',1,'bob',keys,{enforceSeparation:true});
  await b.stageSigned(two,'alice',keys);
  await b.approveSigned('pg-test','dev',2,'bob',keys,{enforceSeparation:true});
  const winners=await Promise.allSettled([
   a.publishSigned('pg-test','dev',2,'carol',keys,{enforceSeparation:true}),
   b.publishSigned('pg-test','dev',2,'david',keys,{enforceSeparation:true})
  ]);
  assert.equal(winners.filter(x=>x.status==='fulfilled').length,1);
  assert.equal(winners.filter(x=>x.status==='rejected').length,1);
  assert.equal((await a.resolveSigned('pg-test','dev',keys)).sequence,2);
  await assert.rejects(()=>b.publishSigned('pg-test','dev',1,'carol',keys,{enforceSeparation:true}),/SIGNED_SEQUENCE_ROLLBACK/);
  await assert.rejects(()=>b.stageSigned(policy(1),'alice',keys),/SIGNED_SEQUENCE_ROLLBACK/);
  const state=await a.state();
  assert.equal(state.signedBindings[0].sequence,2);
  const audits=await pool.query("SELECT action,previous_hash,event_hash FROM qr_governance_events WHERE service_id='pg-test' ORDER BY event_id");
  assert.equal(audits.rowCount,5);
  assert.equal(audits.rows[0].previous_hash,'0'.repeat(64));
  for(let i=1;i<audits.rows.length;i++)assert.equal(audits.rows[i].previous_hash,audits.rows[i-1].event_hash);
  const changed=structuredClone(two);
  changed.payload.sequence=99;
  await assert.rejects(()=>b.stageSigned(changed,'alice',keys),/POLICY_SIGNATURE_INVALID/);
  const conflict=await pool.query("SELECT published_sequence FROM qr_scopes WHERE service_id='pg-test' AND environment='dev'");
  assert.equal(Number(conflict.rows[0].published_sequence),2);
 }finally{await pool.end()}
});
