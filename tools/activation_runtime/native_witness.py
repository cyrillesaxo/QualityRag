"""Run original APX declared-independence grouping; never authenticates roots."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from .common import canonical

COMMIT="9a4f8a3e4a3fe77d576369217525e54d0162b8b0"
SOURCE="packages/apx-evidence/src/index.ts"
SHA256="49c690848c4dcb1022f815d5deb258ddd074317eb0cc3cebde40a99d069199ee"


def build(witnesses, *, apx_root=None):
    root=Path(apx_root or os.environ.get("QUALITYRAG_APX_ROOT") or Path(__file__).parent/"vendor/apx")
    try:
        if not root.is_absolute() or sha256((root/SOURCE).read_bytes()).hexdigest()!=SHA256:
            raise ValueError("Canonical WitnessGraph source mismatch")
        result=subprocess.run(["node",str(Path(__file__).with_name("native_witness_runner.mjs")),str(root)],
            input=canonical(witnesses),capture_output=True,timeout=10,check=False,
            env={"PATH":os.environ.get("PATH","/usr/bin:/bin")})
        if result.returncode or len(result.stdout)>524288:raise ValueError("Canonical WitnessGraph refused")
        return json.loads(result.stdout)
    except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        raise ValueError("Canonical WitnessGraph unavailable; independence cannot be verified") from exc
