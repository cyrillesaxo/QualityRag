"""A *local CI fixture*, not a public governance API or server bootstrap.

Creates throwaway research keys and serves the existing application on a
random loopback port. Startup credentials only go to the test process pipe.
Never log or publish the printed JSON in CI.
"""
import base64
import json
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools.activation_runtime.bootstrap import initialize
from tools.activation_runtime.governance import example
from tools.activation_runtime.service import Application, server

with tempfile.TemporaryDirectory(prefix="qualityrag-mcp-integration-") as work:
    base = Path(work)
    created = initialize(base / "keys")
    config = json.loads(Path(created["keys"]).read_text())
    read_keys = lambda kind: {
        key_id: Ed25519PublicKey.from_public_bytes(base64.b64decode(encoded))
        for key_id, encoded in config[kind].items()
    }
    app = Application(base / "state",
                      access_keys=read_keys("access"),
                      release_keys=read_keys("release"),
                      minimum_sequence=config["minimum_sequence"])
    service = server(app, port=0)
    token = json.loads(Path(created["token_file"]).read_text())
    # This pipe is consumed by the test process, not emitted into Actions logs.
    print(json.dumps({"port": service.server_port,
                      "token": token, "fixture": example()}), flush=True)
    try:
        service.serve_forever(poll_interval=0.05)
    except KeyboardInterrupt:
        pass
    finally:
        service.server_close()
