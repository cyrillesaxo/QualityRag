import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createPublicKey} from 'node:crypto';
import {verifySignedPolicy} from '../src/signed.js';

// The private key is generated in memory by the existing Python signer.
// Only the signed bundle and DER *public* key cross this test process boundary.
const py=String.raw`import base64,json
from datetime import datetime,timedelta,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from signed_bundles import sign_policy
from typed_ir import _fingerprint
source='a'*64
node={'node_id':'source','kind':'EVIDENCE_PRESENCE','runtime':'METADATA_GATE_V0_1',
'status':'PROJECTION_ONLY','parameters':{'requirement_id':'record','min_independent_sources':1},
'source':{'source_sha256':source,'candidate_id':'C0001','location':'/a',
'quotation':'A source record must be present','quotation_sha256':'b'*64},
'review':{'approved':True,'reviewed_by':'author','rationale':'Source evidence is required'}}
nodes=[node]
ir={'schema':'qualityrag.constraint-ir/v1','source':{'sha256':source,'pack_id':'demo','version':'1.0'},
'nodes':nodes,'summary':{'total':1,'evidence_presence_projections':1,'deferred_semantic_constraints':0,
'semantic_constraints_executed':0},'scope':'INSPECTION_DERIVED_CANDIDATES_ONLY',
'assurance':'NO_AUTOMATIC_SEMANTIC_ENFORCEMENT'}
ir['ir_sha256']=_fingerprint({'source_sha256':source,'nodes':nodes})
key=Ed25519PrivateKey.generate()
now=datetime.now(timezone.utc).replace(microsecond=0)
stamp=lambda value:value.isoformat().replace('+00:00','Z')
bundle=sign_policy(ir,key,key_id='python-governance',service='demo-api',
environment='dev',sequence=7,issued_at=stamp(now-timedelta(minutes=5)),
expires_at=stamp(now+timedelta(hours=2)))
pub=key.public_key().public_bytes(encoding=serialization.Encoding.DER,
format=serialization.PublicFormat.SubjectPublicKeyInfo)
print(json.dumps({'bundle':bundle,'key':base64.urlsafe_b64encode(pub).decode('ascii').rstrip('=')}))
`;
test('Python-signed QR-CJSON-1 ASCII bundle verifies in Node without private-key exchange',()=>{
 const result=spawnSync('python3',['-c',py],{
   env:{...process.env,PYTHONPATH:'tools/packspec_compiler'},encoding:'utf8',timeout:10000
 });
 assert.equal(result.status,0,result.stderr);
 const data=JSON.parse(result.stdout);
 const publicKey=createPublicKey({key:Buffer.from(data.key,'base64url'),format:'der',type:'spki'});
 const meta=verifySignedPolicy(data.bundle,new Map([['python-governance',publicKey]]));
 assert.equal(meta.sequence,7);
 assert.equal(meta.serviceId,'demo-api');
 assert.equal(meta.environment,'dev');
 const altered=structuredClone(data.bundle);
 altered.payload.ir.nodes[0].parameters.requirement_id='wrong';
 assert.throws(()=>verifySignedPolicy(altered,new Map([['python-governance',publicKey]])),/POLICY_SIGNATURE_INVALID/);
});
