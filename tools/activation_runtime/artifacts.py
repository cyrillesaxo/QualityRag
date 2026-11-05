"""Tenant-scoped data registry with signed compatibility and atomic writes.

The host must authenticate the principal and derive its tenant before calling.
The tenant parameter is never an authentication credential. Root and trusted-key
configuration are host-owned. Filesystem administrators remain trusted.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile

from .common import HEX, canonical, fingerprint, identity, strict_json

COMPILER = Path(__file__).resolve().parents[1] / "packspec_compiler"
if str(COMPILER) not in sys.path:
    sys.path.insert(0, str(COMPILER))
from signed_bundles import ATTEST_SCHEMA, sign, verify, _validate_period


class ArtifactStore:
    def __init__(self, root, *, tenant):
        self.tenant = identity(tenant)
        self.root = Path(root).resolve() / self.tenant
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("Symlink tenant root prohibited")

    def _path(self, digest):
        if not isinstance(digest, str) or not HEX.fullmatch(digest):
            raise ValueError("Invalid content address")
        return self.root / digest

    def put(self, raw):
        if not isinstance(raw, bytes) or not 0 < len(raw) <= 2_000_000:
            raise ValueError("Source byte budget exceeded")
        digest = sha256(raw).hexdigest()
        target = self._path(digest)
        fd, temp = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Hard link publishes without overwriting an immutable object.
            try:
                os.link(temp, target)
            except FileExistsError:
                if self.get(digest) != raw:
                    raise ValueError("Content-address collision or corrupt object")
        finally:
            os.unlink(temp)
        return digest

    def get(self, digest):
        target = self._path(digest)
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(2_000_001)
        if len(raw) > 2_000_000 or sha256(raw).hexdigest() != digest:
            raise ValueError("Corrupt content-addressed object")
        return raw


def make_manifest(*, tenant, policy_ir_sha256, source_sha256, artifact_sha256,
                  sequence, dependencies=()):
    identity(tenant)
    if type(sequence) is not int or not 1 <= sequence <= 1_000_000_000:
        raise ValueError("Positive release sequence required")
    for value in (policy_ir_sha256, source_sha256, artifact_sha256):
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise ValueError("Pinned SHA-256 required")
    deps = list(dependencies)
    if len(deps) > 64 or len(set(deps)) != len(deps) or any(
            not isinstance(v, str) or not HEX.fullmatch(v) for v in deps):
        raise ValueError("Bounded unique dependency addresses required")
    return {"schema": "qualityrag.activation-manifest/v1", "tenant": tenant,
            "runtime": "flat-json-rename/v1", "sequence": sequence,
            "policy_ir_sha256": policy_ir_sha256, "source_sha256": source_sha256,
            "artifact_sha256": artifact_sha256, "dependencies": sorted(deps)}


def sign_manifest(manifest, key, *, key_id, issued_at, expires_at):
    _validate_period(issued_at, expires_at, issued_at)
    return sign({"activation_manifest": manifest, "issued_at": issued_at,
                 "expires_at": expires_at}, key, key_id=key_id, schema=ATTEST_SCHEMA)


def verify_manifest(envelope, trusted_keys, *, tenant, policy_ir_sha256,
                    source_sha256, artifact_sha256, minimum_sequence, as_of, store):
    """Verify exact scoped release; keys omitted from trust map are revoked.

    Minimum sequence is a host-maintained floor. Rollback is possible only to a
    still trusted/signed compatible release above that floor. This is release
    authenticity and compatibility, never a semantic witness.
    """
    if type(minimum_sequence) is not int or minimum_sequence < 1:
        raise ValueError("Minimum release sequence required")
    payload = verify(envelope, trusted_keys, schema=ATTEST_SCHEMA)
    if set(payload) != {"activation_manifest", "issued_at", "expires_at"}:
        raise ValueError("Wrong signature purpose")
    _validate_period(payload["issued_at"], payload["expires_at"], as_of)
    manifest = payload["activation_manifest"]
    if not isinstance(manifest, dict):
        raise ValueError("Manifest required")
    expected = make_manifest(
        tenant=tenant, policy_ir_sha256=policy_ir_sha256,
        source_sha256=source_sha256, artifact_sha256=artifact_sha256,
        sequence=manifest.get("sequence"), dependencies=manifest.get("dependencies", []))
    if manifest != expected or manifest["sequence"] < minimum_sequence or store.tenant != tenant:
        raise ValueError("Manifest binding, tenant or rollback violation")
    # Modules are inert data. Resolve a bounded dependency DAG before activation.
    visiting, visited = set(), set()
    def visit(address, depth):
        if depth > 16 or len(visited) + len(visiting) > 64:
            raise ValueError("Dependency budget exceeded")
        if address in visiting:
            raise ValueError("Cyclic dependency")
        if address in visited:
            return
        visiting.add(address)
        module = strict_json(store.get(address))
        if not isinstance(module, dict) or set(module) != {"schema", "dependencies", "data"} or module["schema"] != "qualityrag.grammar-module/v1":
            raise ValueError("Unsupported grammar module")
        deps = module["dependencies"]
        if not isinstance(deps, list) or len(deps) > 64 or len(set(deps)) != len(deps):
            raise ValueError("Invalid module dependencies")
        for dep in deps:
            visit(dep, depth + 1)
        visiting.remove(address)
        visited.add(address)
    for dep in manifest["dependencies"]:
        visit(dep, 0)
    store.get(artifact_sha256)
    store.get(source_sha256)
    return {"manifest": manifest, "resolved_modules": sorted(visited),
            "manifest_sha256": fingerprint(manifest), "semantic_admission": "INCONCLUSIVE"}
