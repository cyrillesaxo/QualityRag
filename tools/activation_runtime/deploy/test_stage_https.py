"""HTTPS staging must never connect to the unauthenticated Python engine."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
class HTTPSStageContract(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["bash","-n",str(ROOT/"stage_https.sh")],check=True)

    def test_approved_hostname_and_ip(self):
        s=(ROOT/"stage_https.sh").read_text()
        self.assertIn("governance.dodollc.net",s)
        self.assertIn("159.65.251.50",s)
        self.assertIn('getent ahostsv4 "$DOMAIN"',s)
        self.assertIn("qualityrag-governance-isolated",s)
        self.assertIn("ubuntu:24.04",s)

    def test_tls_stays_fail_closed(self):
        s=(ROOT/"stage_https.sh").read_text()
        self.assertIn('respond @api "QualityRAG backend not configured" 503',s)
        self.assertIn('respond "Not Found" 404',s)
        self.assertIn("caddy validate",s)
        self.assertNotIn("reverse_proxy",s)
        self.assertNotIn("systemctl enable --now qualityrag-governance.service",s)
        self.assertNotIn("ufw allow 8769",s)
        self.assertNotIn("tls internal",s)

    def test_keeps_other_host_configs(self):
        s=(ROOT/"stage_https.sh").read_text()
        self.assertIn('[[ ! -e /etc/caddy/Caddyfile ]]',s)
        self.assertIn('! systemctl is-active --quiet qualityrag-governance.service',s)

if __name__=="__main__":
    unittest.main()
