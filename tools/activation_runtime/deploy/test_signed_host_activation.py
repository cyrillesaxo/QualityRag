"""Fail-closed checks for signed host activation and offline Windows issuance."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent

class SignedHostActivationContract(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(ROOT / "activate_private_backend.sh")], check=True)

    def test_start_requires_valid_separate_public_keys(self):
        s=(ROOT/"activate_private_backend.sh").read_text()
        for required in (
            "QUALITYRAG_PUBLIC_AUTHORITY_VALIDATED",
            "qualityrag-governance-isolated",
            "Ed25519PublicKey.from_public_bytes",
            "if len(key)!=32 or key in seen",
            "install -o root -g qualityrag-governance -m 0640",
            "systemctl enable --now qualityrag-governance.service",
            '[[ "$status" != "403" ]]',
            "CADDY_PUBLIC_API_REMAINS_BLOCKED",
        ):
            with self.subTest(required=required):
                self.assertIn(required,s)
        self.assertNotIn("reverse_proxy",s)
        self.assertNotIn("ufw allow 8769",s)
        self.assertNotIn("tls internal",s)

    def test_windows_keys_are_offline_and_public_bundle_only(self):
        s=(ROOT/"offline_windows_keygen.py").read_text()
        self.assertIn('if os.name != "nt"',s)
        self.assertIn("icacls",s)
        self.assertIn('if directory.exists()',s)
        self.assertIn('"access": "production-access-1"',s)
        self.assertIn('"release": "production-release-1"',s)
        self.assertIn('public_dir = directory / "UPLOAD_PUBLIC_ONLY"',s)
        self.assertNotIn("print(raw_private)",s)

if __name__=="__main__":unittest.main()
