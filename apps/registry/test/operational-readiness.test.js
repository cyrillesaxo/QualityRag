import test from 'node:test';
import assert from 'node:assert/strict';
import {Pool} from 'pg';
import http from 'node:http';
import {createHandler} from '../src/server.js';
import {migrate,checkMigrations} from '../src/migrate.js';
import {PgSignedRegistryStore} from '../src/pg-store.js';
import {readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const url=process.env.PG_TEST_DATABASE_URL;

test('migration locking, checksums, clean restart and readiness failures', {skip:!url}, async()=>{
 const admin=new Pool({connectionString:url,max:2});
 const schema='qr_operational_test';
 await admin.query('CREATE SCHEMA IF NOT EXISTS '+schema);
 const opts={connectionString:url,max:5,options:'-c search_path='+schema};
 const poolA=new Pool(opts),poolB=new Pool(opts);
 const service='qr-operational-test';
 try{
  await Promise.all([migrate(poolA),migrate(poolB)]);
  const migration=await checkMigrations(poolA);
  const files=readdirSync(fileURLToPath(new URL('../migrations/',import.meta.url))).filter(f=>/^[0-9]{3}_.+\.sql$/.test(f));
  assert.equal(migration.count,files.length);
  assert.equal(migration.version,files.sort().at(-1));
  await poolA.query('DELETE FROM qr_governance_events WHERE service_id=$1',[service]);
  await poolA.query('DELETE FROM qr_signed_promotions WHERE service_id=$1',[service]);
  await poolA.query('DELETE FROM qr_governance_heads WHERE service_id=$1',[service]);
  await poolA.query('DELETE FROM qr_scopes WHERE service_id=$1',[service]);
  await poolA.query('DELETE FROM qr_services WHERE service_id=$1',[service]);
  const storeA=new PgSignedRegistryStore(poolA);
  await storeA.register({id:service,displayName:'Operational recovery fixture'});
  await poolA.query('INSERT INTO qr_scopes(service_id,environment) VALUES($1,$2)',[service,'test']);
  await poolA.query('INSERT INTO qr_governance_heads(service_id,environment) VALUES($1,$2)',[service,'test']);
  assert.equal((await storeA.readiness()).ready,true);
  const storeB=new PgSignedRegistryStore(poolB);
  assert.equal((await storeB.readiness()).checkedScopes>=1,true);
  // Corrupt an audit chain head: readiness is now strictly unavailable.
  await poolA.query('UPDATE qr_governance_heads SET last_hash=$3 WHERE service_id=$1 AND environment=$2',
      [service,'test','f'.repeat(64)]);
  await assert.rejects(()=>storeB.readiness(),/GOVERNANCE_AUDIT_INTEGRITY_FAILURE/);
  await poolA.query('UPDATE qr_governance_heads SET last_hash=repeat($3,64) WHERE service_id=$1 AND environment=$2',
      [service,'test','0']);
  assert.equal((await storeB.readiness()).ready,true);
  // Drift in migration history must block startup/readiness.
  const conn=await poolA.connect();
  try{
   await conn.query('BEGIN');
   await conn.query("UPDATE qr_schema_migrations SET sha256=repeat('f',64) WHERE name=$1",
      [migration.version]);
   await assert.rejects(()=>checkMigrations(conn),/MIGRATION_CHECKSUM_MISMATCH/);
  }finally{await conn.query('ROLLBACK');conn.release()}
 }finally{
  await poolA.query('DELETE FROM qr_governance_events WHERE service_id=$1',[service]).catch(()=>{});
  await poolA.query('DELETE FROM qr_signed_promotions WHERE service_id=$1',[service]).catch(()=>{});
  await poolA.query('DELETE FROM qr_governance_heads WHERE service_id=$1',[service]).catch(()=>{});
  await poolA.query('DELETE FROM qr_scopes WHERE service_id=$1',[service]).catch(()=>{});
  await poolA.query('DELETE FROM qr_services WHERE service_id=$1',[service]).catch(()=>{});
  await poolA.end();await poolB.end();
  await admin.query('DROP SCHEMA IF EXISTS '+schema+' CASCADE');
  await admin.end();
 }
});

test('readiness HTTP is 503 on failed backend and liveness remains distinct',async()=>{
 const unavailable={readiness:async()=>{throw new Error('database credentials secret')}};
 const server=http.createServer(createHandler(unavailable,'development-token'));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const url='http://127.0.0.1:'+server.address().port;
  const live=await fetch(url+'/health'),ready=await fetch(url+'/ready');
  assert.equal(live.status,200);
  assert.equal(ready.status,503);
  const detail=await ready.json();
  assert.deepEqual(detail,{ready:false,reason:'REGISTRY_NOT_READY'});
  assert.ok(!JSON.stringify(detail).includes('database credentials'));
 }finally{await new Promise(resolve=>server.close(resolve))}
});
