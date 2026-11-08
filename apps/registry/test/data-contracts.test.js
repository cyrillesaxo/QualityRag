import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {spawnSync} from 'node:child_process';
import {createPublicKey,generateKeyPairSync,sign as signEd25519} from 'node:crypto';
import {mkdtempSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {RegistryStore} from '../src/store.js';
import {createHandler} from '../src/server.js';
import {canonical} from '../src/signed.js';
import {validateContract,verifySignedContract} from '../src/contracts.js';

const REPO=fileURLToPath(new URL('../../../',import.meta.url));
const {publicKey,privateKey}=generateKeyPairSync('ed25519');
const keys=new Map([['contract-governor',publicKey]]);
const stamp=(ms)=>new Date(ms).toISOString().replace(/\.\d+Z$/,'Z');

function source(over={}){
 return {schema:'qualityrag.data-contract/v1',kind:'source',id:'billing-contracts',tenant:'acme-bank',
  publisher_key_id:'billing-ledger',text:'OWNER_CLASSIFIED',scan:['PAN'],
  fields:{public:['customer','due_date'],sensitive:[{field:'card_number',class:'PAN',token:'deterministic'}]},
  derive:{PAN:['brand','last4']},
  release:[{destination:'card-processor',purposes:['payment'],operations:['charge']}],
  detokenize:[{class:'PAN',destination:'card-processor',purposes:['payment'],operations:['charge']}],...over};
}
function envelope(contract,sequence,{key=privateKey,keyId='contract-governor',from=-60000,to=3600000}={}){
 const payload={data_contract:contract,sequence,issued_at:stamp(Date.now()+from),expires_at:stamp(Date.now()+to)};
 const signature=signEd25519(null,Buffer.concat([Buffer.from('QUALITYRAG/qualityrag.signed-observations/v1\0'),
   Buffer.from(canonical(payload))]),key).toString('base64url');
 return {schema:'qualityrag.signed-observations/v1',canonical:'QR-CJSON-1',key_id:keyId,payload,signature};
}
function store(){
 const dir=mkdtempSync(path.join(tmpdir(),'qr-contracts-'));
 return {dir,store:new RegistryStore(path.join(dir,'registry.json'))};
}

test('validation mirrors the runtime: detokenization can never be broader than release',()=>{
 assert.equal(validateContract(source()).id,'billing-contracts');
 assert.throws(()=>validateContract(source({detokenize:[{class:'PAN',destination:'card-processor',purposes:['payment'],operations:['charge','refund']}]})),/DETOKENIZE_BROADER_THAN_RELEASE/);
 assert.throws(()=>validateContract(source({scan:['IBAN']})),/UNSUPPORTED_SCAN_CLASS/);
 assert.throws(()=>validateContract(source({derive:{PAN:['full_number']}})),/UNAPPROVED_DERIVED_ATTRIBUTE/);
 assert.throws(()=>validateContract({...source(),extra:1}),/INVALID_SOURCE_CONTRACT/);
});

test('stage, approve, publish and resolve with separation of duties and no rollback',()=>{
 const {dir,store:s}=store();
 try{
  assert.equal(s.stageContract(envelope(source(),1),'author',keys).status,'STAGED');
  assert.throws(()=>s.approveContract('billing-contracts',1,'author',keys,{enforceSeparation:true}),/SELF_APPROVAL_FORBIDDEN/);
  s.approveContract('billing-contracts',1,'approver',keys,{enforceSeparation:true});
  assert.throws(()=>s.publishContract('billing-contracts',1,'approver',keys,{enforceSeparation:true}),/SAME_ACTOR_PROMOTION_FORBIDDEN/);
  assert.equal(s.publishContract('billing-contracts',1,'publisher',keys,{enforceSeparation:true}).status,'PUBLISHED');
  const resolved=s.resolveContract('billing-contracts',keys);
  assert.equal(resolved.sequence,1);
  assert.equal(verifySignedContract(resolved.signedContract,keys).contractId,'billing-contracts');
  assert.throws(()=>s.stageContract(envelope(source(),1),'author',keys),/SIGNED_SEQUENCE_ROLLBACK/);
  assert.throws(()=>s.stageContract(envelope(source({tenant:'other-bank'}),2),'author',keys),/CONTRACT_IDENTITY_CHANGE_FORBIDDEN/);
  assert.equal(s.publishedContracts('acme-bank',keys).contracts.length,1);
  assert.equal(s.publishedContracts('other-bank',keys).contracts.length,0);
  assert.ok(s.data.governanceAudit.some(e=>e.action==='SIGNED_CONTRACT_PUBLISHED'));
  // Reloading re-verifies the governance hash chain, contracts included.
  assert.doesNotThrow(()=>new RegistryStore(path.join(dir,'registry.json')));
 }finally{rmSync(dir,{recursive:true,force:true})}
});

test('untrusted, tampered, expired and wrong-purpose envelopes are refused',()=>{
 const {dir,store:s}=store();
 try{
  const other=generateKeyPairSync('ed25519').privateKey;
  assert.throws(()=>s.stageContract(envelope(source(),1,{key:other,keyId:'stranger'}),'a',keys),/UNTRUSTED_CONTRACT_KEY/);
  assert.throws(()=>s.stageContract(envelope(source(),1,{key:other}),'a',keys),/CONTRACT_SIGNATURE_INVALID/);
  const tampered=envelope(source(),1);tampered.payload.data_contract.detokenize=[];
  assert.throws(()=>s.stageContract(tampered,'a',keys),/CONTRACT_SIGNATURE_INVALID/);
  assert.throws(()=>s.stageContract(envelope(source(),1,{from:-7200000,to:-3600000}),'a',keys),/CONTRACT_EXPIRED_OR_FUTURE/);
 }finally{rmSync(dir,{recursive:true,force:true})}
});

test('HTTP: validate, stage, approve, publish, list published by tenant',async()=>{
 const {dir,store:s}=store();
 const server=http.createServer(createHandler(s,'secret',{trustedContractKeys:keys}));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port;
 const call=(method,p,body)=>fetch(base+p,{method,headers:{authorization:'Bearer secret','content-type':'application/json'},
   body:body?JSON.stringify(body):undefined}).then(async r=>({status:r.status,body:await r.json()}));
 try{
  assert.equal((await call('POST','/v1/contracts/validate',source())).body.valid,true);
  assert.equal((await call('POST','/v1/contracts/validate',source({text:'MAYBE'}))).status,400);
  assert.equal((await call('POST','/v1/contracts/signed',envelope(source(),3))).status,201);
  assert.equal((await call('GET','/v1/contracts/resolve/billing-contracts')).status,404);
  assert.equal((await call('POST','/v1/contracts/signed/billing-contracts/3/approve')).body.status,'APPROVED');
  assert.equal((await call('POST','/v1/contracts/signed/billing-contracts/3/publish')).body.status,'PUBLISHED');
  const listed=await call('GET','/v1/contracts/published?tenant=acme-bank');
  assert.equal(listed.body.contracts.length,1);
  const state=(await call('GET','/v1/state')).body;
  assert.equal(state.contractBindings[0].sequence,3);
  assert.ok(!('envelope' in state.contractPromotions[0]));
 }finally{server.close();rmSync(dir,{recursive:true,force:true})}
});

test('Python-signed contract round-trips through the registry into the Python runtime',()=>{
 const sign=String.raw`import base64,json,sys
from datetime import datetime,timedelta,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from tools.activation_runtime import protection as p
c=json.loads(sys.argv[1]);key=Ed25519PrivateKey.generate()
now=datetime.now(timezone.utc).replace(microsecond=0);st=lambda v:v.isoformat().replace('+00:00','Z')
env=p.sign_contract(c,key,key_id='python-governor',issued_at=st(now-timedelta(minutes=1)),expires_at=st(now+timedelta(hours=1)),sequence=5)
raw=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
der=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
print(json.dumps({'env':env,'der':base64.urlsafe_b64encode(der).decode().rstrip('='),'raw':base64.b64encode(raw).decode()}))`;
 const signed=spawnSync('python3',['-c',sign,JSON.stringify(source())],{cwd:REPO,encoding:'utf8',timeout:20000});
 assert.equal(signed.status,0,signed.stderr);
 const data=JSON.parse(signed.stdout);
 const pk=new Map([['python-governor',createPublicKey({key:Buffer.from(data.der,'base64url'),format:'der',type:'spki'})]]);
 const {dir,store:s}=store();
 try{
  s.stageContract(data.env,'author',pk);s.approveContract('billing-contracts',5,'approver',pk);
  s.publishContract('billing-contracts',5,'publisher',pk);
  const published=s.publishedContracts('acme-bank',pk);
  const file=path.join(dir,'published.json');writeFileSync(file,JSON.stringify(published));
  const load=String.raw`import base64,json,sys
from datetime import datetime,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from tools.activation_runtime import protection as p
pub=Ed25519PublicKey.from_public_bytes(base64.b64decode(sys.argv[2]))
now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
c=p.load_contracts(json.load(open(sys.argv[1]))['contracts'],{'python-governor':pub},as_of=now)
print(json.dumps(sorted(c)))`;
  const loaded=spawnSync('python3',['-c',load,file,data.raw],{cwd:REPO,encoding:'utf8',timeout:20000});
  assert.equal(loaded.status,0,loaded.stderr);
  assert.deepEqual(JSON.parse(loaded.stdout),['billing-contracts']);
 }finally{rmSync(dir,{recursive:true,force:true})}
});
