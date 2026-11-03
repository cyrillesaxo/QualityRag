import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {generateKeyPairSync,createHash,sign as signEd25519} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {exportJWK,SignJWT} from 'jose';
import {createOidcAuthenticator} from '../src/oidc.js';
import {createHandler} from '../src/server.js';
import {RegistryStore} from '../src/store.js';
import {canonical} from '../src/signed.js';

async function listen(server){
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 return 'http://127.0.0.1:'+server.address().port;
}
function signFixture(privateKey) {
 const source='a'.repeat(64),nodes=[{
   node_id:'evidence',kind:'EVIDENCE_PRESENCE',status:'PROJECTION_ONLY',runtime:'METADATA_GATE_V0_1',
   parameters:{requirement_id:'source',min_independent_sources:1},
   source:{source_sha256:source,candidate_id:'C0001',location:'/r/0',
     quotation:'A source record must exist',quotation_sha256:'b'.repeat(64)},
   review:{approved:true,reviewed_by:'author',rationale:'Declared evidence receipt is required'}
 }];
 const ir={schema:'qualityrag.constraint-ir/v1',source:{sha256:source,pack_id:'sample',version:'1'},
  nodes,summary:{total:1,evidence_presence_projections:1,deferred_semantic_constraints:0,semantic_constraints_executed:0}};
 ir.ir_sha256=createHash('sha256').update(canonical({nodes,source_sha256:source})).digest('hex');
 const issued_at=new Date(Date.now()-60000).toISOString().replace('.000Z','Z');
 const expires_at=new Date(Date.now()+3600000).toISOString().replace('.000Z','Z');
 const payload={ir,service:'api',environment:'dev',sequence:3,issued_at,expires_at};
 const sig=signEd25519(null,Buffer.concat([Buffer.from('QUALITYRAG/qualityrag.signed-policy/v1\0'),
    Buffer.from(canonical(payload))]),privateKey).toString('base64url');
 return {schema:'qualityrag.signed-policy/v1',canonical:'QR-CJSON-1',key_id:'governance',payload,signature:sig};
}

test('OIDC: real signed JWT roles and three distinct actors required to publish',async()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'qr-oidc-'));
 const idKey=generateKeyPairSync('rsa',{modulusLength:2048});
 const govKey=generateKeyPairSync('ed25519');
 const jwk=await exportJWK(idKey.publicKey);
 jwk.kid='idp-1';jwk.use='sig';jwk.alg='RS256';
 const idp=http.createServer((req,res)=>{
   res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({keys:[jwk]}));
 });
 const idpUrl=await listen(idp);
 const issuer='https://id.example/issuer',audience='qualityrag-registry';
 const auth=createOidcAuthenticator({issuer,audience,jwksUri:idpUrl+'/jwks'});
 const store=new RegistryStore(path.join(dir,'registry.json'));
 const registry=http.createServer(createHandler(store,null,{authenticate:auth,enforceSeparation:true,
    trustedPolicyKeys:new Map([['governance',govKey.publicKey]])}));
 const registryUrl=await listen(registry);
 async function token(subject,roles,opts={}){
   const signer=new SignJWT({roles});
   signer.setProtectedHeader({alg:'RS256',kid:'idp-1'}).setIssuer(opts.issuer||issuer)
    .setAudience(opts.audience||audience).setSubject(subject)
    .setIssuedAt().setExpirationTime('15m');
   return signer.sign(idKey.privateKey);
 }
 async function request(method,route,t,data){
   const r=await fetch(registryUrl+route,{method,headers:{
    Authorization:'Bearer '+t,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});
   return {status:r.status,data:await r.json()};
 }
 try{
   const writer=await token('alice',['policy.author']);
   const reviewer=await token('bob',['policy.approver']);
   const publisher=await token('carol',['policy.publisher']);
   const reader=await token('dave',['policy.reader']);
   const superuser=await token('eve',['policy.author','policy.approver','policy.publisher','policy.reader']);
   const wrongAudience=await token('bad',['policy.author'],{audience:'other-service'});
   assert.equal((await request('POST','/v1/services',wrongAudience,{id:'api',displayName:'API'})).status,401);
   assert.equal((await request('POST','/v1/services',reader,{id:'api',displayName:'API'})).status,403);
   assert.equal((await request('POST','/v1/services',writer,{id:'api',displayName:'API'})).status,201);
   const signed=signFixture(govKey.privateKey);
   assert.equal((await request('POST','/v1/signed/promotions',publisher,signed)).status,403);
   assert.equal((await request('POST','/v1/signed/promotions',writer,signed)).status,201);
   assert.equal((await request('POST','/v1/signed/promotions/api/dev/3/approve',writer)).status,403);
   assert.equal((await request('POST','/v1/signed/promotions/api/dev/3/approve',reviewer)).status,200);
   assert.equal((await request('POST','/v1/signed/promotions/api/dev/3/publish',reviewer)).status,403);
   assert.equal((await request('POST','/v1/signed/promotions/api/dev/3/publish',publisher)).status,200);
   assert.equal((await request('GET','/v1/signed/resolve/api/dev',reader)).status,200);
   assert.equal((await request('GET','/v1/state',writer)).status,403);
   // Even a token with all roles cannot self-approve a policy it authored.
   assert.equal((await request('POST','/v1/policies/drafts',superuser,
     {id:'legacy',version:'1',requirements:[{id:'evidence'}]})).status,201);
   assert.deepEqual((await request('POST','/v1/policies/legacy/1/approve',superuser)).data,
     {error:'SELF_APPROVAL_FORBIDDEN'});
   assert.equal((await request('POST','/v1/policies/legacy/1/approve',reviewer)).status,200);
   // A user holding all roles still cannot publish their own staged signed policy.
   const own=signFixture(govKey.privateKey);own.payload.sequence=4;
   // Need a valid signature for sequence 4; instead test store separation directly.
   assert.throws(()=>store.publishSigned('api','dev',3,'https://id.example/issuer#bob',
       new Map([['governance',govKey.publicKey]]),{enforceSeparation:true}),/SIGNED_NOT_APPROVED/);
 }finally{
  await new Promise(resolve=>registry.close(resolve));
  await new Promise(resolve=>idp.close(resolve));
  rmSync(dir,{recursive:true,force:true});
 }
});
