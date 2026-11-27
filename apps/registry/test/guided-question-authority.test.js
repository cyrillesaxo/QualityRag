import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,createHash} from 'node:crypto';
import {createQuestionReviewAuthority} from '../src/guided-question-authority.js';
const {publicKey}=generateKeyPairSync('ed25519');
const pem=publicKey.export({type:'spki',format:'pem'});
const digest=createHash('sha256').update(publicKey.export({type:'spki',format:'der'})).digest('hex');
const expected={ownerBinding:'a'.repeat(64),service:'lexyread',environment:'test',policyDigest:'b'.repeat(64),targetDigest:'c'.repeat(64)};
const input={reviewerId:'r',nonce:'nonce-fixture-00001',expiresAt:1800000000000,expected,grantVersion:'7',keyDigest:digest};
const row={public_key_pem:pem,grant_version:'7',revoked_at:null};
function fixture({current=row,insert=1,error=false}={}){
 const calls=[];
 const conn={query:async(sql,args)=>{calls.push({sql,args});if(sql.startsWith('SELECT'))return {rowCount:current?1:0,rows:current?[current]:[]};if(sql.startsWith('INSERT')){if(error)throw Error('db offline');return {rowCount:insert};}return {};},release:()=>calls.push({sql:'RELEASE'})};
 const pool={connect:async()=>conn,query:async()=>({rowCount:1,rows:[row]})};
 return {authority:createQuestionReviewAuthority(pool),calls};
}
test('lookup returns scoped key snapshot',async()=>{const {authority}=fixture();const r=await authority.lookupReviewer('r',expected);assert.equal(r.grantVersion,'7');assert.equal(r.key.asymmetricKeyType,'ed25519');});
test('lock then insert then commit and release',async()=>{const {authority,calls}=fixture();assert.equal(await authority.consumeNonce(input),true);assert.deepEqual(calls.map(c=>c.sql.split(' ')[0]),['BEGIN','SELECT','INSERT','COMMIT','RELEASE']);assert.match(calls[1].sql,/FOR UPDATE/);assert.deepEqual(calls[1].args,['r',expected.ownerBinding,expected.service,expected.environment,expected.policyDigest]);});
test('revocation or stale version rejects before nonce insertion',async()=>{for(const current of [null,{...row,revoked_at:'revoked'},{...row,grant_version:'8'}]){const {authority,calls}=fixture({current});assert.equal(await authority.consumeNonce(input),false);assert.deepEqual(calls.map(c=>c.sql.split(' ')[0]),['BEGIN','SELECT','ROLLBACK','RELEASE']);}});
test('changed key rejects even with same version',async()=>{const other=generateKeyPairSync('ed25519').publicKey.export({type:'spki',format:'pem'});const {authority,calls}=fixture({current:{...row,public_key_pem:other}});assert.equal(await authority.consumeNonce(input),false);assert.equal(calls.some(c=>c.sql.startsWith('INSERT')),false);});
test('duplicate nonce rolls back and database error propagates',async()=>{const a=fixture({insert:0});assert.equal(await a.authority.consumeNonce(input),false);assert.equal(a.calls.at(-2).sql,'ROLLBACK');const b=fixture({error:true});await assert.rejects(b.authority.consumeNonce(input),/db offline/);assert.equal(b.calls.at(-2).sql,'ROLLBACK');assert.equal(b.calls.at(-1).sql,'RELEASE');});
