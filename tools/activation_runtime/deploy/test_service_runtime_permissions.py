"""Regression: root-only smoke must not conceal a service-account 203/EXEC."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
class RuntimePermissionsContract(unittest.TestCase):
    def test_shell_syntax(self):
        for name in ("prepare_host.sh","activate_private_backend.sh"):
            with self.subTest(name=name):
                subprocess.run(["bash","-n",str(ROOT/name)],check=True)
    def test_prepared_checkout_is_readable_but_not_writable_by_service(self):
        s=(ROOT/"prepare_host.sh").read_text()
        self.assertIn("chgrp -R qualityrag-governance /opt/qualityrag",s)
        self.assertIn("chmod -R g+rX,g-w,o-rwx /opt/qualityrag",s)
        self.assertIn("runuser -u qualityrag-governance -- /opt/qualityrag/.venv/bin/python --version",s)
    def test_activation_fails_before_authority_install_if_service_cannot_execute(self):
        s=(ROOT/"activate_private_backend.sh").read_text()
        self.assertLess(s.index("runuser -u qualityrag-governance -- /opt/qualityrag/.venv/bin/python --version"),s.index("install -o root -g qualityrag-governance -m 0640"))
if __name__=="__main__":unittest.main()
