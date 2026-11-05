import copy
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
import test_service_sdk as service_fixture

from tools.activation_runtime.evolution import EvolutionGarden,OllamaProposer,experiment
from tools.activation_runtime.evolution_program import encode,decode,validate


def program(rules=None,mode="ON_DEMAND",chunk=2048):
    return {"schema":"qualityrag.reversible-grammar/v1","rules":rules or [{"op":"zlib","level":6}],
            "activation":{"mode":mode,"chunk_bytes":chunk}}


class Proposer:
    def __init__(self,callback):self.callback=callback;self.contexts=[]
    def propose(self,context):
        self.contexts.append(copy.deepcopy(context))
        return {"candidates":self.callback(context),"provider":{"backend":"TEST_SCRIPTED_NOT_LIVE_AI"}}


class EvolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def config(self,cohorts=3):
        rows=[]
        for i,split in enumerate(["TRAIN","DEV"]+["EVALUATION"]*cohorts):
            path=self.root/f"source-{i}.txt"
            path.write_bytes((f"family-{i}: "+("actor nurse; must NOT disclose; quantity 1 mg; "*200)).encode())
            rows.append({"id":f"case{i}","family":f"family{i}","split":split,
                         "path":str(path),"rights_ref":"owned authored test data"})
        return {"schema":"qualityrag.evolution-config/v1","packspec":{"id":"contract","revision":"v1",
            "purpose":"exact-records","fidelity":"BYTE_EXACT","baseline":"ORIGINAL_PASSTHROUGH",
            "decoder_install_bytes":0},"sources":rows,"max_candidates":2}

    def test_three_cycles_grow_reopen_preserve_negatives_and_resume_champion(self):
        config=self.config();path=self.root/"events.sqlite"
        def propose(context):
            if not context["history"]:
                return [{"hypothesis":"Try reverse-only regime", "parents":[],"program":program([{"op":"reverse"}])},
                        {"hypothesis":"Unsupported new operation is retained as a refusal", "parents":[],"program":program([{"op":"eval"}])}]
            if len(context["history"])==1:
                dormant=next(b["id"] for b in context["branches"] if not b["active"])
                return [{"hypothesis":"Factor the repeated negation production and activate chunks lazily",
                    "parents":[dormant],"program":program([{"op":"productions","rules":[
                        {"name":"negative_obligation","literal":"must NOT disclose"}]},{"op":"zlib","level":9}])}]
            return [{"hypothesis":"Investigate eager fine-grained activation under the same contract",
                "parents":[context["champion"]["branch"]],"program":program(mode="EAGER",chunk=256)}]
        provider=Proposer(propose)
        garden=EvolutionGarden(path,config,work_limit=100)
        first=garden.cycle(provider);self.assertFalse(first["promoted_this_cycle"])
        before=garden.garden.replay();self.assertEqual(len(before["branches"]),3)
        self.assertTrue(any(o["status"]=="REFUSED" for o in first["outcomes"]))
        spent=garden.garden.db.execute("SELECT spent FROM evolution_budget").fetchone()[0];garden.close()
        garden=EvolutionGarden(path,config,work_limit=100000)
        try:
            self.assertEqual(garden.garden.db.execute("SELECT spent FROM evolution_budget").fetchone()[0],spent)
            second=garden.cycle(provider);self.assertTrue(second["promoted_this_cycle"],second)
            third=garden.cycle(provider)
            self.assertEqual(third["research_champion"],second["research_champion"])
            self.assertFalse(third["promoted_this_cycle"])
            development=garden.cycle(provider)
            self.assertEqual(development["status"],"DEVELOPMENT_ONLY")
            self.assertFalse(development["promoted_this_cycle"])
            self.assertEqual(development["fresh_evaluation_families"],[])
            self.assertEqual(len(provider.contexts),4)
            state=garden.garden.replay()
            self.assertEqual(len(state["branches"]),6)
            self.assertTrue(any(e["operation"]=="REOPEN" for e in state["events"].values()))
            reopened=state["branches"]["evo-1-candidate-0"]["reopened_context"]
            self.assertTrue(reopened["prior_challenges"])
            self.assertTrue(all(b["evidence_status"]=="UNVERIFIED" for b in state["branches"].values()))
            self.assertEqual(len({family for r in (first,second,third) for family in r["fresh_evaluation_families"]}),3)
            self.assertFalse(second["can_release"]);self.assertFalse(second["can_generate"])
            self.assertIn("diagnostics",provider.contexts[1]["history"][0]["development_findings"][0])
            for context in provider.contexts:
                text=json.dumps(context)
                self.assertNotIn("case2",text);self.assertNotIn("family-2:",text)
                self.assertNotIn(str(self.root),text)
            with self.assertRaises(sqlite3.IntegrityError):
                garden.garden.db.execute("UPDATE evolution_cycles SET body='{}' WHERE id=1")
            garden.garden.db.rollback()
        finally:garden.close()

    def test_unknown_install_cost_forces_untouched_baseline(self):
        raw=b"must NOT disclose;"*300
        receipt,payload=experiment(raw,program(),decoder_install_bytes=None)
        self.assertTrue(receipt["fallback"])
        self.assertEqual(payload,raw)
        self.assertEqual(receipt["selected_bytes"],len(raw))
        receipt,payload=experiment(raw,program(),decoder_install_bytes=len(raw))
        self.assertTrue(receipt["fallback"]);self.assertEqual(payload,raw)

    def test_budget_survives_restart_and_prevents_provider_call(self):
        config=self.config(1);path=self.root/"budget.sqlite";provider=Proposer(lambda c:[])
        garden=EvolutionGarden(path,config,work_limit=1)
        self.assertEqual(garden.cycle(provider)["status"],"PAUSED_BUDGET_EXHAUSTED");garden.close()
        garden=EvolutionGarden(path,config,work_limit=10000)
        try:self.assertEqual(garden.cycle(provider)["status"],"PAUSED_BUDGET_EXHAUSTED")
        finally:garden.close()
        self.assertEqual(provider.contexts,[])

    def test_provider_failure_needs_charged_retry_without_new_cohort(self):
        config=self.config(2);garden=EvolutionGarden(self.root/"retry.sqlite",config)
        failing=Proposer(lambda c: (_ for _ in ()).throw(ConnectionError()))
        try:
            self.assertEqual(garden.cycle(failing)["status"],"PROVIDER_FAILED_REQUIRES_EXPLICIT_RETRY")
            self.assertEqual(garden.cycle(failing)["status"],"PROVIDER_FAILED_REQUIRES_EXPLICIT_RETRY")
            self.assertEqual(len(failing.contexts),1)
            spent=garden.garden.db.execute("SELECT spent FROM evolution_budget").fetchone()[0]
            garden.retry_provider()
            result=garden.cycle(Proposer(lambda c:[{"hypothesis":"Reconstruct exact data","parents":[],"program":program()}]))
            self.assertEqual(result["cycle"],1)
            self.assertEqual(garden.garden.db.execute("SELECT spent FROM evolution_budget").fetchone()[0],spent+1)
        finally:garden.close()

    def test_content_and_family_leakage_refused_across_restarts(self):
        config=self.config(1);changed=copy.deepcopy(config)
        changed["sources"][2]["path"]=changed["sources"][0]["path"]
        with self.assertRaises(ValueError):EvolutionGarden(self.root/"bad.sqlite",changed)
        path=self.root/"history.sqlite";garden=EvolutionGarden(path,config);garden.close()
        renamed=copy.deepcopy(config);renamed["sources"][2]["family"]="renamed"
        with self.assertRaises(ValueError):EvolutionGarden(path,renamed)

    def test_source_bound_productions_and_sandbox_refusal_become_branches(self):
        config=self.config(1);garden=EvolutionGarden(self.root/"refusal.sqlite",config)
        p=program([{"op":"productions","rules":[{"name":"invented","literal":"HELDOUT SECRET"}]}])
        try:
            result=garden.cycle(Proposer(lambda c:[{"hypothesis":"Unsupported production", "parents":[],"program":p}]))
            self.assertEqual(result["outcomes"][0]["status"],"REFUSED")
            self.assertIn("training source anchor",result["outcomes"][0]["failure_reason"])
            self.assertFalse(result["promoted_this_cycle"])
        finally:garden.close()

    def test_registered_snapshot_cannot_be_changed_by_mutating_input_files(self):
        config=self.config(1);garden=EvolutionGarden(self.root/"snapshot.sqlite",config)
        original=Path(config["sources"][0]["path"]).read_bytes()
        private=Path(config["sources"][2]["path"]).read_bytes()
        Path(config["sources"][0]["path"]).write_bytes(private)
        provider=Proposer(lambda c:[{"hypothesis":"Use frozen training custody","parents":[],"program":program()}])
        try:
            garden.cycle(provider)
            import base64
            preview=base64.b64decode(provider.contexts[0]["training_samples"][0]["sample_base64"])
            self.assertEqual(preview,original[:2048])
            self.assertNotIn(b"family-2:",preview)
        finally:garden.close()

    def test_ollama_adapter_calls_real_http_json_protocol(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                body=json.dumps({"model":"host-installed-open-model","done":True,"message":{"content":json.dumps({"candidates":[{"hypothesis":"Compose","parents":[],"program":program()}]})},"eval_count":12}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        http=HTTPServer(("127.0.0.1",0),Handler);thread=Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            result=OllamaProposer("host-installed-open-model",f"http://127.0.0.1:{http.server_port}/api/chat").propose({"history":[]})
            self.assertEqual(result["provider"]["reported_output_tokens"],12)
            self.assertFalse(captured[0]["stream"]);self.assertEqual(captured[0]["format"],"json")
            self.assertEqual(captured[0]["options"]["num_predict"],2048)
            self.assertIn("productions",captured[0]["messages"][0]["content"])
        finally:http.shutdown();http.server_close();thread.join()

    def test_interrupted_experiment_is_not_replayed_as_unspent_work(self):
        config=self.config(1);path=self.root/"interrupted.sqlite";garden=EvolutionGarden(path,config)
        provider=Proposer(lambda c:[{"hypothesis":"Try a regime","parents":[],"program":program()}])
        original=garden._save
        def interrupt(cycle,stage,body):
            original(cycle,stage,body)
            if body.get("attempting")==0:raise KeyboardInterrupt()
        with patch.object(garden,"_save",side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):garden.cycle(provider)
        garden.close();garden=EvolutionGarden(path,config)
        try:
            with patch("tools.activation_runtime.evolution.experiment",side_effect=AssertionError("must not execute twice")):
                result=garden.cycle(provider)
            self.assertEqual(len(provider.contexts),1)
            self.assertIn("Interrupted experiment",result["outcomes"][0]["failure_reason"])
            self.assertFalse(result["promoted_this_cycle"])
        finally:garden.close()

    def test_completed_receipt_recovers_after_crash_before_tree_test_event(self):
        config=self.config(1);path=self.root/"receipt.sqlite";garden=EvolutionGarden(path,config)
        provider=Proposer(lambda c:[{"hypothesis":"Measured regime","parents":[],"program":program()}])
        original=garden._event
        def interrupt(*args,**kwargs):
            if args[2]=="TEST":raise KeyboardInterrupt()
            return original(*args,**kwargs)
        with patch.object(garden,"_event",side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):garden.cycle(provider)
        garden.close();garden=EvolutionGarden(path,config)
        try:
            with patch("tools.activation_runtime.evolution.experiment",side_effect=AssertionError("receipt must be recovered")):
                result=garden.cycle(provider)
            self.assertTrue(result["promoted_this_cycle"])
            self.assertEqual(len(provider.contexts),1)
            self.assertEqual(sum(e["operation"]=="TEST" for e in garden.garden.replay()["events"].values()),1)
        finally:garden.close()

    def test_two_parent_synthesis_retains_lineage_without_domain_validation(self):
        config=self.config(2);garden=EvolutionGarden(self.root/"synthesis.sqlite",config)
        def propose(context):
            if not context["history"]:
                return [{"hypothesis":"zlib branch","parents":[],"program":program()},
                        {"hypothesis":"bz2 branch","parents":[],"program":program([{"op":"bz2","level":3}])}]
            parents=[b["id"] for b in context["branches"] if b["id"].startswith("evo-1-candidate")]
            return [{"hypothesis":"Borrow structure from both investigations","parents":parents,
                     "program":program([{"op":"delta","stride":2},{"op":"zlib","level":9}])}]
        try:
            provider=Proposer(propose);garden.cycle(provider);garden.cycle(provider)
            state=garden.garden.replay();joined=state["branches"]["evo-2-candidate-0"]
            self.assertEqual(len(joined["parents"]),2)
            self.assertEqual(joined["evidence_status"],"UNVERIFIED")
            self.assertTrue(any(e["operation"]=="SYNTHESIZE" for e in state["events"].values()))
        finally:garden.close()


class GrammarProgramTests(unittest.TestCase):
    def test_production_grammar_and_activation_evolve_together_with_exact_roundtrip(self):
        raw=b"must NOT disclose;"*200+b"TAIL"*200
        rules=[{"op":"productions","rules":[{"name":"negation","literal":"must NOT disclose;"}]},
               {"op":"delta","stride":3},{"op":"reverse"},{"op":"xor","value":17},{"op":"bz2","level":3}]
        lazy=program(rules,chunk=1024);packet,_=encode(raw,lazy)
        output,trace=decode(packet);self.assertEqual(output,raw)
        self.assertIn("negation",trace["productions_materialized"])
        first,trace=decode(packet,indices=[0]);self.assertEqual(first,raw[:1024]);self.assertEqual(trace["activated_chunks"],[0])
        eager=copy.deepcopy(lazy);eager["activation"]["mode"]="EAGER";packet,_=encode(raw,eager)
        first,trace=decode(packet,indices=[0]);self.assertEqual(first,raw[:1024]);self.assertGreater(len(trace["activated_chunks"]),1)

    def test_byte_floor_includes_metadata_and_rejects_tampering(self):
        raw=random.Random(12).randbytes(5000)
        receipt,selected=experiment(raw,program(),decoder_install_bytes=0)
        self.assertTrue(receipt["fallback"]);self.assertEqual(selected,raw)
        self.assertGreater(receipt["candidate_bytes"],len(raw))
        packet,_=encode(raw,program([{"op":"reverse"}]))
        changed=packet[:-1]+bytes([packet[-1]^1])
        with self.assertRaises(ValueError):decode(changed)
        with self.assertRaises(ValueError):validate(program([{"op":"eval","code":"anything"}]))

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg unavailable")
    def test_real_av1_payload_is_untouched_on_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"baseline.mkv"
            subprocess.run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","testsrc2=size=32x32:rate=4",
                "-t","0.5","-c:v","libaom-av1","-crf","0","-cpu-used","8",str(path)],check=True,capture_output=True,timeout=30)
            raw=path.read_bytes();receipt,selected=experiment(raw,program(),decoder_install_bytes=None)
            self.assertTrue(receipt["fallback"]);self.assertEqual(sha256(selected).hexdigest(),sha256(raw).hexdigest())
            self.assertEqual(receipt["selected_bytes"],len(raw))


