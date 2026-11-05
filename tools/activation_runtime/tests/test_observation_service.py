"""Tenant-authorized source graphs have Python/TypeScript/CLI wire parity."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.error import HTTPError
import test_service_sdk as fixture
from test_semantic_ir import RAW,drafts
from tools.activation_runtime.cli import main


class ObservationServiceTests(unittest.TestCase):
    make_token=fixture.ServiceSDKTests.make_token
    setUp=fixture.ServiceSDKTests.setUp

    def request(self):return {"source_sha256":self.client.upload(RAW)["source_sha256"],"observations":drafts()}

    def test_real_http_python_typescript_and_cli_roundtrip_and_rename_parity(self):
        for rename in (None,{row["observation_id"]:"new-"+row["observation_id"] for row in drafts()}):
            request=self.request()
            if rename is not None:request["rename"]=rename
            py=self.client.observations(**request)
            sdk=Path(__file__).resolve().parents[3]/"sdk/typescript/src/activation.ts"
            script="import {ActivationClient} from "+json.dumps(sdk.as_uri())+";let text='';for await(const c of process.stdin)text+=c;let i=JSON.parse(text);console.log(JSON.stringify(await new ActivationClient(i.url,i.token).observations(i.request)));"
            child=subprocess.run(["node","--input-type=module","-e",script],input=json.dumps({"url":self.endpoint,"token":self.token,"request":request}).encode(),capture_output=True,timeout=15)
            self.assertEqual(child.returncode,0,child.stderr.decode());self.assertEqual(json.loads(child.stdout),py)
            with tempfile.TemporaryDirectory() as root:
                path=Path(root);(path/"source.txt").write_bytes(RAW)
                (path/"request.json").write_text(json.dumps({k:v for k,v in request.items() if k!="source_sha256"}));out=StringIO()
                with contextlib.redirect_stdout(out):main(["observations","--source",str(path/"source.txt"),"--request",str(path/"request.json")])
                self.assertEqual(json.loads(out.getvalue()),py)
            self.assertFalse(py["can_generate"]);self.assertEqual(py["domain_validity"],"UNKNOWN")

    def test_cross_tenant_guessed_source_and_unsupported_options_refuse(self):
        request=self.request();foreign=fixture.Client(self.endpoint,self.make_token("bob","b"))
        with self.assertRaises(HTTPError):foreign.observations(**request)
        for changed in ({**request,"tenant":"b"},{**request,"verified":True},{**request,"as_of":"2026-11-04T00:00:00Z"}):
            with self.assertRaises(HTTPError):self.client.observations(**changed)
        self.assertEqual(self.client.observations(**request)["type_status"],"WELL_TYPED")

    def test_invalid_joins_and_corrupt_original_do_not_release_ast(self):
        request=self.request();request["observations"][3]["roles"]["recipient"]="absent"
        with self.assertRaises(HTTPError):self.client.observations(**request)
        request=self.request()
        from tools.activation_runtime.authority import Principal
        store=self.app.store(Principal("alice","a",frozenset({"read"})))
        (store.root/request["source_sha256"]).write_bytes(b"corrupt")
        with self.assertRaises(HTTPError):self.client.observations(**request)
