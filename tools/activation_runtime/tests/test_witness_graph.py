import sys
import unittest
from pathlib import Path

from tools.activation_runtime import witness_graph as wg

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
from qualityrag import evaluate  # noqa: E402

A, B = "a" * 64, "b" * 64
T0, NOW = "2026-11-05T10:00:00Z", "2026-11-05T12:00:00Z"


def source(wid, root, status="SUPPORTS", at=T0, obligation="dose"):
    return {"id": wid, "obligation": obligation, "status": status, "observed_at": at,
            "source_sha256": root, "custody": {"custodian": "records-office"}}


def derived(wid, parents, status="SUPPORTS", at=T0, obligation="dose"):
    return {"id": wid, "obligation": obligation, "status": status, "observed_at": at,
            "derived_from": parents, "transform": "copy"}


class WitnessGraphTests(unittest.TestCase):
    def test_roots_and_custody_are_recorded_through_derivation(self):
        g = wg.build([source("label", A), derived("excerpt", ["label"]), derived("summary", ["excerpt"])])
        self.assertEqual(g["roots"]["summary"], [A])
        self.assertEqual(g["witnesses"]["label"]["custody"]["custodian"], "records-office")

    def test_shared_roots_collapse(self):
        g = wg.build([source("label", A), derived("mirror", ["label"]), derived("translation", ["mirror"])])
        result = wg.assess_exact(g, "dose", as_of=NOW, max_age_seconds=None, min_independent_roots=2)
        self.assertEqual((result["finite_constraint_result"], result["independent_roots"]), ("UNKNOWN", 1))
        g2 = wg.build([source("label", A), source("pharmacy", B)])
        self.assertEqual(wg.assess_exact(g2, "dose", as_of=NOW, max_age_seconds=None,
                                         min_independent_roots=2)["finite_constraint_result"], "SAT")

    def test_merged_derivation_joins_groups_transitively(self):
        # A synthesis of two sources shares roots with both, so all three are one group.
        g = wg.build([source("label", A), source("pharmacy", B), derived("synthesis", ["label", "pharmacy"])])
        self.assertEqual(wg.independent_groups(g, ["label", "pharmacy", "synthesis"]),
                         [["label", "pharmacy", "synthesis"]])

    def test_contradicting_stale_unknown_or_missing_cannot_satisfy(self):
        g = wg.build([source("label", A), source("pharmacy", B, status="CONTRADICTS")])
        self.assertEqual(wg.assess_exact(g, "dose", as_of=NOW, max_age_seconds=None)["finite_constraint_result"], "UNSAT")
        stale = wg.build([source("label", A, at="2026-01-01T00:00:00Z")])
        r = wg.assess_exact(stale, "dose", as_of=NOW, max_age_seconds=3600)
        self.assertEqual((r["finite_constraint_result"], r["reasons"]),
                         ("UNKNOWN", ["INSUFFICIENT_INDEPENDENT_ROOTS", "STALE_WITNESS"]))
        unknown = wg.build([source("label", A, status="UNKNOWN")])
        self.assertEqual(wg.assess_exact(unknown, "dose", as_of=NOW, max_age_seconds=None)["finite_constraint_result"], "UNKNOWN")
        r = wg.assess_exact(g, "route", as_of=NOW, max_age_seconds=None)
        self.assertEqual((r["finite_constraint_result"], "MISSING_WITNESS" in r["reasons"]), ("UNKNOWN", True))
        future = wg.build([source("label", A, at="2026-11-06T00:00:00Z")])
        self.assertIn("FUTURE_WITNESS", wg.assess_exact(future, "dose", as_of=NOW, max_age_seconds=None)["reasons"])

    def test_never_admits(self):
        g = wg.build([source("label", A)])
        r = wg.assess_exact(g, "dose", as_of=NOW, max_age_seconds=None)
        self.assertEqual((r["finite_constraint_result"], r["qualityrag_admission"], r["can_generate"]),
                         ("SAT", "INCONCLUSIVE", False))

    def test_invalid_graphs_refuse(self):
        bad = [
            [derived("x", ["x"])],                                     # self cycle
            [derived("x", ["y"]), derived("y", ["x"])],                # cycle
            [derived("x", ["missing"])],                               # dangling parent
            [source("x", "not-a-hash")],
            [dict(source("x", A), custody={})],                        # no custodian
            [dict(source("x", A), derived_from=["y"])],                # both kinds
            [dict(derived("x", ["y"]), transform="")],
            [source("x", A), source("x", B)],                          # duplicate ID
            [dict(source("x", A), status="TRUE")],
            [dict(source("x", A), extra=1)],
            [dict(source("x", A), observed_at="2026-11-05T10:00:00")], # naive timestamp
        ]
        for witnesses in bad:
            with self.subTest(witnesses=witnesses), self.assertRaises(ValueError):
                wg.build(witnesses)

    def test_gate_counts_a_mirror_once(self):
        pack = {"id": "p", "version": "1", "requirements": [{"id": "dose", "min_independent_sources": 2}]}
        mirrored = wg.build([source("label", A), derived("mirror", ["label"])])
        naive = [dict(row, origin=row["id"]) for row in wg.gate_evidence(mirrored)]
        self.assertEqual(evaluate(pack, naive, as_of=NOW)["verdict"], "ADMIT")  # what label-based origins would do
        self.assertEqual(evaluate(pack, wg.gate_evidence(mirrored), as_of=NOW)["verdict"], "INCONCLUSIVE")
        independent = wg.build([source("label", A), source("pharmacy", B)])
        self.assertEqual(evaluate(pack, wg.gate_evidence(independent), as_of=NOW)["verdict"], "ADMIT")


if __name__ == "__main__":
    unittest.main()
