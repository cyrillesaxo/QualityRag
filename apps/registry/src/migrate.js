import {Pool} from 'pg';
import {readFileSync,readdirSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const ROOT=fileURLToPath(new URL('../migrations/',import.meta.url));
const digest=(data)=>createHash('sha256').update(data).digest('hex');
const expected=()=>readdirSync(ROOT).filter(f=>/^[0-9]{3}_[a-z0-9_-]+\.sql$/.test(f)).sort()
 .map(name=>({name,sql:readFileSync(path.join(ROOT,name),'utf8'),
               sha256:digest(readFileSync(path.join(ROOT,name)))}));

export async function migrate(pool){
 const conn=await pool.connect();
 try{
  await conn.query('BEGIN');
  // Serialize all instances running migrations against the same database.
  await conn.query('SELECT pg_advisory_xact_lock(714073,1001)');
  await conn.query('CREATE TABLE IF NOT EXISTS qr_schema_migrations (name text PRIMARY KEY, sha256 char(64) NOT NULL, installed_at timestamptz NOT NULL DEFAULT now())');
  for(const migration of expected()){
   const existing=await conn.query('SELECT sha256 FROM qr_schema_migrations WHERE name=$1',[migration.name]);
   if(existing.rowCount){
    if(existing.rows[0].sha256!==migration.sha256)throw new Error('MIGRATION_CHECKSUM_MISMATCH:'+migration.name);
    continue;
   }
   await conn.query(migration.sql);
   await conn.query('INSERT INTO qr_schema_migrations(name,sha256) VALUES($1,$2)',
    [migration.name,migration.sha256]);
  }
  await conn.query('COMMIT');
 }catch(e){
  await conn.query('ROLLBACK');
  throw e;
 }finally{conn.release()}
}

export async function checkMigrations(pool){
 const rows=await pool.query('SELECT name,sha256 FROM qr_schema_migrations');
 const installed=new Map(rows.rows.map(x=>[x.name,x.sha256]));
 const files=expected();
 if(installed.size!==files.length)throw new Error('MIGRATION_VERSION_MISMATCH');
 for(const file of files)if(installed.get(file.name)!==file.sha256)
  throw new Error('MIGRATION_CHECKSUM_MISMATCH:'+file.name);
 return {version:files.at(-1)?.name||null,count:files.length};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const url=process.env.DATABASE_URL;
 if(!url){console.error('DATABASE_URL_REQUIRED');process.exitCode=1}
 else {
  const pool=new Pool({connectionString:url,connectionTimeoutMillis:3000,statement_timeout:15000});
  try{await migrate(pool);console.log('QualityRag migrations applied and checksums validated')}
  catch(e){console.error('QualityRag migration failed:',e.message);process.exitCode=1}
  finally{await pool.end()}
 }
}
