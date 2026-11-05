import copy
import hashlib
import unittest
from finite_activation import encode, execute, digest, parse_source
from typed_ir import IR_SCHEMA, _fingerprint


def policy():
    source_hash = hashlib.sha256(b"Require original-source evidence").hexdigest()
    nodes = [{
        "node_id": "custody", "kind": "EVIDENCE_PRESENCE",
        "runtime": "METADATA_GATE_V0_1", "status": "PROJECTION_ONLY",
        "source": {"source_sha256": source_hash}, "review": {"approved": True},
        "parameters": {"requirement_id": "custody", "min_independent_sources": 1},
    }]
    return {"schema": IR_SCHEMA, "source": {"sha256": source_hash}, "nodes": nodes,
            "ir_sha256": _fingerprint({"source_sha256": source_hash, "nodes": nodes}),
            "summary": {"total": 1, "evidence_presence_projections": 1,
                        "deferred_semantic_constraints": 0}}


class FiniteActivationTest(unittest.TestCase):
    def setUp(self):
        self.raw = b'{"instruction":"Do NOT transfer","quantity":1,"unit":"mg","actor":"nurse"}'
        self.artifact = encode(self.raw, {"instruction": "i", "quantity": "q", "unit": "u", "actor": "a"})

    def run_artifact(self, artifact=None, pin=None):
        artifact = self.artifact if artifact is None else artifact
        return execute(self.raw, artifact,
                       expected_artifact_sha256=digest(artifact) if pin is None else pin,
                       ir=policy(), witnesses=[], as_of="2026-11-04T12:00:00Z")

    def test_real_round_trip_and_no_admission(self):
        result = self.run_artifact()
        self.assertEqual(result["research_output"], parse_source(self.raw))
        self.assertEqual(result["finite_constraint_result"], "SAT")
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")

    def test_tampered_payload_with_original_pin(self):
        changed = copy.deepcopy(self.artifact)
        changed["payload"]["i"] = "Transfer"
        self.assertEqual(self.run_artifact(changed, digest(self.artifact))["reason"],
                         "ARTIFACT_INTEGRITY_MISMATCH")

    def test_rehashed_semantic_tamper_still_refuses(self):
        changed = copy.deepcopy(self.artifact)
        changed["payload"]["i"] = "Transfer"
        result = self.run_artifact(changed)
        self.assertEqual(result["reason"], "RECONSTRUCTION_MISMATCH")
        self.assertIsNone(result["research_output"])
        self.assertFalse(result["fallback"]["released"])

    def test_numeric_type_tamper(self):
        changed = copy.deepcopy(self.artifact)
        changed["payload"]["q"] = True
        self.assertEqual(self.run_artifact(changed)["action"], "REFUSE")

    def test_wrong_runtime(self):
        changed = {**self.artifact, "runtime": "arbitrary-code"}
        self.assertEqual(self.run_artifact(changed)["reason"], "INCOMPATIBLE_RUNTIME")

    def test_missing_extra_and_colliding_fields(self):
        for mapping in ({}, {"instruction": "i"}, {k: "same" for k in parse_source(self.raw)}):
            with self.assertRaises(ValueError):
                encode(self.raw, mapping)

    def test_bad_source_inputs(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":{}}', b'[]', b'{}',
                    b'x' * 65537, b'\xff'):
            with self.assertRaises(ValueError):
                parse_source(raw)

    def test_wrong_source_hash(self):
        changed = {**self.artifact, "source_sha256": "0" * 64}
        self.assertEqual(self.run_artifact(changed)["reason"], "SOURCE_MISMATCH")

    def test_policy_tamper_not_ignored(self):
        ir = policy()
        ir["nodes"][0]["review"]["approved"] = False
        with self.assertRaises(ValueError):
            execute(self.raw, self.artifact, expected_artifact_sha256=digest(self.artifact),
                    ir=ir, witnesses=[], as_of="2026-11-04T12:00:00Z")

    def test_receipt_replay(self):
        self.assertEqual(self.run_artifact(), self.run_artifact())


if __name__ == "__main__":
    unittest.main()
