"""Complete signed workflow over real HTTP through Python, TypeScript and CLI."""
import base64
import contextlib
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.error import HTTPError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import Principal,review_binding
from tools.activation_runtime.common import canonical,fingerprint
from tools.activation_runtime.artifacts import make_manifest,sign_manifest
from tools.activation_runtime.preservation import make_contract
from tools.activation_runtime.pipeline import encode
from tools.activation_runtime.service import Application
import test_service_sdk as service_fixture
Client=service_fixture.Client
AT=service_fixture.AT
from test_runtime import policy


class ReviewedWorkflowTests(unittest.TestCase):
    make_token=service_fixture.ServiceSDKTests.make_token
    def setUp(self):
        service_fixture.ServiceSDKTests.setUp(self)
        self.author=Ed25519PrivateKey.generate();self.reviewer=Ed25519PrivateKey.generate();self.serial=0
        self.app.preservation_authorities={"a":{"authors":{"author":self.author.public_key()},
            "review":{"review-key":self.reviewer.public_key()},"subjects":{"review-key":"reviewer"}}}

    def request(self,values=None,changes=None,fallback=False):
        values=values or {"instruction":"NOT permitted","unit":"mg"};raw=canonical(values)
        source=self.client.upload(raw)["source_sha256"]
        artifact=encode(raw,{field:"f"+str(i) for i,field in enumerate(values)})
        for field,value in (changes or {}).items():artifact["payload"][artifact["mapping"][field]]=value
        artifact_hash=self.client.upload(canonical(artifact))["source_sha256"];ir=policy()
        manifest=make_manifest(tenant="a",source_sha256=source,artifact_sha256=artifact_hash,policy_ir_sha256=ir["ir_sha256"],sequence=1)
        signed=sign_manifest(manifest,self.release,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
        contract=make_contract(raw,task="external-input",author="author",reviewer="reviewer",tenant="a",ir=ir,
            obligations=[{"field":field,"ir_node_id":"custody","mode":"UNKNOWN" if value is None else "EXACT",
                          "tolerance":None,"omission_permitted":False} for field,value in values.items()])
        context={"purpose":"PRESERVATION_CONTRACT_REVIEW","source_sha256":source,"policy_ir_sha256":ir["ir_sha256"],
                 "policy_source_sha256":ir["source"]["sha256"],"contract_sha256":fingerprint(contract)}
        self.serial+=1
        review=review_binding(context,decision="APPROVE",reviewer="reviewer",author_key_id="author",key=self.reviewer,
            key_id="review-key",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce="workflow-"+str(self.serial))
        return {"source_sha256":source,"artifact":artifact,"signed_manifest":signed,"policy_ir":ir,"contract":contract,
                "signed_review":review,"allow_fallback":fallback}

    def test_complete_positive_workflow_has_signed_review_and_actual_trace(self):
        result=self.client.activate_plan(**self.request())
        self.assertEqual(result["action"],"REQUIRES_REVIEW");self.assertEqual(result["finite_constraint_result"],"SAT")
        self.assertEqual(result["output"],{"instruction":"NOT permitted","unit":"mg"})
        self.assertEqual([r["operator"] for r in result["execution"]["trace"]],["PRESERVE","TRANSITION","ACTIVATE","VERIFY"])
        self.assertEqual(result["preservation_review"]["review"]["reviewer"],"reviewer")
        self.assertFalse(result["can_generate"]);self.assertEqual(result["qualityrag_admission"],"INCONCLUSIVE")

    def test_negative_candidate_refuses_without_releasing_output(self):
        result=self.client.activate_plan(**self.request(changes={"instruction":"permitted"}))
        self.assertEqual(result["action"],"REFUSE");self.assertIsNone(result["output"])
        self.assertIsNone(result["execution"]["output"])
        self.assertEqual(result["candidate_audit"]["finite_constraint_result"],"UNSAT")

    def test_signed_original_fallback_is_reverified_and_only_attempted_once(self):
        result=self.client.activate_plan(**self.request(changes={"unit":"g"},fallback=True))
        self.assertEqual(result["action"],"FALLBACK");self.assertEqual(result["output"]["unit"],"mg")
        self.assertEqual(result["finite_constraint_result"],"SAT")
        self.assertEqual(result["candidate_audit"]["finite_constraint_result"],"UNSAT")
        self.assertEqual([r["operator"] for r in result["execution"]["trace"]].count("FALLBACK"),1)
        positive=self.client.activate_plan(**self.request(fallback=True))
        self.assertFalse(positive["execution"]["fallback_used"])

    def test_clinical_nursing_legal_and_education_complete_paths(self):
        cases=[({"symptom":"Chest discomfort while running","diagnosis":None},{"diagnosis":"asthma"}),
               ({"instruction":"Select every action EXCEPT B","unit":"mg"},{"instruction":"Select every action"}),
               ({"actor":"supplier","recipient":"buyer","obligation":"must NOT disclose"},{"actor":"buyer","recipient":"supplier"}),
               ({"question":"Choose all EXCEPT B","exception":"B"},{"exception":"A"})]
        for values,changes in cases:
            with self.subTest(values=values):
                self.assertEqual(self.client.activate_plan(**self.request(values))["output"],values)
                self.assertIsNone(self.client.activate_plan(**self.request(values,changes))["output"])
                self.assertEqual(self.client.activate_plan(**self.request(values,changes,True))["output"],values)

    def test_python_typescript_and_cli_match_on_all_three_outcomes(self):
        sdk=Path(__file__).resolve().parents[3]/"sdk/typescript/src/activation.ts"
        script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let text='';for await(const c of process.stdin)text+=c;let i=JSON.parse(text);console.log(JSON.stringify(await new ActivationClient(i.url,i.token).activatePlan(i.request)));"
        from tools.activation_runtime.cli import main
        for changes,fallback in ((None,False),({"unit":"g"},False),({"unit":"g"},True)):
            py=self.client.activate_plan(**self.request(changes=changes,fallback=fallback))
            request=self.request(changes=changes,fallback=fallback)
            child=subprocess.run(["node","--input-type=module","-e",script],input=json.dumps({"url":self.endpoint,"token":self.token,"request":request}).encode(),capture_output=True,timeout=15)
            self.assertEqual(child.returncode,0,child.stderr.decode());self.assertEqual(json.loads(child.stdout),py)
            with tempfile.TemporaryDirectory() as root:
                path=Path(root);(path/"request.json").write_text(json.dumps(self.request(changes=changes,fallback=fallback)))
                (path/"token.json").write_text(json.dumps(self.token));out=StringIO()
                with contextlib.redirect_stdout(out):main(["activate-plan","--endpoint",self.endpoint,"--token",str(path/"token.json"),"--request",str(path/"request.json")])
                self.assertEqual(json.loads(out.getvalue()),py)

    def test_missing_tenant_authorities_or_author_identity_refuses(self):
        request=self.request();authorities=self.app.preservation_authorities
        for changed in ({},{"a":{}}):
            self.app.preservation_authorities=changed
            with self.assertRaises(HTTPError):self.client.activate_plan(**request)
        self.app.preservation_authorities=authorities
        self.assertEqual(self.client.activate_plan(**request)["finite_constraint_result"],"SAT")

    def test_cross_tenant_requests_and_contract_transplant_refuse(self):
        request=self.request();foreign=Client(self.endpoint,self.make_token("bob","b"))
        with self.assertRaises(HTTPError):foreign.activate_plan(**request)
        changed=deepcopy(request);changed["contract"]["tenant"]="b"
        with self.assertRaises(HTTPError):self.client.activate_plan(**changed)
        self.assertEqual(self.client.activate_plan(**request)["finite_constraint_result"],"SAT")

    def test_review_replay_after_application_restart_refuses(self):
        request=self.request();self.client.activate_plan(**request)
        app=Application(self.temp.name,access_keys=self.app.access_keys,release_keys=self.app.release_keys,clock=lambda:AT,
                        preservation_authorities=self.app.preservation_authorities)
        authorization="Bearer "+self.client.token
        with self.assertRaises(PermissionError):app.dispatch("activate-plan",request,authorization)

    def test_source_artifact_and_policy_tampering_preserve_review_for_valid_request(self):
        request=self.request()
        for mutate in (lambda d:d["artifact"]["payload"].update(f0="changed"),
                       lambda d:d["contract"]["obligations"][0]["anchor"].update(value_sha256="0"*64),
                       lambda d:d["policy_ir"]["nodes"][0]["parameters"].update(min_independent_sources=2),
                       lambda d:d.update(source_sha256="0"*64)):
            changed=deepcopy(request);mutate(changed)
            with self.assertRaises(HTTPError):self.client.activate_plan(**changed)
        self.assertEqual(self.client.activate_plan(**request)["finite_constraint_result"],"SAT")

    def test_revoked_release_or_review_key_cannot_authorize_fallback(self):
        request=self.request(changes={"unit":"g"},fallback=True)
        original=self.app.release_keys;self.app.release_keys={}
        with self.assertRaises(HTTPError):self.client.activate_plan(**request)
        self.app.release_keys=original;keys=self.app.preservation_authorities["a"]["review"]
        self.app.preservation_authorities["a"]["review"]={}
        with self.assertRaises(HTTPError):self.client.activate_plan(**request)
        self.app.preservation_authorities["a"]["review"]=keys
        self.assertEqual(self.client.activate_plan(**request)["action"],"FALLBACK")

    def test_unsupported_options_and_invalid_fallback_policy_refuse(self):
        request=self.request()
        for changed in ({**request,"tenant":"b"},{**request,"allow_fallback":"yes"},{**request,"max_steps":1000}):
            with self.assertRaises(HTTPError):self.client.activate_plan(**changed)
        self.assertEqual(self.client.activate_plan(**request)["finite_constraint_result"],"SAT")

    def test_missing_original_or_artifact_custody_cannot_fallback(self):
        request=self.request(changes={"unit":"g"},fallback=True)
        store=self.app.store(Principal("alice","a",frozenset({"read"})))
        for address in (request["source_sha256"],fingerprint(request["artifact"])):
            path=store.root/address;raw=path.read_bytes();path.unlink()
            with self.assertRaises(HTTPError):self.client.activate_plan(**request)
            store.put(raw)
        self.assertEqual(self.client.activate_plan(**request)["action"],"FALLBACK")

    def test_host_reviewer_subject_mismatch_refuses_before_consuming_review(self):
        request=self.request();subjects=self.app.preservation_authorities["a"]["subjects"]
        self.app.preservation_authorities["a"]["subjects"]={"review-key":"different-subject"}
        with self.assertRaises(HTTPError):self.client.activate_plan(**request)
        self.app.preservation_authorities["a"]["subjects"]=subjects
        self.assertEqual(self.client.activate_plan(**request)["finite_constraint_result"],"SAT")

    def test_approximation_cannot_bypass_the_canonical_exact_runtime(self):
        request=self.request(values={"amount":0.3},changes={"amount":0.4})
        request["contract"]["obligations"][0].update(mode="APPROXIMATE",tolerance=0.1)
        context={"purpose":"PRESERVATION_CONTRACT_REVIEW","source_sha256":request["source_sha256"],
            "policy_ir_sha256":request["policy_ir"]["ir_sha256"],"policy_source_sha256":request["policy_ir"]["source"]["sha256"],
            "contract_sha256":fingerprint(request["contract"])}
        request["signed_review"]=review_binding(context,decision="APPROVE",reviewer="reviewer",author_key_id="author",key=self.reviewer,
            key_id="review-key",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z",nonce="approximation-workflow")
        with self.assertRaises(HTTPError):self.client.activate_plan(**request)

    def test_staged_run_works_from_empty_custody_without_preparatory_upload_calls(self):
        request=self.request();self.app.root=Path(self.temp.name)/"fresh-runtime"
        raw=b'{"instruction":"NOT permitted","unit":"mg"}'
        result=self.client.run_reviewed(raw,request)
        self.assertEqual(result["finite_constraint_result"],"SAT")
        store=self.app.store(Principal("alice","a",frozenset({"read"})))
        self.assertEqual(store.get(request["source_sha256"]),raw)
        self.assertEqual(store.get(fingerprint(request["artifact"])),canonical(request["artifact"]))

    def test_staged_run_requires_both_read_and_write_and_preserves_review_on_failure(self):
        request=self.request();raw=b'{"instruction":"NOT permitted","unit":"mg"}'
        for scopes in (["read"],["write"]):
            restricted=Client(self.endpoint,self.make_token("restricted","a",scopes))
            with self.assertRaises(HTTPError):restricted.run_reviewed(raw,request)
        with self.assertRaises(HTTPError):self.client.run_reviewed(b"wrong original",request)
        self.assertEqual(self.client.run_reviewed(raw,request)["finite_constraint_result"],"SAT")

    def test_staged_python_typescript_cli_parity_for_preserved_refused_and_fallback(self):
        raw=b'{"instruction":"NOT permitted","unit":"mg"}'
        sdk=Path(__file__).resolve().parents[3]/"sdk/typescript/src/activation.ts"
        script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let text='';for await(const c of process.stdin)text+=c;let i=JSON.parse(text);console.log(JSON.stringify(await new ActivationClient(i.url,i.token).runReviewed(new TextEncoder().encode(i.raw),i.request)));"
        from tools.activation_runtime.cli import main
        for changes,fallback in ((None,False),({"unit":"g"},False),({"unit":"g"},True)):
            py=self.client.run_reviewed(raw,self.request(changes=changes,fallback=fallback))
            child=subprocess.run(["node","--input-type=module","-e",script],input=json.dumps({"url":self.endpoint,"token":self.token,"raw":raw.decode(),"request":self.request(changes=changes,fallback=fallback)}).encode(),capture_output=True,timeout=15)
            self.assertEqual(child.returncode,0,child.stderr.decode());self.assertEqual(json.loads(child.stdout),py)
            with tempfile.TemporaryDirectory() as root:
                path=Path(root);(path/"source.json").write_bytes(raw);(path/"request.json").write_text(json.dumps(self.request(changes=changes,fallback=fallback)));(path/"token.json").write_text(json.dumps(self.token));out=StringIO()
                with contextlib.redirect_stdout(out):main(["activate-plan","--endpoint",self.endpoint,"--token",str(path/"token.json"),"--request",str(path/"request.json"),"--source",str(path/"source.json")])
                self.assertEqual(json.loads(out.getvalue()),py)

    def test_staging_cannot_bypass_release_checks_or_silently_accept_extra_options(self):
        request=self.request();raw=b'{"instruction":"NOT permitted","unit":"mg"}'
        changed=deepcopy(request);changed["artifact"]["payload"]["f0"]="altered"
        with self.assertRaises(HTTPError):self.client.run_reviewed(raw,changed)
        with self.assertRaises(HTTPError):self.client.request("reviewed-run",{"base64":base64.b64encode(raw).decode(),"request":request,"approve":True})
        self.assertEqual(self.client.run_reviewed(raw,request)["finite_constraint_result"],"SAT")
