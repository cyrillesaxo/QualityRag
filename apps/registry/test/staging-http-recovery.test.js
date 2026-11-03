import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:http';
import {generateKeyPairSync,createHash,randomUUID,sign as edSign} from 'node:crypto';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Pool} from 'pg';
import {SignJWT,exportJWK} from 'jose';
import {canonical,verifySignedPolicy} from '../src/signed.js';
import {checkMigrations} from '../src/migrate.js';

const database=process.env.PG_TEST_DATABASE_URL;
const serverFile=fileURLToPath(new URL('../src/server.js',import.meta.url));

async function listen(server){
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 return 'http://127.0.0.1:'+server.address().port;
}
async function unusedPort(){
 const server=createServer();
 await listen(server);
 const port=server.address().port;
 await new Promise(resolve=>server.close(resolve));
 return port;
}
function signedPolicy(privateKey,service,sequence,environment='staging'){
 const sha='a'.repeat(64);
 const nodes=[{node_id:'required-evidence',kind:'EVIDENCE_PRESENCE',
  status:'PROJECTION_ONLY',runtime:'METADATA_GATE_V0_1',
  parameters:{requirement_id:'source-witness',min_independent_sources:1},
  source:{candidate_id:'C0001',location:'/rules/0',source_sha256:sha,
   quotation:'The final answer must have a source witness',quotation_sha256:'b'.repeat(64)},
  review:{approved:true,reviewed_by:'example-reviewer',
   rationale:'This is a strictly scoped verified-source witness requirement'}}];
 const ir={schema:'qualityrag.constraint-ir/v1',
  source:{sha256:sha,pack_id:'staging-example',version:'1'},
  nodes,summary:{total:1,evidence_presence_projections:1,
    deferred_semantic_constraints:0,semantic_constraints_executed:0}};
 ir.ir_sha256=createHash('sha256').update(canonical({source_sha256:sha,nodes})).digest('hex');
 const issued_at=new Date(Date.now()-60_000).toISOString().replace('.000Z','Z');
 const expires_at=new Date(Date.now()+3_600_000).toISOString().replace('.000Z','Z');
 const payload={ir,service,environment,sequence,issued_at,expires_at};
 const signature=edSign(null,Buffer.concat([
    Buffer.from('QUALITYRAG/qualityrag.signed-policy/v1\0','ascii'),
    Buffer.from(canonical(payload),'utf8')]),privateKey).toString('base64url');
 return {schema:'qualityrag.signed-policy/v1',canonical:'QR-CJSON-1',
  key_id:'staging-governance',payload,signature};
}
async function request(base,route,accessToken,method='GET',body){
 const res=await fetch(base+route,{
  method,headers:{'Authorization':'Bearer '+accessToken,'Content-Type':'application/json'},
  body:body===undefined?undefined:JSON.stringify(body),
  signal:AbortSignal.timeout(5000)});
 return {status:res.status,body:await res.json()};
}
async function waitReady(base,child){
 let last;
 for(let attempt=0;attempt<70;attempt++){
  if(child.exitCode!==null)throw new Error('Registry exited before readiness: '+child.exitCode);
  try{
   const result=await fetch(base+'/ready',{signal:AbortSignal.timeout(400)});
   if(result.status===200)return;
   last=result.status;
  }catch(error){last=error.message}
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw new Error('Registry readiness deadline: '+last);
}
async function stop(child){
 if(child.exitCode!==null)return;
 child.kill('SIGTERM');
 await Promise.race([
  once(child,'exit'),
  new Promise((_,reject)=>setTimeout(()=>reject(new Error('Registry shutdown timeout')),5000))
 ]);
}
async function cleanScope(pool,service){
 await pool.query('DELETE FROM qr_governance_events WHERE service_id=$1',[service]);
 await pool.query('DELETE FROM qr_signed_promotions WHERE service_id=$1',[service]);
 await pool.query('DELETE FROM qr_governance_heads WHERE service_id=$1',[service]);
 await pool.query('DELETE FROM qr_scopes WHERE service_id=$1',[service]);
 await pool.query('DELETE FROM qr_services WHERE service_id=$1',[service]);
}

test('staging HTTP: OIDC+PostgreSQL stage/approve/publish, process restart, rollback refused',
 {skip:!database,timeout:45000},async()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'qualityrag-stage-'));
 const service='stage-'+randomUUID().slice(0,12);
 const pool=new Pool({connectionString:database,max:4});
 const govKey=generateKeyPairSync('ed25519');
 const authKey=generateKeyPairSync('rsa',{modulusLength:2048});
 const issuer='https://staging-issuer.example/qualityrag';
 const jwk=await exportJWK(authKey.publicKey);
 Object.assign(jwk,{kid:'staging-oidc',use:'sig',alg:'RS256'});
 const jwks=createServer((req,res)=>{
  if(req.url!=='/jwks'){res.writeHead(404);res.end();return}
  res.writeHead(200,{'content-type':'application/json'});
  res.end(JSON.stringify({keys:[jwk]}));
 });
 let processA,processB;
 try{
  await checkMigrations(pool);
  const oidcURL=await listen(jwks);
  const pub=govKey.publicKey.export({format:'der',type:'spki'}).toString('base64url');
  const trustFile=path.join(dir,'trusted-policy-keys.json');
  writeFileSync(trustFile,JSON.stringify({'staging-governance':pub}),{mode:0o600});
  const port=await unusedPort();
  const base='http://127.0.0.1:'+port;
  const env={...process.env,PORT:String(port),
    QUALITYRAG_BIND_HOST:'127.0.0.1',
    QUALITYRAG_REGISTRY_BACKEND:'postgres',
    QUALITYRAG_AUTH_MODE:'oidc',
    QUALITYRAG_POLICY_KEYS_FILE:trustFile,
    QUALITYRAG_OIDC_ISSUER:issuer,
    QUALITYRAG_OIDC_AUDIENCE:'qualityrag-registry',
    QUALITYRAG_OIDC_JWKS_URI:oidcURL+'/jwks',
    DATABASE_URL:database};
  function start(){
   const child=spawn(process.execPath,[serverFile],{env,stdio:'ignore'});
   child.on('error',()=>{});
   return child;
  }
  async function token(sub,roles,audience='qualityrag-registry'){
   return new SignJWT({roles}).setProtectedHeader({alg:'RS256',kid:'staging-oidc'})
    .setIssuer(issuer).setAudience(audience).setSubject(sub)
    .setIssuedAt().setExpirationTime('15m').sign(authKey.privateKey);
  }
  const author=await token('author',['policy.author']);
  const approver=await token('approver',['policy.approver']);
  const publisher=await token('publisher',['policy.publisher']);
  const reader=await token('reader',['policy.reader']);
  const wrongAudience=await token('wrong',['policy.author'],'incorrect-audience');
  const first=signedPolicy(govKey.privateKey,service,10);
  const second=signedPolicy(govKey.privateKey,service,11);
  processA=start();
  await waitReady(base,processA);

  assert.equal((await request(base,'/v1/services',wrongAudience,'POST',
    {id:service,displayName:'Staging check'})).status,401);
  assert.equal((await request(base,'/v1/services',author,'POST',
    {id:service,displayName:'Staging check'})).status,201);
  assert.equal((await request(base,'/v1/signed/promotions',reader,'POST',first)).status,403);
  assert.equal((await request(base,'/v1/signed/promotions',author,'POST',first)).status,201);
  const route=(n,action)=>'/v1/signed/promotions/'+service+'/staging/'+n+'/'+action;
  assert.equal((await request(base,route(10,'approve'),author,'POST')).status,403);
  assert.equal((await request(base,route(10,'approve'),approver,'POST')).status,200);
  assert.equal((await request(base,route(10,'publish'),approver,'POST')).status,403);
  assert.equal((await request(base,route(10,'publish'),publisher,'POST')).status,200);

  const published=await request(base,'/v1/signed/resolve/'+service+'/staging',reader);
  assert.equal(published.status,200);
  assert.equal(published.body.sequence,10);
  assert.equal(published.body.signedPolicy.signature,first.signature);
  assert.equal(verifySignedPolicy(published.body.signedPolicy,
    new Map([['staging-governance',govKey.publicKey]])).sequence,10);

  await stop(processA);
  processA=undefined;
  processB=start();
  await waitReady(base,processB);
  const recovered=await request(base,'/v1/signed/resolve/'+service+'/staging',reader);
  assert.equal(recovered.status,200);
  assert.deepEqual(recovered.body.signedPolicy,first);
  assert.equal((await request(base,'/v1/signed/promotions',author,'POST',first)).status,409);

  assert.equal((await request(base,'/v1/signed/promotions',author,'POST',second)).status,201);
  assert.equal((await request(base,route(11,'approve'),approver,'POST')).status,200);
  assert.equal((await request(base,route(11,'publish'),publisher,'POST')).status,200);
  const advanced=await request(base,'/v1/signed/resolve/'+service+'/staging',reader);
  assert.equal(advanced.body.sequence,11);
  assert.equal((await request(base,route(10,'publish'),publisher,'POST')).status,409);
  const sequence=await pool.query(
   'SELECT published_sequence FROM qr_scopes WHERE service_id=$1 AND environment=$2',
    [service,'staging']);
  assert.equal(Number(sequence.rows[0].published_sequence),11);
  const steps=await pool.query(
   'SELECT action FROM qr_governance_events WHERE service_id=$1 ORDER BY event_id',[service]);
  assert.deepEqual(steps.rows.map(x=>x.action),
   ['STAGED','APPROVED','PUBLISHED','STAGED','APPROVED','PUBLISHED']);

  await stop(processB);processB=undefined;
  processA=start();
  await waitReady(base,processA);
  assert.equal((await request(base,'/v1/signed/resolve/'+service+'/staging',reader)).body.sequence,11);
 }finally{
  if(processA)await stop(processA).catch(()=>processA.kill('SIGKILL'));
  if(processB)await stop(processB).catch(()=>processB.kill('SIGKILL'));
  await cleanScope(pool,service).catch(()=>{});
  await pool.end();
  await new Promise(resolve=>jwks.close(resolve));
  rmSync(dir,{recursive:true,force:true});
 }
});