class EvolutionServiceTests(unittest.TestCase):
    setUp=service_fixture.ServiceSDKTests.setUp
    make_token=service_fixture.ServiceSDKTests.make_token

    def test_existing_service_observes_growth_without_exposing_evaluation_sources(self):
        from tools.activation_runtime.authority import Principal
        from urllib.error import HTTPError
        from qualityrag_activation import Client
        self.assertEqual(self.client.request("gardener/evolution",{})["status"],"NOT_STARTED")
        helper=EvolutionTests();helper.root=Path(self.temp.name)/"inputs";helper.root.mkdir()
        config=helper.config(1)
        principal=Principal("alice","a",frozenset({"read","write"}))
        garden=EvolutionGarden(self.app.garden_path(principal),config,public_contract_store=self.app.store(principal))
        try:
            result=garden.cycle(Proposer(lambda c:[{"hypothesis":"Grow a measured research branch","parents":[],"program":program()}]))
            state=self.client.request("gardener/evolution",{})
            self.assertEqual(state,self.client.garden_evolution())
            self.assertEqual(state["cycles"][0]["stage"],"DONE")
            self.assertEqual(state["champions"][0]["branch"],result["research_champion"])
            self.assertEqual(state["worker_running"],"NOT_INFERRED_FROM_HISTORY")
            self.assertFalse(state["can_release"])
            sdk=Path(__file__).resolve().parents[3]/"sdk/typescript/src/activation.ts"
            script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let raw='';for await(const c of process.stdin)raw+=c;let i=JSON.parse(raw);console.log(JSON.stringify(await new ActivationClient(i.endpoint,i.token).gardenEvolution()));"
            result_ts=subprocess.run(["node","--input-type=module","-e",script],input=json.dumps({"endpoint":self.endpoint,"token":self.token}).encode(),capture_output=True,timeout=10)
            self.assertEqual(result_ts.returncode,0,result_ts.stderr.decode())
            self.assertEqual(json.loads(result_ts.stdout),state)
            self.assertIn("evo-1-candidate-0",self.client.garden_state()["branches"])
            private_sha=sha256(Path(config["sources"][2]["path"]).read_bytes()).hexdigest()
            with self.assertRaises(HTTPError):self.client.fallback(private_sha)
            other=Client(self.endpoint,self.make_token("bob","b"))
            self.assertEqual(other.request("gardener/evolution",{})["status"],"NOT_STARTED")
            with self.assertRaises(HTTPError):self.client.request("gardener/evolution",{"start":True})
        finally:garden.close()
