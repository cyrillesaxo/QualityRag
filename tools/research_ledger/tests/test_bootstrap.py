"""QualityRag milestone bootstrap never turns a hypothesis into a proven fact."""
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bootstrap_qualityrag import seed
from ledger import verify_integrity, progress

class BootstrappingTests(unittest.TestCase):
    def test_history_is_persistent_and_cautiously_classified(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"research.db"
            db=sqlite3.connect(path)
            one=seed(db)
            self.assertEqual(one["new_claims"],14)
            self.assertEqual(one["report"]["counts"]["by_status"]["IMPLEMENTED"],11)
            self.assertEqual(one["report"]["counts"]["by_status"]["UNVERIFIED"],3)
            self.assertTrue(verify_integrity(db)["consistent"])
            self.assertEqual(seed(db)["new_claims"],0)
            db.close()
            reopened=sqlite3.connect(path)
            self.assertEqual(progress(reopened,project="QualityRag")["counts"]["total"],14)
            reopened.close()

if __name__=="__main__":
    unittest.main()
