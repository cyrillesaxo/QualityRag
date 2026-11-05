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

def view(page,name):
    """Open a console screen from the sidebar (on a phone, through the menu)."""
    if page.locator("#menu-toggle").is_visible():page.locator("#menu-toggle").click()
    page.locator('[data-nav="'+name+'"]').click()
    page.locator('[data-view="'+name+'"]').wait_for()

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
                    page.locator("#home-title").filter(has_text="Workspace demo").wait_for()
                    view(page,"review")
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
                    view(page,"advanced")
                    view(page,"advanced");page.get_by_text("Run a reviewed transformation",exact=True).click()
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
        if page.locator("#switch-ws").is_visible():page.get_by_role("button",name="Switch workspace").click()
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
                view(page,"advanced");page.get_by_text("Run a reviewed transformation",exact=True).click()
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
                view(page,"advanced");page.get_by_text("Inspect a source observation graph",exact=True).click()
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
                view(page,"advanced");page.get_by_text("Inspect a source observation graph",exact=True).click()
                page.get_by_label("Or existing source SHA-256",exact=True).fill(source)
                page.get_by_label("Observation draft file",exact=True).set_input_files({"name":"drafts.json","mimeType":"application/json","buffer":json.dumps({"observations":drafts()}).encode()})
                page.route("**/api/observations",lambda route:held.append(route))
                page.get_by_role("button",name="Check observation graph",exact=True).click()
                foreign=base64.urlsafe_b64encode(canonical(factory.make_token("bob","b"))).decode().rstrip("=")
                self.connect(page,foreign,"b")
                self.assertTrue(held)
                held[0].fulfill(status=200,content_type="application/json",body=json.dumps(result))
                # Locator assertion, not wait_for_function: the console's CSP forbids eval in the page.
                from playwright.sync_api import expect
                expect(page.locator("#observation-form button")).to_be_enabled()
                self.assertFalse(page.locator("#observation-result").is_visible())
                self.assertEqual(page.locator("#observation-nodes").text_content(),"")
                self.assertEqual(page.locator("#observation-receipt").text_content(),"")
                self.assertEqual(page.get_by_label("Or existing source SHA-256",exact=True).input_value(),"")
                self.assertEqual(page.locator("#token").input_value(),"")
                self.assertIn("Workspace: b",page.locator("#status").text_content())
            finally:browser.close()


@unittest.skipUnless(os.environ.get("QUALITYRAG_BROWSER_TESTS")=="1" and importlib.util.find_spec("playwright"),
                     "Real browser suite requires opt-in and installed Chromium")
