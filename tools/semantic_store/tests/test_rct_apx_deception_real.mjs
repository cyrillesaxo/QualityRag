import test from 'node:test';
import assert from 'node:assert/strict';
import {loadNativeDeceptionCensus} from '../rct_apx_deception_native.mjs';

if(!process.env.APX_PACKAGES_ROOT) {
  throw new Error('Real original APX evidence build required for native D15');
}
const engine=await loadNativeDeceptionCensus();
const families=['DW','DD','DS'];
const axes=['DEPTH','BREADTH','CHANNEL','FRAME','IMPLICATURE'];
const catalog=families.flatMap(family=>axes.map(axis=>family+'_'+axis));
const allPass=catalog.map(id=>({
  id,status:'PASS',evidenceRefs:['synthetic-observation:'+id]
}));

test('real original APX D15 recognizes 15 canonical cells',()=>{
  const r=engine.inspect({subjectId:'synthetic-rct',evidence:[]});
  assert.deepEqual(r.cells.map(c=>c.id),catalog);
  assert.equal(r.untested_cells.length,15);
  assert.equal(r.verdict,'INCONCLUSIVE');
  assert.equal(r.compression_authorized,false);
  assert.equal(r.can_generate,false);
});

test('one actual witnessed failure dominates other recorded passes',()=>{
  const evidence=allPass.map(x=>({...x}));
  evidence[3].status='FAIL';
  const r=engine.inspect({subjectId:'synthetic-rct',evidence});
  assert.equal(r.raw_apx_gate_status,'REFUSED');
  assert.deepEqual(r.failed_cells,['DW_FRAME']);
  assert.equal(r.verdict,'REFUSE');
  assert.equal(r.qualityrag_admission,'INCONCLUSIVE');
  assert.equal(r.compression_authorized,false);
});

test('all declared PASS statuses do not authorize QualityRag semantic admission',()=>{
  const r=engine.inspect({subjectId:'synthetic-rct',evidence:allPass});
  assert.equal(r.raw_apx_gate_status,'ADMITTED');
  assert.equal(r.verdict,'INCONCLUSIVE');
  assert.equal(r.compression_authorized,false);
  assert.equal(r.semantic_completeness,'UNKNOWN');
});

test('partial census does not convert missing cells to passing',()=>{
  const r=engine.inspect({subjectId:'synthetic-rct',evidence:[allPass[0]]});
  assert.equal(r.untested_cells.length,14);
  assert.equal(r.passed_cells.length,1);
  assert.equal(r.raw_apx_gate_status,'UNTESTED');
  assert.equal(r.verdict,'INCONCLUSIVE');
});

test('unknown or forged D15 identifiers rejected',()=>{
  assert.throws(()=>engine.inspect({
    subjectId:'synthetic-rct',
    evidence:[{id:'DW_UNKNOWN',status:'PASS',evidenceRefs:['ref']}],
  }),TypeError);
});
