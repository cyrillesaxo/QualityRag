import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {evaluate} from "../dist/index.js";
const fixture=JSON.parse(readFileSync("../../examples/apx-packspecs/fixtures.json","utf8"));
test("APX-derived examples: four domains x three decisions",()=>{
 let count=0;
 for(const domain of fixture.scenarios)for(const example of domain.cases){
  const result=evaluate(domain.pack,example.evidence,fixture.as_of);
  assert.equal(result.verdict,example.expected,domain.id+"/"+example.id);
  count++;
 }
 assert.equal(count,12);
});
