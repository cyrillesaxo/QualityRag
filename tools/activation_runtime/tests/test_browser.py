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
                    page.set_viewport_size({"width":390,"height":844})
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),390)
                    target=os.environ.get("QUALITYRAG_BROWSER_SCREENSHOT")
                    if target:page.screenshot(path=target,full_page=True)
                    self.assertEqual(errors,[])
                    browser.close()
            finally:http.shutdown();http.server_close()
