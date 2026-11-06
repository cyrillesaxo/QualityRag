"""The Academy labs are teaching material: their printed verdicts must stay true."""
import pathlib, subprocess, sys, unittest

HERE = pathlib.Path(__file__).parent
EXPECT = {
    "a1_right_document_wrong_answer.py": ["verdict: INCONCLUSIVE", "verdict: ADMIT"],
    "a2_governed_abstention.py": ["WITHHELD (INCONCLUSIVE): missing evidence for eu-screening-control, approval-or-exception", "GENERATE"],
    "a3_independent_sources.py": ["INCONCLUSIVE  sources=1", "ADMIT         sources=2"],
    "a4_stale_and_contradicted.py": ["STALE_EVIDENCE", "verdict: REFUSE", "CONTRADICTION"],
    "a5_unverified_extraction.py": ["UNKNOWN_EVIDENCE", "verdict: ADMIT"],
    "a6_combine_documents.py": ["verdict: INCONCLUSIVE", "dpa-in-place", "verdict: ADMIT", "msa -REQUIRES-> dpa", "INVALID_EXPLICIT_DECLARATION", "STRUCTURAL_CANDIDATE_NOT_FACT", "admission: INCONCLUSIVE"],
    "a7_images_and_video.py": ["lab/architecture-reversed.png", "distance=0", "identity=UNKNOWN", "admission: INCONCLUSIVE"],
    "a8_wrong_scope.py": ["verdict: INCONCLUSIVE", "applies-to-eu", "verdict: ADMIT", "review: NOT_AUTHENTICATED", "is rejected"],
    "a12_measure_improvement.py": ["11 recorded cases", "gateway-recovery@1.0", "answer rate 100%   false admissions 60%", "1.1-two-origins", "answer rate 83%   false admissions 0%"],
    "a13_demo_vs_production.py": ["demo cases", "false admissions 0%", "held-out production cases", "false admissions 75%"],
    "a14_every_change_breaks.py": ["min_independent_sources 1 -> 2", "4 verdicts changed", "false_admission_removed", "field-regulator", "correct_answer_lost", "false admissions removed 3 · correct answers lost 1"],
}


class AcademyLabs(unittest.TestCase):
    def test_labs_print_the_taught_verdicts(self):
        for name, needles in EXPECT.items():
            out = subprocess.run([sys.executable, str(HERE / name)], capture_output=True, text=True, check=True).stdout
            pos = 0
            for n in needles:
                i = out.find(n, pos)
                self.assertGreaterEqual(i, 0, f"{name}: expected {n!r} after position {pos}\n{out}")
                pos = i + len(n)


if __name__ == "__main__":
    unittest.main()
