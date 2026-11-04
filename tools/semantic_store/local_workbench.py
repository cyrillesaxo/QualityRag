"""Loopback-only Semantic Codex directory workbench bridge.

Local single-user development only. Directory root is fixed at process startup
and NEVER accepted from browser input. Separate local bearer token; no registry
privilege inheritance. Do not publish this service or proxy it from the internet.
"""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock

from directory_codex import index_directory, search_store, find_visual_similar
from visual_semantic import OpenClipEncoder, index_visual_semantics, find_visual_scenes
from semantic_find_sql import execute_find
from semantic_codex import CodexError
from store import SemanticStore

MAX_BODY = 5000
MAX_REQUEST = 8192
LOCK = RLock()


def create_app(root: Path, db_path: Path, token: str, *, namespace: str = "local"):
    if not token or len(token) < 24:
        raise ValueError("Explicit local token of at least 24 characters required")
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise ValueError("Configured directory does not exist or is a symlink")
    if not namespace.isascii() or not namespace.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Invalid namespace")
    root = root.resolve(strict=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    store = SemanticStore(conn)
    store.initialize()
    # Vision-language inference is deliberately opt-in. No silent stub/model
    # fallback; model weights may require a one-time approved download.
    semantic_model = None
    if os.environ.get("QUALITYRAG_ENABLE_SCENE_MODEL") == "1":
        semantic_model = OpenClipEncoder()

    def authorized(principal: str, source: str, revision: str) -> bool:
        return principal == "local-owner" and source.startswith(namespace + "/")

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, data: dict):
            raw = json.dumps(data, ensure_ascii=False).encode("utf8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _auth(self):
            provided = self.headers.get("Authorization", "")
            if not hmac.compare_digest(provided, "Bearer " + token):
                self._reply(401, {"error": "UNAUTHORIZED"})
                return False
            # The browser interface is localhost:5173, proxied through Vite.
            # Never silently allow a cross-origin web page to trigger indexing.
            origin = self.headers.get("Origin")
            if origin and origin not in ("http://127.0.0.1:5173", "http://localhost:5173"):
                self._reply(403, {"error": "ORIGIN_NOT_ALLOWED"})
                return False
            return True

        def _payload(self):
            size = self.headers.get("Content-Length")
            if size is None or not size.isdecimal() or int(size) > MAX_BODY:
                raise ValueError("INVALID_BODY_SIZE")
            try:
                data = json.loads(self.rfile.read(int(size)))
            except (ValueError, UnicodeError) as e:
                raise ValueError("INVALID_JSON") from e
            if not isinstance(data, dict):
                raise ValueError("INVALID_JSON_OBJECT")
            return data

        def do_GET(self):
            if not self._auth():
                return
            if self.path == "/semantic/status":
                self._reply(200, {"schema": "qualityrag.semantic-local-status/v0.1",
                                  "namespace": namespace,
                                  "directory": root.name,
                                  "formats": ["csv", "json", "vtt", "pdf", "docx", "html", "htm", "txt", "png", "jpg", "jpeg", "webp", "mp4", "mov", "mkv"],
                                  "mode": "LOOPBACK_LOCAL_ONLY",
                                  "visual_identity_recognition": "NOT_PERFORMED",
                                  "scene_model_ready": semantic_model is not None,
                                  "scene_model_id": semantic_model.model_id if semantic_model else None})
            else:
                self._reply(404, {"error": "NOT_FOUND"})

        def do_POST(self):
            if not self._auth():
                return
            if self.path not in ("/semantic/index", "/semantic/find", "/semantic/visual-similar", "/semantic/scenes/index", "/semantic/scenes/find"):
                return self._reply(404, {"error": "NOT_FOUND"})
            try:
                data = self._payload()
                if self.path == "/semantic/index":
                    if data:
                        raise ValueError("INDEX_ARGUMENTS_NOT_ALLOWED")
                    with LOCK:
                        result = index_directory(store, root, namespace=namespace,
                                                 principal="local-owner",
                                                 authorize_source=authorized)
                elif self.path in ("/semantic/scenes/index", "/semantic/scenes/find"):
                    if semantic_model is None:
                        return self._reply(503, {"error":"SCENE_MODEL_NOT_CONFIGURED"})
                    if self.path == "/semantic/scenes/index":
                        if data:
                            raise ValueError("SCENE_INDEX_ARGUMENTS_NOT_ALLOWED")
                        with LOCK:
                            result = index_visual_semantics(
                                store, root, namespace=namespace, principal="local-owner",
                                authorize_source=authorized, encoder=semantic_model)
                    else:
                        if (set(data)!={"prompt"} or not isinstance(data["prompt"],str)):
                            raise ValueError("EXPECTED_SCENE_PROMPT")
                        with LOCK:
                            result = find_visual_scenes(
                                store, data["prompt"], namespace=namespace,
                                principal="local-owner", authorize_source=authorized,
                                encoder=semantic_model)
                elif self.path == "/semantic/visual-similar":
                    if (set(data) != {"reference_source_id"}
                            or not isinstance(data["reference_source_id"], str)):
                        raise ValueError("EXPECTED_INDEXED_IMAGE_SOURCE_ID")
                    with LOCK:
                        result = find_visual_similar(
                            store, reference_source_id=data["reference_source_id"],
                            namespace=namespace, principal="local-owner",
                            authorize_source=authorized)
                else:
                    if set(data) != {"statement"} or not isinstance(data["statement"], str):
                        raise ValueError("EXPECTED_FIND_STATEMENT")
                    with LOCK:
                        result = execute_find(store, data["statement"], principal="local-owner",
                                              authorize_source=authorized)
                    if result["plan"]["namespace"] != namespace:
                        raise ValueError("NAMESPACE_NOT_ALLOWED")
                return self._reply(200, result)
            except (ValueError, CodexError, PermissionError) as e:
                self._reply(400, {"error": str(e)})
            except sqlite3.DatabaseError:
                self._reply(500, {"error": "INDEX_STORE_UNAVAILABLE"})

        def log_message(self, format, *args):
            # Avoid logging query content or sensitive file names.
            return

    return Handler, conn


def main():
    token = os.environ.get("QUALITYRAG_SEMANTIC_TOKEN", "")
    root = Path(os.environ.get("QUALITYRAG_SEMANTIC_ROOT", ""))
    db = Path(os.environ.get("QUALITYRAG_SEMANTIC_DB", ".qualityrag/semantic-local.sqlite3"))
    if not os.environ.get("QUALITYRAG_SEMANTIC_ROOT"):
        raise ValueError("QUALITYRAG_SEMANTIC_ROOT is required")
    db.parent.mkdir(parents=True, exist_ok=True)
    handler, conn = create_app(root, db, token)
    port = int(os.environ.get("QUALITYRAG_SEMANTIC_PORT", "5056"))
    if port < 1024 or port > 65535:
        raise ValueError("Port must be 1024..65535")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        print(f"Semantic local workbench: http://127.0.0.1:{port} (local only)", flush=True)
        server.serve_forever()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
