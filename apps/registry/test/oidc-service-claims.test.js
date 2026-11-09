import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {generateKeyPairSync} from 'node:crypto';
import {SignJWT,exportJWK} from 'jose';
import {createOidcAuthenticator,ROLE} from '../src/oidc.js';

test('signed service claims are bounded, scoped and fail closed',async()=>{
 const key=generateKeyPairSync('rsa',{modulusLength:2048});
 const jwk=await exportJWK(key.publicKey);
 jwk.kid='test-key';jwk.alg='RS256';jwk.use='sig';
 const server=http.createServer((req,res)=>{
  if(req.url!=='/jwks'){res.writeHead(404);res.end();return;}
  res.writeHead(200,{'content-type':'application/json'});
  res.end(JSON.stringify({keys:[jwk]}));
 });
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 try{
  const issuer='https://issuer.example',audience='qualityrag-registry';
  const authenticate=createOidcAuthenticator({issuer,audience,
   jwksUri:'http://127.0.0.1:'+server.address().port+'/jwks'});
  async function issue({services,roles=['drive.reader','policy.reader'],aud=audience}={}){
   const payload={roles};
   if(services!==undefined)payload.qualityrag_services=services;
   return new SignJWT(payload).setProtectedHeader({alg:'RS256',kid:'test-key'})
    .setIssuer(issuer).setAudience(aud).setSubject('customer-1')
    .setIssuedAt().setExpirationTime('15m').sign(key.privateKey);
  }
  const good=await authenticate(await issue({services:['claims@prod']}));
  assert.equal(good.subject,issuer+'#customer-1');
  assert.ok(good.roles.has(ROLE.driveRead));
  assert.ok(good.roles.has(ROLE.read));
  assert.deepEqual([...good.evidenceServices],['claims@prod']);
  const absent=await authenticate(await issue());
  assert.equal(absent.evidenceServices.size,0);
  for(const services of ['claims@prod',['bad service@prod'],['claims'],[42],null]){
   assert.equal(await authenticate(await issue({services})),null,
     'unsupported service-claim shape must reject token');
  }
  assert.equal(await authenticate(await issue({services:['claims@prod'],aud:'wrong'})),null);
  const ignored=await authenticate(await issue({roles:['not.an.allowed.role'],services:[]}));
  assert.equal(ignored.roles.size,0);
 }finally{await new Promise(done=>server.close(done))}
});
