"""Check the signed SSH-tunnel smoke utility cannot disclose keys and checks real verdicts."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
class SignedSmokeContract(unittest.TestCase):
    def test_parses(self):
        ast.parse((ROOT/"offline_windows_smoke.py").read_text())
    def test_requires_operator_and_private_tunnel(self):
        src=(ROOT/"offline_windows_smoke.py").read_text()
        self.assertIn('sys.platform != "win32"',src)
        self.assertIn('http://127.0.0.1:18769',src)
        self.assertNotIn("https://governance.dodollc.net",src)
        self.assertIn('anonymous!=403',src)
        self.assertIn('full.get("verdict")!="ADMIT"',src)
        self.assertIn('partial.get("verdict")!="INCONCLUSIVE"',src)
        self.assertIn('signed_token_not_printed=true',src)
        self.assertNotIn('print(bearer)',src)
        self.assertNotIn('print(private)',src)
if __name__=="__main__":unittest.main()
