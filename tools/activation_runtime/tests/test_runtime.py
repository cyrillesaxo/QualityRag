import copy
from hashlib import sha256
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.artifacts import ArtifactStore, make_manifest, sign_manifest, verify_manifest
from tools.activation_runtime.common import canonical, fingerprint
from tools.activation_runtime.pipeline import ingest_csv, activate_signed, RCTCache
from tools.activation_runtime.gardener import Gardener
from tools.activation_runtime.economics import COMPONENTS, lifecycle, pareto

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packspec_compiler"))
from finite_activation import encode
from typed_ir import IR_SCHEMA, _fingerprint

AT = "2026-11-04T12:00:00Z"


def policy():
    source = sha256(b"source custody required").hexdigest()
    nodes = [{"node_id": "custody", "kind": "EVIDENCE_PRESENCE",
              "runtime": "METADATA_GATE_V0_1", "status": "PROJECTION_ONLY",
              "review": {"approved": True}, "source": {"source_sha256": source},
              "parameters": {"requirement_id": "custody", "min_independent_sources": 1}}]
    return {"schema": IR_SCHEMA, "source": {"sha256": source}, "nodes": nodes,
            "ir_sha256": _fingerprint({"source_sha256": source, "nodes": nodes}),
            "summary": {"total": 1, "evidence_presence_projections": 1,
                        "deferred_semantic_constraints": 0}}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ArtifactStore(self.temp.name, tenant="tenant-a")
        self.key = Ed25519PrivateKey.generate()
        self.keys = {"release": self.key.public_key()}
        self.raw = b'{"instruction":"NOT permitted","amount":1,"unit":"mg"}'
        self.artifact = encode(self.raw, {"instruction": "i", "amount": "a", "unit": "u"})
        self.source_sha = self.store.put(self.raw)
        self.artifact_sha = self.store.put(canonical(self.artifact))
        self.ir = policy()

    def manifest(self, **changes):
        args = dict(tenant="tenant-a", source_sha256=self.source_sha,
                    artifact_sha256=self.artifact_sha, policy_ir_sha256=self.ir["ir_sha256"],
                    sequence=2)
        args.update(changes)
        return make_manifest(**args)

    def signed(self, **changes):
        return sign_manifest(self.manifest(**changes), self.key, key_id="release",
                             issued_at="2026-11-04T00:00:00Z", expires_at="2026-11-05T00:00:00Z")

    def verify(self, envelope=None, **changes):
        args = dict(tenant="tenant-a", policy_ir_sha256=self.ir["ir_sha256"],
                    source_sha256=self.source_sha, artifact_sha256=self.artifact_sha,
                    minimum_sequence=1, as_of=AT, store=self.store)
        args.update(changes)
        return verify_manifest(self.signed() if envelope is None else envelope, self.keys, **args)

    def test_signed_activation_uses_real_gate_and_remains_unadmitted(self):
        result = activate_signed(self.raw, self.artifact, signed_manifest=self.signed(),
                                 trusted_keys=self.keys, store=self.store, tenant="tenant-a",
                                 minimum_sequence=1, ir=self.ir, witnesses=[], as_of=AT)
        self.assertEqual(result["research_output"]["instruction"], "NOT permitted")
        self.assertFalse(result["can_generate"])
        self.assertEqual(result["qualityrag_admission"], "INCONCLUSIVE")

    def test_wrong_tenant_policy_and_sequence(self):
        for changes in ({"tenant": "tenant-b"}, {"policy_ir_sha256": "0"*64},
                        {"minimum_sequence": 3}, {"as_of": "2026-11-06T12:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.verify(**changes)

    def test_signature_and_revocation(self):
        envelope = self.signed()
        envelope["payload"]["activation_manifest"]["sequence"] = 100
        with self.assertRaises(ValueError):
            self.verify(envelope)
        self.keys = {}
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_dependency_and_wrong_module_type(self):
        with self.assertRaises(FileNotFoundError):
            self.verify(self.signed(dependencies=["0"*64]))
        invalid = self.store.put(canonical({"schema": "executable-code", "data": "eval"}))
        with self.assertRaises(ValueError):
            self.verify(self.signed(dependencies=[invalid]))

    def test_transitive_resolution(self):
        leaf = self.store.put(canonical({"schema": "qualityrag.grammar-module/v1",
                                        "dependencies": [], "data": {"fields": ["unit"]}}))
        root = self.store.put(canonical({"schema": "qualityrag.grammar-module/v1",
                                        "dependencies": [leaf], "data": {}}))
        self.assertEqual(self.verify(self.signed(dependencies=[root]))["resolved_modules"],
                         sorted([leaf, root]))

    def test_cross_tenant_and_path_traversal(self):
        other = ArtifactStore(self.temp.name, tenant="tenant-b")
        with self.assertRaises(FileNotFoundError):
            other.get(self.source_sha)
        with self.assertRaises(ValueError):
            ArtifactStore(self.temp.name, tenant="../tenant-a")
        with self.assertRaises(ValueError):
            self.store.get("../anything")

    def test_corruption_and_duplicate_put(self):
        self.assertEqual(self.store.put(self.raw), self.source_sha)
        (self.store.root / self.source_sha).write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.store.get(self.source_sha)
        with self.assertRaises(ValueError):
            self.store.put(self.raw)

    def test_symlink_not_followed(self):
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(b"secret")
        target = self.store.root / ("a"*64)
        target.symlink_to(outside)
        with self.assertRaises(OSError):
            self.store.get("a"*64)


class AdapterTests(unittest.TestCase):
    def test_csv_multiline_and_exact_strings(self):
        result = ingest_csv(b'actor,instruction\r\n"nurse","Do NOT\ntransfer"\r\n')
        self.assertEqual(result["records"][0]["fields"]["instruction"], "Do NOT\ntransfer")
        self.assertEqual((result["records"][0]["line_start"], result["records"][0]["line_end"]), (2, 3))

    def test_bad_csv(self):
        for raw in (b"a,a\n1,2", b"a,b\n1", b',b\n1,2', b'a\n"unterminated'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ingest_csv(raw)


class GardenerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "garden.sqlite")
        self.garden = Gardener(self.path)
        self.addCleanup(self.garden.close)

    def append(self, id, operation, branch, **kwargs):
        return self.garden.append(event_id=id, operation=operation, branch=branch, actor="researcher",
                                  source_ref="turn:1", source_sha256="a"*64, statement="A research hypothesis",
                                  at=AT, **kwargs)

    def test_fork_synthesis_prune_reopen_and_restart(self):
        self.append("event1", "PROPOSE", "root")
        self.append("event2", "PROPOSE", "alternative", parents=["root"])
        state = self.append("event3", "SYNTHESIZE", "joined", parents=["root", "alternative"])
        self.assertEqual(state["branches"]["joined"]["evidence_status"], "UNVERIFIED")
        state = self.append("event4", "PRUNE", "root")
        self.assertFalse(state["branches"]["root"]["active"])
        state = self.append("event5", "REOPEN", "root")
        restarted = Gardener(self.path)
        try:
            self.assertEqual(state, restarted.replay())
        finally:
            restarted.close()

    def test_rejects_missing_parent_and_invalid_test(self):
        with self.assertRaises(ValueError):
            self.append("event1", "PROPOSE", "branch", parents=["missing"])
        self.assertEqual(self.garden.replay()["branches"], {})
        self.append("event2", "PROPOSE", "branch")
        with self.assertRaises(ValueError):
            self.append("event3", "TEST", "branch")
        with self.assertRaises(ValueError):
            self.append("event4", "SYNTHESIZE", "joined", parents=["branch"])

    def test_append_only_and_tamper_detection(self):
        self.append("event1", "PROPOSE", "branch")
        with self.assertRaises(sqlite3.IntegrityError):
            self.garden.db.execute("DELETE FROM gardener_events")
        self.garden.db.rollback()
        self.garden.db.execute("DROP TRIGGER gardener_no_update")
        self.garden.db.execute("UPDATE gardener_events SET event_hash=?", ("b"*64,))
        self.garden.db.commit()
        with self.assertRaises(ValueError):
            self.garden.replay()

    def test_claim_is_linked_to_existing_ledger(self):
        self.append("event1", "PROPOSE", "branch")
        import ledger
        self.assertEqual(ledger.progress(self.garden.db)["claims"][0]["claim_id"], "gardener-branch")
        self.assertTrue(ledger.verify_integrity(self.garden.db)["consistent"])


class EconomicsTests(unittest.TestCase):
    def test_missing_cost_is_unknown_not_zero(self):
        costs = {k: {"value": 1, "unit": "USD", "evidence": "ASSUMED"} for k in COMPONENTS}
        costs["review"] = {"value": None, "unit": "USD", "evidence": "UNKNOWN"}
        result = lifecycle(costs)
        self.assertIsNone(result["total_usd"])
        self.assertEqual(result["classification"], "INCONCLUSIVE")
        costs["review"] = {"value": 2, "unit": "USD", "evidence": "ASSUMED"}
        self.assertEqual(lifecycle(costs)["classification"], "SCENARIO")

    def test_pareto_excludes_fidelity_failures(self):
        base = {"id": "base", "bytes": 100, "latency_ms": 10, "energy_j": 2, "fidelity_pass": True}
        self.assertEqual(pareto([base, {**base, "id": "bad", "bytes": 1, "fidelity_pass": False},
                                  {**base, "id": "worse", "bytes": 200}]), ["base"])


class RCTTests(unittest.TestCase):
    def test_existing_typed_engine_cache_and_policy_invalidation(self):
        train = {"schema": "rct.structured-ast/v1", "facts": [
            {"id": "f1", "subject": "a", "predicate": "p", "object": "b", "source_ref": "train#1"}]}
        heldout = {"schema": "rct.structured-ast/v1", "facts": [
            {"id": "f2", "subject": "x", "predicate": "p", "object": "y", "source_ref": "heldout#1"}]}
        labels = [{"subject": "a", "object": "b", "positive": True, "source_ref": "label#1"},
                  {"subject": "b", "object": "a", "positive": False, "source_ref": "label#2"}]
        held_labels = [{"subject": "x", "object": "y", "positive": True, "source_ref": "held-label#1"},
                       {"subject": "y", "object": "x", "positive": False, "source_ref": "held-label#2"}]
        grammar = {"schema": "rct.typed-operator-grammar/v1.4", "predicate_types": {"p": ["actor", "recipient"]},
                   "operators": ["EDGE"], "max_ast_nodes": 1, "max_candidates": 10}
        cache = RCTCache()
        def run(ir):
            return cache.evaluate(train, labels, heldout, held_labels, grammar, ir,
                                  purpose="role-check", witnesses=[], as_of=AT)
        first, second = run(policy()), run(policy())
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["finite_constraint_result"], "SAT")
        self.assertEqual(first["assessment"], second["assessment"])
        ir = policy()
        ir["nodes"][0]["parameters"]["min_independent_sources"] = 2
        ir["ir_sha256"] = _fingerprint({"source_sha256": ir["source"]["sha256"], "nodes": ir["nodes"]})
        self.assertFalse(run(ir)["cache_hit"])
        held_labels[1]["positive"] = True
        self.assertEqual(run(policy())["finite_constraint_result"], "UNSAT")


class InventoryTests(unittest.TestCase):
    def test_all_51_stories_have_explicit_remaining_acceptance(self):
        from tools.activation_runtime.audit import audit
        result = audit()
        self.assertEqual(result["stories"], 51)
        self.assertEqual(result["done"], 0)

    def test_completion_claim_is_not_accepted_from_local_metadata(self):
        from tools.activation_runtime.audit import audit
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools/activation_runtime").mkdir(parents=True)
            original_root = Path(__file__).resolve().parents[3]
            (root / "FR.MD").write_text((original_root / "FR.MD").read_text())
            inventory = json.loads((original_root / "tools/activation_runtime/capabilities.json").read_text())
            inventory["stories"][0]["status"] = "DONE"
            (root / "tools/activation_runtime/capabilities.json").write_text(json.dumps(inventory))
            with self.assertRaises(ValueError):
                audit(root)
