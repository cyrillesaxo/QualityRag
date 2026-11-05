"""Local Garden console ⇄ actual controller HTTP integration tests."""
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request
from urllib.error import HTTPError

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "research_ledger"))
from ledger import initialize, claim, evidence, assess
from rct_garden_http import create_app
from rct_garden_demo import fixture

TOKEN = "garden-unit-test-token-at-least-24-characters"


class GardenHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "research.sqlite"
        with sqlite3.connect(self.db_path) as db:
            initialize(db)
            claim(db, claim_id="garden.test.hypothesis", project="QualityRag",
                  kind="HYPOTHESIS", statement="Unverified test hypothesis")
            evidence(db, evidence_id="garden.test.evidence", kind="OBSERVATION",
                     uri="https://example.org/test-evidence",
                     description="Test-only provenance reference")
            assess(db, event_id="garden.test.event",
                   claim_id="garden.test.hypothesis", assessment="INCONCLUSIVE",
                   reason="Test-only observation is insufficient",
                   actor="fixture", evidence_ids=["garden.test.evidence"])
        handler, self.connection = create_app(self.db_path, TOKEN)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.connection.close()
        self.temp.cleanup()

    def call(self, method, endpoint, payload=None, *, token=TOKEN, origin=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": "Bearer " + token}
        if origin:
            headers["Origin"] = origin
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = request.Request("http://127.0.0.1:" + str(self.port) + endpoint,
                              data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=10) as result:
                return result.status, json.load(result)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_auth_status_and_projected_history(self):
        code, rejected = self.call("GET", "/garden/status", token="wrong")
        self.assertEqual(code, 401)
        self.assertEqual(rejected["error"], "UNAUTHORIZED")
        code, status = self.call("GET", "/garden/status")
        self.assertEqual(code, 200)
        self.assertTrue(status["connected"])
        self.assertEqual(status["ledger_integrity"], "CONSISTENT")
        self.assertFalse(status["production_ready"])
        code, projection = self.call("GET", "/garden/projection")
        self.assertEqual(code, 200)
        self.assertEqual(projection["summary"]["branches"], 1)
        self.assertEqual(projection["summary"]["events"], 1)
        self.assertFalse(projection["promotion_authorized"])

    def test_origin_is_enforced(self):
        code, result = self.call("GET", "/garden/status",
                                 origin="https://attacker.example")
        self.assertEqual(code, 403)
        self.assertEqual(result["error"], "ORIGIN_NOT_ALLOWED")
        code, _ = self.call("GET", "/garden/status",
                            origin="http://localhost:5173")
        self.assertEqual(code, 200)

    def test_real_engine_executes_bounded_experiment(self):
        training = fixture("train-")
        source = fixture("live-")
        revised = fixture("live-", revised=True)
        manifest = {
            "training": training,
            "examples": [
                {"subject": "train-s0", "destination": "train-t0", "expected": True},
                {"subject": "train-s1", "destination": "train-t1", "expected": True},
                {"subject": "train-s0", "destination": "train-t1", "expected": False},
            ],
            "source": source, "revised_source": revised,
            "workload": {"subjects": ["live-s0", "live-s1"]},
            "trials": 2, "max_probes": 0,
        }
        code, result = self.call("POST", "/garden/investigate", manifest)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["status"], "EVALUATED_UNVERIFIED")
        self.assertEqual(len(result["investigation"]["experiment"]["results"]), 6)
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["ledger_persisted"])
        # A successful experiment cannot be silently written as verified.
        self.assertEqual(self.call("GET", "/garden/projection")[1]["summary"]["branches"], 1)

    def test_invalid_budget_and_missing_auth_fail(self):
        code, _ = self.call("POST", "/garden/investigate", {"trials": 2},
                            token="wrong")
        self.assertEqual(code, 401)
        code, result = self.call("POST", "/garden/investigate", {"trials": 2})
        self.assertEqual(code, 400)
        self.assertIn("EXACT_INVESTIGATION_FIELDS_REQUIRED", result["error"])
        self.assertEqual(self.call("GET", "/garden/unknown")[0], 404)

    def test_missing_database_refused(self):
        with self.assertRaisesRegex(ValueError, "Existing research ledger"):
            create_app(Path(self.temp.name) / "missing.sqlite", TOKEN)


if __name__ == "__main__":
    unittest.main()
