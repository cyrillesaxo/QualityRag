"""Execute hash-pinned original APX WBC/RCoC sources through a fixed Node runner.

APX root is trusted host configuration, never a user-supplied model/plugin path.
No bundled Python substitute is used. Missing original sources raise explicitly.
"""
import json
import os
from pathlib import Path
import subprocess

from .common import canonical

COMMIT = "9a4f8a3e4a3fe77d576369217525e54d0162b8b0"
SOURCES = {
    "packages/apx-wbc/src/index.ts": "d25ab8317bfd37407fa68a711985e567317faf89f97fd3aadc65d2cd26217898",
    "packages/apx-rcoc/src/index.ts": "33bf9a1ffe7e18ac28e859de514bf1a3beb8e39f9c4014c6764cd32d224f110a",
    "packages/apx-rcoc/src/canonical-taxonomy.ts": "315588fd9efaf20b8021e7ca4da19066bfd86c3d22b82a40f088f0e5908eee97",
}


def evaluate(apx_root, request):
    from hashlib import sha256
    root = Path(apx_root)
    if not root.is_absolute() or not isinstance(request, dict):
        raise ValueError("Host-selected absolute APX root and typed request required")
    for path, expected in SOURCES.items():
        if sha256((root / path).read_bytes()).hexdigest() != expected:
            raise ValueError("Original APX source differs from pinned canonical version")
    payload = canonical(request)
    result = subprocess.run(
        ["node", str(Path(__file__).with_name("native_apx_runner.mjs")), str(root)],
        input=payload, capture_output=True, timeout=10, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    if result.returncode or len(result.stdout) > 65536:
        raise ValueError("Canonical APX execution unavailable or invalid request")
    return {"schema": "qualityrag.canonical-apx-activation/v1",
            "source_repository": "cyrillesaxo/apx", "source_commit": COMMIT,
            "source_hashes": SOURCES, "result": json.loads(result.stdout),
            "qualityrag_admission": "INCONCLUSIVE", "can_generate": False,
            "boundary": "Canonical finite WBC/RCoC execution, not attested source truth or metric authenticity"}
