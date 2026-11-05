"""Authenticated, loopback-only Semantic Garden engine for local Studio.

No remote deployment, no multi-tenant permission model, no PackSpec admission,
no background autonomous runtime. Executions are synchronous and bounded.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
import hmac
import json
import os
import sqlite3
import sys

from rct_garden_controller import run_controller
from rct_garden_projection import project_garden
from rct_garden_lifecycle import register_cycle
from store import digest

_LEDGER = str(Path(__file__).resolve().parents[1] / "research_ledger")
if _LEDGER not in sys.path:
    sys.path.insert(0, _LEDGER)
from ledger import initialize, verify_integrity

MAX_BODY = 120_000
LOCK = RLock()
ALLOWED_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def create_app(db_path: Path, token: str):
    if not isinstance(token, str) or len(token) < 24:
        raise ValueError("Explicit Garden engine token of 24+ characters required")
    db_path = Path(db_path)
    if db_path.is_symlink():
        raise ValueError("Symlink ledger database forbidden")
    if not db_path.is_file():
        raise ValueError("Existing research ledger database required")
    db = sqlite3.connect(db_path, check_same_thread=False)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        # Never initialize or silently create the ledger through this engine.
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_claims'").fetchone():
            raise ValueError("Research ledger has not been initialized")
        if not verify_integrity(db)["consistent"]:
            raise ValueError("Research ledger integrity failed")
    except Exception:
        db.close()
        raise

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code, result):
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _authorized(self):
            origin = self.headers.get("Origin")
            if origin and origin not in ALLOWED_ORIGINS:
                self._reply(403, {"error": "ORIGIN_NOT_ALLOWED"})
                return False
            if not hmac.compare_digest(self.headers.get("Authorization", ""),
                                       "Bearer " + token):
                self._reply(401, {"error": "UNAUTHORIZED"})
                return False
            return True

        def _body(self):
            content_type = self.headers.get("Content-Type", "")
            if content_type.split(";")[0].strip().lower() != "application/json":
                raise ValueError("JSON_CONTENT_TYPE_REQUIRED")
            length = self.headers.get("Content-Length", "")
            if not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
                raise ValueError("INVALID_BODY_SIZE")
            try:
                payload = json.loads(self.rfile.read(int(length)))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("INVALID_JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("JSON_OBJECT_REQUIRED")
            return payload

        def do_GET(self):
            if not self._authorized():
                return
            try:
                if self.path == "/garden/status":
                    with LOCK:
                        healthy = verify_integrity(db)["consistent"]
                    return self._reply(200 if healthy else 503, {
                        "schema": "rct.garden-engine-status/v0.1",
                        "engine": "BOUND_GARDEN_RESEARCH_CONTROLLER",
                        "version": "0.1",
                        "connected": healthy,
                        "ledger_integrity": "CONSISTENT" if healthy else "FAILED",
                        "mode": "LOOPBACK_DEVELOPMENT_ONLY",
                        "qualityrag_admission": "INCONCLUSIVE",
                        "production_ready": False,
                    })
                if self.path == "/garden/projection":
                    with LOCK:
                        result = project_garden(db)
                    return self._reply(200, result)
                return self._reply(404, {"error": "NOT_FOUND"})
            except (sqlite3.Error, ValueError):
                return self._reply(503, {"error": "GARDEN_ENGINE_UNAVAILABLE"})

        def do_POST(self):
            if not self._authorized():
                return
            if self.path != "/garden/investigate":
                return self._reply(404, {"error": "NOT_FOUND"})
            try:
                payload = self._body()
                required = {"training", "examples", "source", "revised_source",
                            "workload", "trials", "max_probes"}
                if set(payload) != required:
                    raise ValueError("EXACT_INVESTIGATION_FIELDS_REQUIRED")
                if type(payload["trials"]) is not int or not 2 <= payload["trials"] <= 3:
                    raise ValueError("INVALID_TRIAL_BUDGET")
                if type(payload["max_probes"]) is not int or not 0 <= payload["max_probes"] <= 3:
                    raise ValueError("INVALID_PROBE_BUDGET")
                # This endpoint has no oracle configuration. Ambiguous
                # research cannot invent missing evidence; NEEDS_ORACLE is
                # surfaced explicitly. Unambiguous experiments run for real.
                result = run_controller(
                    payload["training"], payload["examples"],
                    payload["source"], payload["revised_source"],
                    payload["workload"], oracle=None,
                    trials=payload["trials"],
                    max_probes=payload["max_probes"])
                if result["status"] == "EVALUATED_UNVERIFIED":
                    experiment = result["investigation"]["experiment"]
                    sources = {
                        "training": digest(payload["training"]),
                        "source": digest(payload["source"]),
                        "revised": digest(payload["revised_source"]),
                    }
                    # The HTTP body is not an authenticated source document.
                    # Persist only experiment metadata and receipt hash;
                    # never pretend we have a retrievable receipt artifact.
                    result = {**result, "ledger_persisted": False,
                              "ledger_reason": "NO_RETRIEVABLE_ATTESTED_RECEIPT"}
                else:
                    result = {**result, "ledger_persisted": False}
                return self._reply(200, result)
            except (ValueError, TypeError, KeyError) as exc:
                return self._reply(400, {"error": str(exc)})
            except Exception:
                # Do not leak input details or filesystem location.
                return self._reply(500, {"error": "GARDEN_EXECUTION_FAILED"})

        def log_message(self, format, *args):
            return

    return Handler, db


def main():
    token = os.environ.get("QUALITYRAG_GARDEN_TOKEN", "")
    db_path = os.environ.get("QUALITYRAG_RESEARCH_DB", "")
    if not db_path:
        raise ValueError("QUALITYRAG_RESEARCH_DB is required")
    port = int(os.environ.get("QUALITYRAG_GARDEN_PORT", "5057"))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid Garden port")
    handler, conn = create_app(Path(db_path), token)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        print(f"Semantic Garden local engine listening on 127.0.0.1:{port}",
              flush=True)
        server.serve_forever()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