class GardenTreeBrowserTests(unittest.TestCase):
    def test_tree_renders_selects_queries_replays_and_grows_live(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp:
            key=Ed25519PrivateKey.generate()
            token=issue_access(subject="reviewer",tenant="demo",scopes=["read","write","review"],
                key=key,key_id="issuer",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
            encoded=base64.urlsafe_b64encode(canonical(token)).decode().rstrip("=")
            app=Application(temp,access_keys={"issuer":key.public_key()},release_keys={},clock=lambda:"2026-11-04T12:00:00Z")
            auth="Bearer "+encoded
            source=app.dispatch("source",{"base64":base64.b64encode(b"Research notes").decode()},auth)["source_sha256"]
            def event(i,op,branch,statement,parents=()):
                app.dispatch("gardener/event",{"event_id":i,"operation":op,"branch":branch,"source_sha256":source,
                    "source_ref":"turn:"+i,"statement":statement,"parents":list(parents)},auth)
            event("e1","PROPOSE","gate","An evidence gate stops unsupported answers")
            event("e2","PROPOSE","lexical","Word overlap is a sufficient labeler",["gate"])
            event("e3","PROPOSE","llm","An LLM labeler with exact quotes",["gate"])
            event("e4","CHALLENGE","lexical","Adversarial questions reuse the passage wording")
            event("e5","PRUNE","lexical","Not viable alone")
            event("e6","SYNTHESIZE","shared","One labeler for gate and Gardener",["gate","llm"])
            http=server(app);thread=Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as runtime:
                    executable=os.environ.get("QUALITYRAG_BROWSER_EXECUTABLE")
                    browser=runtime.chromium.launch(headless=True,args=["--no-sandbox"],**({"executable_path":executable} if executable else {}))
                    page=browser.new_page(viewport={"width":1280,"height":1000})
                    errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
                    page.goto("http://127.0.0.1:"+str(http.server_port))
                    page.get_by_label("Access token").fill(encoded)
                    page.get_by_role("button",name="Open workspace").click()
                    page.locator("#home-tree").filter(has_text="branches").wait_for()
                    view(page,"tree")
                    nodes=page.locator("#garden-svg .node")
                    nodes.first.wait_for()
                    self.assertEqual(nodes.count(),4)
                    self.assertIn("pruned",page.locator('#garden-svg .node[data-branch="lexical"]').get_attribute("aria-label"))
                    page.locator('#garden-svg .node[data-branch="llm"]').click()
                    page.locator("#garden-inspector h3").filter(has_text="An LLM labeler with exact quotes").wait_for()
                    page.locator('#garden-svg .node[data-branch="shared"]').focus();page.keyboard.press("Enter")
                    page.locator("#garden-inspector").filter(has_text="synthesis · never inherits validation").wait_for()
                    # Challenge from the inspector appends a real event.
                    page.locator('#garden-svg .node[data-branch="llm"]').click()
                    page.get_by_role("button",name="Challenge").click()
                    page.get_by_label("Counterexample or objection").fill("Self-abstaining LLMs may match it")
                    page.get_by_role("button",name="Append CHALLENGE").click()
                    page.locator('#garden-svg .node[data-branch="llm"]').filter(has_text="open challenge").wait_for()
                    # Query highlights matches only.
                    page.locator("#garden-text").fill("labeler");page.get_by_role("button",name="Query").click()
                    page.locator("#garden-result").filter(has_text="3 matching branches").wait_for()
                    self.assertEqual(page.locator('#garden-svg .node[data-branch="gate"]').get_attribute("opacity"),"0.22")
                    page.locator("#garden-filter").select_option("all");page.locator("#garden-text").fill("")
                    page.get_by_role("button",name="Query").click()
                    # Replay to before the synthesis.
                    page.locator("#garden-time").fill("5");page.locator("#garden-time").dispatch_event("input")
                    page.locator("#garden-time-label").filter(has_text="event 5 / 7").wait_for()
                    self.assertEqual(page.locator('#garden-svg .node[data-branch="shared"]').count(),0)
                    page.locator("#garden-time").fill("7");page.locator("#garden-time").dispatch_event("input")
                    # Another client's event appears without a reload.
                    event("e8","PROPOSE","prefilter","Overlap as a cheap pre-filter",["lexical"])
                    page.locator('#garden-svg .node[data-branch="prefilter"]').wait_for(timeout=12000)
                    page.locator("#garden-result").filter(has_text="new event").wait_for()
                    page.set_viewport_size({"width":390,"height":844})
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),390)
                    self.assertEqual(errors,[])
                    browser.close()
            finally:http.shutdown();http.server_close()


@unittest.skipUnless(os.environ.get("QUALITYRAG_BROWSER_TESTS")=="1" and importlib.util.find_spec("playwright"),
                     "Real browser suite requires opt-in and installed Chromium")
