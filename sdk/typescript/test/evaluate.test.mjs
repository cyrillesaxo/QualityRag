import test from "node:test";
import assert from "node:assert/strict";
import {evaluate} from "../dist/index.js";
const pack={id:"p",version:"1",requirements:[{id:"r",min_independent_sources:2,max_age_seconds:3600}]};
const row=(id,origin,status="SUPPORTS")=>({id,origin,status,requirement_id:"r",source_ref:"test:"+id,observed_at:"2026-11-02T10:00:00Z"});
const at="2026-11-02T10:05:00Z";
test("distinct origins admit",()=>assert.equal(evaluate(pack,[row("a","a"),row("b","b")],at).verdict,"ADMIT"));
test("same origin does not corroborate",()=>assert.equal(evaluate(pack,[row("a","a"),row("b","a")],at).verdict,"INCONCLUSIVE"));
test("contradiction refuses",()=>assert.equal(evaluate(pack,[row("a","a"),row("b","b"),row("c","c","CONTRADICTS")],at).verdict,"REFUSE"));
