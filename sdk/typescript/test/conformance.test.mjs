import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {evaluate} from "../dist/index.js";
const fixture=JSON.parse(fs.readFileSync(new URL("../../../conformance/v0.1.json",import.meta.url),"utf8"));
for(const c of fixture.cases){
 test("conformance: "+c.name,()=>{
  const evidence=c.evidence.map(([id,origin,status,observed_at="2026-11-02T10:00:00Z"])=>({id,origin,status,observed_at,requirement_id:"r",source_ref:"doc:"+id}));
  const out=evaluate(fixture.pack,evidence,fixture.as_of);
  assert.equal(out.verdict,c.verdict);
  assert.deepEqual(out.findings[0].reasons,c.reasons);
 });
}
