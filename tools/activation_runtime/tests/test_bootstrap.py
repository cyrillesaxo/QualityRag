from pathlib import Path
import tempfile
import unittest
from tools.activation_runtime.bootstrap import initialize
from tools.activation_runtime.authority import authenticate
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import base64,json
from datetime import datetime,timezone


class BootstrapTests(unittest.TestCase):
    def test_runnable_local_bootstrap_has_private_permissions_and_no_fake_independence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"research"
            receipt=initialize(root)
            config=json.loads((root/"public-keys.json").read_text())
            token=json.loads((root/"access-token.json").read_text())
            keys={kid:Ed25519PublicKey.from_public_bytes(base64.b64decode(value)) for kid,value in config["access"].items()}
            principal=authenticate(token,keys,as_of=datetime.now(timezone.utc).isoformat(),scope="read")
            self.assertEqual(principal.tenant,"local")
            self.assertEqual((root/"local-issuer.key").stat().st_mode&0o777,0o600)
            self.assertEqual(receipt["independent_review"],"NOT_CREATED")
            with self.assertRaises(FileExistsError):initialize(root)
