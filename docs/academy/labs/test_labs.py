"""The Academy labs are teaching material: their printed verdicts must stay true."""
import pathlib, subprocess, sys, unittest

HERE = pathlib.Path(__file__).parent
EXPECT = {
    "a1_right_document_wrong_answer.py": ["verdict: INCONCLUSIVE", "verdict: ADMIT"],
    "a2_governed_abstention.py": ["WITHHELD (INCONCLUSIVE): missing evidence for eu-screening-control, approval-or-exception", "GENERATE"],
    "a3_independent_sources.py": ["INCONCLUSIVE  sources=1", "ADMIT         sources=2"],
    "a4_stale_and_contradicted.py": ["STALE_EVIDENCE", "verdict: REFUSE", "CONTRADICTION"],
    "a5_unverified_extraction.py": ["UNKNOWN_EVIDENCE", "verdict: ADMIT"],
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
