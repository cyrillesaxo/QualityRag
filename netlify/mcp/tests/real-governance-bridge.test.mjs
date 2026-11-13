/**
 * Actual MCP -> Python governance API regression (local, controlled transport).
 * This does NOT prove public HTTPS/OAuth provider interoperability.
 *
 * Netlify adapter accepts only HTTPS external origins in production. This
 * test deliberately rewrites one fixed synthetic external origin to the
 * Python test service at loopback, with a real Ed25519 access token.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import handler from "../netlify/functions/mcp.mjs";

const originalFetch=globalThis.fetch;
const originalEnv={...process.env};

function launch() {
  return new Promise((resolve,reject)=>{
    const child=spawn("python",["netlify/mcp/tests/real-governance-fixture.py"],{
      cwd:process.cwd(),
      env:{...process.env,PYTHONUNBUFFERED:"1",PYTHONPATH:process.cwd()},
      stdio:["ignore","pipe","pipe"],
    });
    let stdout="",stderr="",finished=false;
    const timeout=setTimeout(()=>finish(new Error("Python fixture timed out")),20000);
    function finish(error,data){
      if(finished)return;
      finished=true;clearTimeout(timeout);
      if(error){child.kill();reject(error)}
      else resolve({child,...data});
    }
    child.stdout.on("data",piece=>{
      stdout+=piece.toString();
      const end=stdout.indexOf("\n");
      if(end<0)return;
      try{finish(null,{ready:JSON.parse(stdout.slice(0,end))})}
      catch{finish(new Error("Python fixture returned invalid startup JSON"))}
    });
    child.stderr.on("data",piece=>{stderr=(stderr+piece.toString()).slice(-1600)});
    child.on("error",error=>finish(error));
    child.on("exit",code=>finish(new Error("Python service exited during startup; status "+code+
      "; captured stderr length "+stderr.length)));
  });
}

function mcp(id,name,args){
  return new Request("https://qualityrag-mcp.netlify.app/mcp",{
    method:"POST",
    headers:{"authorization":"Bearer local-bridge-test",
      "content-type":"application/json"},
    body:JSON.stringify({jsonrpc:"2.0",id,method:"tools/call",
      params:{name,arguments:args}}),
  });
}

test("real signed Python governance API produces both admissible and inconclusive PackSpec results",async()=>{
  const {child,ready}=await launch();
  try{
    process.env.QUALITYRAG_MCP_ACCESS_TOKEN="local-bridge-test";
  // main enforces a current, at most 60-day client bearer window (security(mcp) 60-day expiry).
  process.env.QUALITYRAG_MCP_TOKEN_ISSUED_AT=new Date(Date.now()-1000).toISOString().replace(/\.\d{3}Z$/,"Z");
  process.env.QUALITYRAG_MCP_TOKEN_EXPIRES_AT=new Date(Date.now()+30*24*60*60*1000).toISOString().replace(/\.\d{3}Z$/,"Z");
    process.env.QUALITYRAG_API_ENDPOINT="https://fixture-governance.example";
    process.env.QUALITYRAG_API_TOKEN_JSON=JSON.stringify(ready.token);

    const origin="http://127.0.0.1:"+ready.port;
    globalThis.fetch=(input,options)=>{
      const destination=new URL(input);
      assert.equal(destination.origin,"https://fixture-governance.example");
      assert.match(destination.pathname,/^\/api\/(policy\/test|gardener\/query)$/);
      assert.equal(options.redirect,"error");
      return originalFetch(new URL(destination.pathname,origin),{
        ...options,redirect:"manual",
      });
    };
    const fixture=ready.fixture;
    const body={
      pack:fixture.pack,documents:fixture.documents,
      retrieved:fixture.retrieved,
      as_of:fixture.as_of,
    };
    const call=async(id,name,args)=>{
      const response=await handler(mcp(id,name,args));
      assert.equal(response.status,200);
      const envelope=await response.json();
      assert.equal(envelope.result.isError,undefined,JSON.stringify(envelope));
      return JSON.parse(envelope.result.content[0].text);
    };

    const accepted=await call(1,"policy_test",body);
    assert.equal(accepted.verdict,"ADMIT");

    const incomplete=await call(2,"policy_test",{
      ...body,retrieved:["ops-7.3","incident-summary","runbook-restart","ops-mirror-7.3"],
    });
    assert.equal(incomplete.verdict,"INCONCLUSIVE");
    assert.notDeepEqual(accepted,incomplete);

    const garden=await call(3,"garden_query",{text:"test",limit:3});
    assert.equal(Array.isArray(garden.branches),true);

    console.log(JSON.stringify({
      result:"REAL_PYTHON_MCP_BRIDGE_PASSED",
      full_evidence_verdict:accepted.verdict,
      incomplete_evidence_verdict:incomplete.verdict,
      garden_query:"PASSED",
      external_oauth:"NOT_TESTED",
      public_deployment:"NOT_TESTED",
    }));
  }finally{
    child.kill();
    globalThis.fetch=originalFetch;
    process.env=originalEnv;
  }
});
