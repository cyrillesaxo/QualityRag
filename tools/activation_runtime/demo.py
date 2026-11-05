"""One-command reproducible finite slice. Ephemeral demo keys are never production trust.

Run: python -m tools.activation_runtime.demo --out /tmp/activation-demo
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .artifacts import ArtifactStore, make_manifest, sign_manifest
from .common import canonical, fingerprint
from .pipeline import activate_signed, RCTCache, encode, ingest_csv

ROOT = Path(__file__).resolve().parent
AT = "2026-11-04T12:00:00Z"
FIXTURES = {
    "nursing": {"instruction": "Select the action NOT permitted in the supplied example.",
                "amount": 1, "unit": "mg", "actor": "learner"},
    "legal": {"actor": "supplier", "recipient": "buyer", "obligation": "must NOT disclose"},
    "education": {"question": "Choose every item EXCEPT the named exception.", "exception": "B"},
    "clinical-description": {"observation": "Chest discomfort during running",
                             "diagnosis": None, "unsupported_inference": "UNKNOWN"},
}


def run(out):
    # Existing compiler inspects an explicit authored research policy.
    from compiler import inspect
    from typed_ir import compile_ir
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    policy_path = out / "policy-source.json"
    policy_path.write_bytes(canonical({"requirement": "Original source custody evidence is required."}))
    inspected = inspect(policy_path)
    first = inspected["candidate_constraints"][0]
    mapping = {"schema": "qualityrag.typed-mapping/v1",
               "source_sha256": inspected["source"]["sha256"],
               "rules": [{"candidate_id": first["candidate_id"], "node_id": "custody",
                          "kind": "EVIDENCE_PRESENCE",
                          "parameters": {"requirement_id": "custody", "min_independent_sources": 1},
                          "approved": True, "reviewed_by": "DEMO_LABEL_NOT_AUTHENTICATED",
                          "rationale": "Authored research fixture only; independent admission is unavailable"}]}
    ir = compile_ir(inspected, mapping)
    (out / "policy-ir.json").write_bytes(canonical(ir))
    key = Ed25519PrivateKey.generate()
    store = ArtifactStore(out / "custody", tenant="demo")
    cases = []
    for name, fields in FIXTURES.items():
        raw = canonical(fields)
        source_sha = store.put(raw)
        artifact = encode(raw, {field: "field-" + str(index) for index, field in enumerate(sorted(fields))})
        artifact_sha = store.put(canonical(artifact))
        manifest = make_manifest(tenant="demo", policy_ir_sha256=ir["ir_sha256"],
                                 source_sha256=source_sha, artifact_sha256=artifact_sha, sequence=1)
        signed = sign_manifest(manifest, key, key_id="ephemeral-demo",
                               issued_at="2026-11-04T00:00:00Z", expires_at="2026-11-05T00:00:00Z")
        result = activate_signed(raw, artifact, signed_manifest=signed,
                                 trusted_keys={"ephemeral-demo": key.public_key()}, store=store,
                                 tenant="demo", minimum_sequence=1, ir=ir, witnesses=[], as_of=AT)
        # Do not persist secret keys; no real authority is implied by this signature.
        cases.append({"case": name, "source_sha256": source_sha, "artifact_sha256": artifact_sha,
                      "receipt": result})
    stable = {"schema": "qualityrag.activation-demo/v1", "fixture_kind": "AUTHORED_SYNTHETIC",
              "cases": cases, "can_generate": False, "qualityrag_admission": "INCONCLUSIVE",
              "limitations": ["No independent domain review", "No clinical or legal advice",
                              "No video codec", "No authenticated production identity"]}
    (out / "receipt.json").write_bytes(canonical(stable))
    (out / "run.json").write_text(json.dumps({
        "python": platform.python_version(), "arguments": sys.argv,
        "fixture_sha256": fingerprint(FIXTURES),
        "receipt_sha256": hashlib.sha256(canonical(stable)).hexdigest(),
        "replay": "receipt.json is stable; run arguments and ephemeral signatures are not benchmark evidence",
    }, sort_keys=True, indent=2))
    return stable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out)
    print(json.dumps({"cases": len(result["cases"]), "can_generate": False,
                      "receipt": str(args.out / "receipt.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
