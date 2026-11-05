"""Opt-in real Chromium review workflow; no mock DOM or external signed-in session."""
import base64
import importlib.util
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.authority import issue_access
from tools.activation_runtime.common import canonical
from tools.activation_runtime.service import Application,server

@unittest.skipUnless(os.environ.get("QUALITYRAG_BROWSER_TESTS")=="1" and importlib.util.find_spec("playwright"),
                     "Real browser suite requires opt-in and installed Chromium")
class BrowserReviewTests(unittest.TestCase):
    def test_connect_search_preview_prune_reopen_and_mobile_layout(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp:
            key=Ed25519PrivateKey.generate()
            token=issue_access(subject="reviewer",tenant="demo",scopes=["read","write","review"],
                key=key,key_id="issuer",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
            encoded=base64.urlsafe_b64encode(canonical(token)).decode().rstrip("=")
            app=Application(temp,access_keys={"issuer":key.public_key()},release_keys={},clock=lambda:"2026-11-04T12:00:00Z")
            auth="Bearer "+encoded
            source=app.dispatch("source",{"base64":base64.b64encode(b"Original research turn").decode()},auth)["source_sha256"]
            event={"event_id":"seed","operation":"PROPOSE","branch":"hypothesis-one","source_sha256":source,
                   "source_ref":"turn:1","statement":"Review this source-linked hypothesis","parents":[]}
            app.dispatch("gardener/event",event,auth)
            http=server(app);thread=Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as runtime:
                    browser=runtime.chromium.launch(headless=True,args=["--no-sandbox"])
                    page=browser.new_page(viewport={"width":1280,"height":900})
                    errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
                    page.goto("http://127.0.0.1:"+str(http.server_port))
                    page.get_by_label("Access token").fill(encoded)
                    page.get_by_role("button",name="Open workspace").click()
                    page.get_by_role("cell",name="hypothesis-one",exact=True).wait_for()
                    page.get_by_text("Add a research branch",exact=True).click()
                    page.get_by_label("Branch name",exact=True).fill("from-browser")
                    page.get_by_label("Hypothesis or observation").fill("A source-linked browser proposal")
                    page.get_by_label("Original source",exact=True).set_input_files({"name":"source.txt","mimeType":"text/plain","buffer":b"Browser-owned source fixture"})
                    page.get_by_role("button",name="Create source-linked branch").click()
                    page.get_by_role("cell",name="from-browser",exact=True).wait_for()
                    row=page.get_by_role("row").filter(has=page.get_by_role("cell",name="hypothesis-one",exact=True))
                    row.get_by_role("button",name="Review pruning").click()
                    page.get_by_role("dialog").wait_for()
                    page.get_by_role("button",name="Apply reviewed change").click()
                    page.get_by_role("cell",name="Pruned",exact=True).wait_for()
                    row.get_by_role("button",name="Review reopening").click()
                    page.get_by_role("button",name="Apply reviewed change").click()
                    row.get_by_role("cell",name="Active",exact=True).wait_for()
                    page.get_by_role("searchbox",name="Search").fill("missing")
                    page.get_by_text("No matching branches.",exact=False).wait_for()
                    page.get_by_role("searchbox",name="Search").fill("")
                    page.get_by_text("Run a reviewed transformation",exact=True).click()
                    page.locator("#transform-availability").wait_for()
                    self.assertFalse(page.locator("#transform-form").is_visible())
                    page.set_viewport_size({"width":390,"height":844})
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),390)
                    target=os.environ.get("QUALITYRAG_BROWSER_SCREENSHOT")
                    if target:page.screenshot(path=target,full_page=True)
                    self.assertEqual(errors,[])
                    browser.close()
            finally:http.shutdown();http.server_close()


@unittest.skipUnless(os.environ.get("QUALITYRAG_BROWSER_TESTS")=="1" and importlib.util.find_spec("playwright"),
                     "Real browser suite requires opt-in and installed Chromium")
