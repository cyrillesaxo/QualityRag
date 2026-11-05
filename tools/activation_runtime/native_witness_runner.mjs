// Only the pinned original APX module is evaluated; request fields are inert data.
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {stripTypeScriptTypes} from 'node:module';
try {
  let raw='';
  for await (const chunk of process.stdin) {
    raw+=chunk.toString('utf8');
    if(Buffer.byteLength(raw)>524288) throw Error('Input budget');
  }
  const rows=JSON.parse(raw);
  if(!Array.isArray(rows)||rows.length>1000) throw Error('Witness budget');
  const ids=new Set();
  for(const row of rows) {
    if(!row||Object.keys(row).sort().join(',')!=='id,independence_key'
       ||typeof row.id!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(row.id)
       ||ids.has(row.id)||typeof row.independence_key!=='string'
       ||!/^[a-f0-9]{64}$/.test(row.independence_key)) throw Error('Typed witness input');
    ids.add(row.id);
  }
  const source=readFileSync(resolve(process.argv[2],'packages/apx-evidence/src/index.ts'));
  if(createHash('sha256').update(source).digest('hex')!=='49c690848c4dcb1022f815d5deb258ddd074317eb0cc3cebde40a99d069199ee') throw Error('Source mismatch');
  const module=await import('data:text/javascript;base64,'+Buffer.from(stripTypeScriptTypes(source.toString('utf8'))).toString('base64'));
  process.stdout.write(JSON.stringify(module.buildWitnessGraph(rows)));
} catch {
  process.stderr.write('Canonical APX WitnessGraph unavailable or input refused.\n');
  process.exitCode=2;
}
