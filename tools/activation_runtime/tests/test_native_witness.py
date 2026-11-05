import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.activation_runtime.native_witness import build,COMMIT,SHA256,SOURCE
from tools.activation_runtime import witness_graph as wg
import test_witness_graph as fixture


class NativeWitnessTests(unittest.TestCase):
    def test_original_apx_matches_pinned_golden_groups(self):
        data=json.loads((Path(__file__).resolve().parents[1]/"fixtures/canonical-witness-graph.json").read_text())
        self.assertEqual((data["source_commit"],data["source_sha256"]),(COMMIT,SHA256))
        self.assertEqual(build(data["input"]),data["expected"])

    def test_duplicate_unknown_and_unbounded_input_refuse(self):
        row={"id":"a","independence_key":"a"*64}
        for rows in ([row,row],[{**row,"source_truth":True}],[row]*1001):
            with self.subTest(size=len(rows)),self.assertRaises(ValueError):build(rows)

    def test_missing_or_changed_canonical_source_never_falls_back(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):build([],apx_root=root)
            path=Path(root)/SOURCE;path.parent.mkdir(parents=True);path.write_text("export const fake=true;")
            with self.assertRaises(ValueError):build([],apx_root=root)

    def test_discrepancy_blocks_root_assessment_and_gate_projection(self):
        graph=wg.build([fixture.source("root",fixture.A),fixture.derived("copy",["root"])])
        with patch("tools.activation_runtime.native_witness.build",return_value={"nodes":[],"dependentGroups":[]}):
            with self.assertRaises(ValueError):wg.assess_exact(graph,"dose",as_of=fixture.NOW,max_age_seconds=None)
            with self.assertRaises(ValueError):wg.gate_evidence(graph)

    def test_transitive_root_resolution_matches_original_declared_grouping(self):
        graph=wg.build([fixture.source("root",fixture.A),fixture.source("other",fixture.B),
                        fixture.derived("joined",["root","other"])])
        result=wg.assess_exact(graph,"dose",as_of=fixture.NOW,max_age_seconds=None,min_independent_roots=2)
        self.assertEqual(result["independent_groups"],[["joined","other","root"]])
        self.assertEqual(result["finite_constraint_result"],"UNKNOWN")
        self.assertFalse(result["can_generate"])