class BrowserWorkspaceTests(unittest.TestCase):
    def workspace(self):
        import test_reviewed_workflow as fixture
        factory=fixture.ReviewedWorkflowTests();factory.setUp();self.addCleanup(factory.doCleanups)
        return factory

    def connect(self,page,token,tenant="a"):
        page.get_by_label("Access token",exact=True).fill(token)
        page.get_by_role("button",name="Open workspace",exact=True).click()
        page.locator("#status").filter(has_text="Workspace: "+tenant+" ·").wait_for()

    def test_signed_transform_success_refusal_fallback_and_exact_receipt_download(self):
        from playwright.sync_api import sync_playwright
        import json
        factory=self.workspace()
        values={"instruction":"NOT permitted","unit":"mg","amount":1.0};raw=canonical(values)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True,args=["--no-sandbox"])
            try:
                page=browser.new_page();errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
                page.goto(factory.endpoint);self.connect(page,factory.client.token)
                page.get_by_text("Run a reviewed transformation",exact=True).click()
                for changes,fallback,heading in ((None,False,"Finite preservation checks passed"),({"unit":"g"},False,"Transformation refused"),({"unit":"g"},True,"Original restored after failed checks")):
                    request=factory.request(values=values,changes=changes,fallback=fallback)
                    page.get_by_label("Transformation source file",exact=True).set_input_files({"name":"source.json","mimeType":"application/json","buffer":raw})
                    page.get_by_label("Signed transformation request",exact=True).set_input_files({"name":"request.json","mimeType":"application/json","buffer":json.dumps(request).encode()})
                    page.get_by_role("button",name="Run signed transformation",exact=True).click()
                    page.get_by_role("heading",name=heading,exact=True).wait_for()
                    receipt=json.loads(page.locator("#transform-receipt").text_content())
                    self.assertFalse(receipt["can_generate"])
                    if changes and not fallback:self.assertIsNone(receipt["output"])
                    else:self.assertEqual(receipt["output"],values)
                    if changes is None:
                        with page.expect_download() as download:page.get_by_role("button",name="Download transformation receipt").click()
                        downloaded=Path(download.value.path()).read_bytes()
                        self.assertIn(b'"amount":1.0',downloaded)
                bad={**factory.request(values=values),"approve":True}
                page.get_by_label("Signed transformation request",exact=True).set_input_files({"name":"invalid.json","mimeType":"application/json","buffer":json.dumps(bad).encode()})
                page.get_by_role("button",name="Run signed transformation",exact=True).click()
                page.locator("#status").filter(has_text="INVALID_OR_UNAVAILABLE_INPUT").wait_for()
                self.assertFalse(page.locator("#transform-result").is_visible())
                self.assertEqual(page.locator("#transform-output").text_content(),"")
                self.assertEqual(errors,[])
            finally:browser.close()

    def test_observation_graph_rename_text_safety_readonly_source_and_mobile_layout(self):
        from playwright.sync_api import sync_playwright
        from test_semantic_ir import RAW,drafts
        import json
        factory=self.workspace();rows=drafts();rows[0]["value"]='<img src=x onerror="window.graphInjected=true">'
        request={"observations":rows,"rename":{row["observation_id"]:"new-"+row["observation_id"] for row in rows}}
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True,args=["--no-sandbox"])
            try:
                page=browser.new_page();page.goto(factory.endpoint);self.connect(page,factory.client.token)
                page.get_by_text("Inspect a source observation graph",exact=True).click()
                page.get_by_label("Observation source file",exact=True).set_input_files({"name":"source.txt","mimeType":"text/plain","buffer":RAW})
                page.get_by_label("Observation draft file",exact=True).set_input_files({"name":"drafts.json","mimeType":"application/json","buffer":json.dumps(request).encode()})
                page.get_by_role("button",name="Check observation graph",exact=True).click()
                page.locator("#observation-summary").filter(has_text="ID transition checked").wait_for()
                self.assertEqual(page.locator("#observation-nodes img").count(),0)
                self.assertIsNone(page.evaluate("window.graphInjected"))
                self.assertEqual(page.get_by_role("cell",name="new-bob",exact=True).count(),1)
                result=json.loads(page.locator("#observation-receipt").text_content());self.assertEqual(result["domain_validity"],"UNKNOWN")
                page.set_viewport_size({"width":390,"height":844})
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),390)
                target=os.environ.get("QUALITYRAG_OBSERVATION_SCREENSHOT")
                if target:page.screenshot(path=target,full_page=True)
                reader=base64.urlsafe_b64encode(canonical(factory.make_token("reader","a",["read"]))).decode().rstrip("=")
                self.connect(page,reader)
                self.assertFalse(page.locator("#observation-result").is_visible());self.assertTrue(page.locator("#observation-source").is_disabled())
                self.assertFalse(page.locator("#transformation-panel").is_visible())
                page.get_by_label("Or existing source SHA-256",exact=True).fill(result["source_sha256"])
                page.get_by_label("Observation draft file",exact=True).set_input_files({"name":"drafts.json","mimeType":"application/json","buffer":json.dumps(request).encode()})
                page.get_by_role("button",name="Check observation graph",exact=True).click()
                page.locator("#observation-result").wait_for()
            finally:browser.close()

    def test_delayed_old_tenant_response_is_discarded_after_token_switch(self):
        from playwright.sync_api import sync_playwright
        from test_semantic_ir import RAW,drafts
        from tools.activation_runtime.semantic_ir import evaluate
        import json
        factory=self.workspace();source=factory.client.upload(RAW)["source_sha256"]
        result=evaluate(RAW,{"observations":drafts()});held=[]
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True,args=["--no-sandbox"])
            try:
                page=browser.new_page();page.goto(factory.endpoint);self.connect(page,factory.client.token)
                page.get_by_text("Inspect a source observation graph",exact=True).click()
                page.get_by_label("Or existing source SHA-256",exact=True).fill(source)
                page.get_by_label("Observation draft file",exact=True).set_input_files({"name":"drafts.json","mimeType":"application/json","buffer":json.dumps({"observations":drafts()}).encode()})
                page.route("**/api/observations",lambda route:held.append(route))
                page.get_by_role("button",name="Check observation graph",exact=True).click()
                foreign=base64.urlsafe_b64encode(canonical(factory.make_token("bob","b"))).decode().rstrip("=")
                self.connect(page,foreign,"b")
                self.assertTrue(held)
                held[0].fulfill(status=200,content_type="application/json",body=json.dumps(result))
                page.wait_for_function("!document.querySelector('#observation-form button').disabled")
                self.assertFalse(page.locator("#observation-result").is_visible())
                self.assertEqual(page.locator("#observation-nodes").text_content(),"")
                self.assertEqual(page.locator("#observation-receipt").text_content(),"")
                self.assertEqual(page.get_by_label("Or existing source SHA-256",exact=True).input_value(),"")
                self.assertEqual(page.locator("#token").input_value(),"")
                self.assertIn("Workspace: b",page.locator("#status").text_content())
            finally:browser.close()
