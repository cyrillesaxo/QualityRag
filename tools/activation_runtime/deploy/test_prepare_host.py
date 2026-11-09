"""Installer invariants: the operator can stage without activating public access."""
import subprocess
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent

class PrepareHostChecks(unittest.TestCase):
    def setUp(self):
        self.path=ROOT/"prepare_host.sh"
        self.body=self.path.read_text()

    def test_shell_syntax(self):
        subprocess.run(["bash","-n",str(self.path)],check=True)

    def test_exact_repo_and_commit_verified(self):
        for expected in (
            '^[0-9a-f]{40}$',
            'ubuntu:24.04',
            'qualityrag-governance-isolated',
            'https://github.com/cyrillesaxo/QualityRag.git',
            'fetch --depth 1 origin "$COMMIT"',
            'rev-parse FETCH_HEAD',
            'checkout --detach -q "$COMMIT"',
            'rev-parse HEAD',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected,self.body)

    def test_signed_runtime_staged_but_never_started(self):
        self.assertIn('systemctl disable --now qualityrag-governance.service',self.body)
        self.assertNotIn('systemctl enable --now qualityrag-governance.service',self.body)
        self.assertIn('test ! -e /etc/qualityrag-governance/authority.json',self.body)
        self.assertIn('QUALITYRAG_HOST_PREPARED_NOT_STARTED',self.body)
        self.assertNotIn('QUALITYRAG_API_TOKEN_JSON=',self.body)
        self.assertNotIn('private-issuer.key',self.body)
        self.assertIn('QUALITYRAG_LOCAL_EVIDENCE_SMOKE_PASSED ADMIT INCONCLUSIVE',self.body)

    def test_does_not_modify_firewall_or_touch_unrelated_vm(self):
        self.assertNotIn('ufw allow',self.body)
        self.assertNotIn('cloud.digitalocean.com',self.body)
        self.assertNotIn('159.203.98.9',self.body)

if __name__=="__main__":
    unittest.main()
