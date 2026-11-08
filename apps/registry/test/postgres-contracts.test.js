import test from 'node:test';
import assert from 'node:assert/strict';
import {Pool} from 'pg';
import {generateKeyPairSync,sign as signEd25519} from 'node:crypto';
import {PgSignedRegistryStore} from '../src/pg-store.js';
import {migrate} from '../src/migrate.js';
import {canonical} from '../src/signed.js';

const url=process.env.PG_TEST_DATABASE_URL;
const {publicKey,privateKey}=generateKeyPairSync('ed25519');
const keys=new Map([['contract-governor',publicKey]]);
const stamp=(ms)=>new Date(ms).toISOString().replace(/\.\d+Z$/,'Z');
const destination=(id='pg-card-processor')=>({schema:'qualityrag.data-contract/v1',kind:'destination',id,tenant:'pg-bank',
 channel:'api',accepts:{sources:['pg-billing'],classes:['PAN'],operations:['charge']},link_hosts:[],max_bytes:20000,
 requires_review:false,review_classes:['PAN']});
function envelope(contract,sequence){
 const payload={data_contract:contract,sequence,issued_at:stamp(Date.now()-60000),expires_at:stamp(Date.now()+3600000)};
 const signature=signEd25519(null,Buffer.concat([Buffer.from('QUALITYRAG/qualityrag.signed-observations/v1\0'),
   Buffer.from(canonical(payload))]),privateKey).toString('base64url');
 return {schema:'qualityrag.signed-observations/v1',canonical:'QR-CJSON-1',key_id:'contract-governor',payload,signature};
}

test('Postgres contracts: transactional lifecycle, concurrency, rollback refusal, audit integrity',{skip:!url},async()=>{
 const pool=new Pool({connectionString:url,max:10});
 try{
  await migrate(pool);
  for(const t of ['qr_contract_events','qr_contract_promotions','qr_contract_heads'])
   await pool.query('DELETE FROM '+t+" WHERE contract_id LIKE 'pg-%'");
  const a=new PgSignedRegistryStore(pool),b=new PgSignedRegistryStore(pool);
  // Two writers race to stage the same sequence: exactly one wins.
  const raced=await Promise.allSettled([a.stageContract(envelope(destination(),1),'author',keys),
                                        b.stageContract(envelope(destination(),1),'author',keys)]);
  assert.equal(raced.filter(r=>r.status==='fulfilled').length,1);
  await assert.rejects(a.approveContract('pg-card-processor',1,'author',keys,{enforceSeparation:true}),/SELF_APPROVAL_FORBIDDEN/);
  await a.approveContract('pg-card-processor',1,'approver',keys,{enforceSeparation:true});
  await assert.rejects(a.publishContract('pg-card-processor',1,'approver',keys,{enforceSeparation:true}),/SAME_ACTOR_PROMOTION_FORBIDDEN/);
  assert.equal((await a.publishContract('pg-card-processor',1,'publisher',keys,{enforceSeparation:true})).status,'PUBLISHED');
  await assert.rejects(a.stageContract(envelope(destination(),1),'author',keys),/SIGNED_SEQUENCE_ROLLBACK/);
  await assert.rejects(a.stageContract(envelope({...destination(),tenant:'other'},2),'author',keys),/CONTRACT_IDENTITY_CHANGE_FORBIDDEN/);
  const listed=await b.publishedContracts('pg-bank',keys);
  assert.equal(listed.contracts.length,1);
  assert.equal((await b.resolveContract('pg-card-processor',keys)).sequence,1);
  assert.ok((await a.verifyContractIntegrity()).contracts>=1);
  // Editing an audit event is detected.
  await pool.query("UPDATE qr_contract_events SET actor='someone-else' WHERE contract_id='pg-card-processor' AND action='APPROVED'");
  await assert.rejects(a.verifyContractIntegrity(),/GOVERNANCE_AUDIT_INTEGRITY_FAILURE/);
  await pool.query("UPDATE qr_contract_events SET actor='approver' WHERE contract_id='pg-card-processor' AND action='APPROVED'");
  const state=await a.state();
  assert.ok(state.contractBindings.some(x=>x.contractId==='pg-card-processor'&&x.sequence===1));
 }finally{await pool.end()}
});