class GovernanceBrowserTests(unittest.TestCase):
    def test_evidence_screens_work_without_touching_json(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp:
            key=Ed25519PrivateKey.generate()
            token=issue_access(subject="dev",tenant="demo",scopes=["read"],
                key=key,key_id="issuer",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
            encoded=base64.urlsafe_b64encode(canonical(token)).decode().rstrip("=")
            app=Application(temp,access_keys={"issuer":key.public_key()},release_keys={},clock=lambda:"2026-11-04T12:00:00Z")
            http=server(app);thread=Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as runtime:
                    executable=os.environ.get("QUALITYRAG_BROWSER_EXECUTABLE")
                    browser=runtime.chromium.launch(headless=True,args=["--no-sandbox"],**({"executable_path":executable} if executable else {}))
                    page=browser.new_page(viewport={"width":1280,"height":1000})
                    errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
                    page.on("response",lambda r:errors.append(r.status_text+" "+r.url) if r.status>=400 and not r.url.endswith("/favicon.ico") else None)
                    page.goto("http://127.0.0.1:"+str(http.server_port))
                    self.assertFalse(page.locator("#sidebar").is_visible())  # signed out: only the sign-in card
                    page.get_by_label("Access token").fill(encoded)
                    page.get_by_role("button",name="Open workspace").click()
                    # Home: lands on a summary; health checks ran in the background.
                    page.locator("#home-title").filter(has_text="Workspace demo").wait_for()
                    page.locator("#home-health").filter(has_text="to fix").wait_for()
                    self.assertTrue(page.locator("#badge-health").is_visible())
                    # Check an answer: sample data loads by itself; no JSON needed.
                    view(page,"ask")
                    page.locator("#gov-sample").filter(has_text="Using sample data").wait_for()
                    self.assertEqual(page.locator("#gov-passages input:checked").count(),6)
                    self.assertFalse(page.locator("#gov-pack").is_visible())  # JSON stays under Advanced
                    page.get_by_role("button",name="Check answer").click()
                    page.locator(".gov-verdict-word").filter(has_text="Supported").wait_for()
                    self.assertEqual(page.locator(".gov-verdict-tag").inner_text(),"ADMIT")
                    page.locator(".gov-headline").filter(has_text="2 rely on conditional wording and 3 rest on a single source").wait_for()
                    self.assertEqual(page.locator(".gov-req").count(),3)
                    page.locator(".gov-span").filter(has_text="Same origin as ops-7.3").wait_for()
                    page.locator('.gov-req[data-requirement="eu-screening-control"]').click()
                    self.assertEqual(page.locator(".gov-span-text mark").all_inner_texts(),["unless"])
                    # Unticking the evidence for one requirement makes the answer unsupported.
                    page.locator("#gov-passages label").filter(has_text="memo-exception").click()
                    page.get_by_role("button",name="Check answer").click()
                    page.locator(".gov-verdict-word").filter(has_text="Not enough evidence").wait_for()
                    page.locator("#gov-passages label").filter(has_text="memo-exception").click()
                    page.get_by_role("button",name="Check answer").click()
                    page.locator(".gov-verdict-word").filter(has_text="Supported").wait_for()
                    # Health: plain-language severities, fixes, code.
                    view(page,"health")
                    page.locator(".gov-finding").first.wait_for()
                    titles=page.locator(".gov-finding .gov-title").all_inner_texts()
                    self.assertIn("2 supporting span(s) admitted with a qualifier",titles)
                    page.get_by_role("button",name="Review · 2").click()
                    self.assertEqual(page.locator(".gov-finding").count(),2)
                    page.locator(".gov-finding summary").first.click()
                    page.locator(".gov-finding pre").filter(has_text="approval-reference-recorded").wait_for()
                    # Policy changes: edit a number, not JSON.
                    view(page,"changes")
                    page.locator("#gov-branch-editor").get_by_label("Independent sources needed for recovery procedure").wait_for()
                    self.assertEqual(page.locator("#gov-branch-editor input[type=number]").first.input_value(),"2")  # suggested change
                    page.get_by_role("button",name="Compare results").click()
                    page.locator(".gov-headline").filter(has_text="would change under the proposed policy").wait_for()
                    page.locator(".gov-diff .add").filter(has_text="min_independent_sources: 2").wait_for()
                    page.locator("#gov-branch-editor").get_by_label("Independent sources needed for recovery procedure").fill("1")
                    page.get_by_role("button",name="Compare results").click()
                    page.locator(".gov-headline").filter(has_text="No result would change").wait_for()
                    # Alternatives: sample loads by itself.
                    view(page,"alternatives")
                    page.locator("#gov-sib-label").filter(has_text="7 candidates").wait_for()
                    page.get_by_role("button",name="Compare alternatives").click()
                    page.locator(".gov-matrix tbody tr").first.wait_for()
                    self.assertEqual(page.locator(".gov-matrix tbody tr").count(),7)
                    self.assertEqual(page.locator(".gov-matrix .s-UNSAT").count(),1)
                    page.locator("#gov-sib-result p").filter(has_text="rivet: works under join, fails under join and separate").wait_for()
                    # Connect: copy-ready snippets for code and agents.
                    view(page,"connect")
                    self.assertIn("/api/policy/test",page.locator("#connect-snippet").inner_text())
                    page.get_by_role("button",name="AI agent (MCP)").click()
                    self.assertIn("QUALITYRAG_TOKEN_FILE",page.locator("#connect-snippet").inner_text())
                    # Home remembers what was done.
                    view(page,"home")
                    self.assertEqual(page.locator("#home-steps li.done").count(),4)
                    self.assertIn("Supported",page.locator("#home-check").inner_text())
                    # Phone: menu instead of sidebar, no sideways scroll.
                    page.set_viewport_size({"width":390,"height":844})
                    self.assertFalse(page.locator("#sidebar").is_visible())
                    view(page,"ask")
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),390)
                    self.assertEqual(errors,[])
                    browser.close()
            finally:http.shutdown();http.server_close()
