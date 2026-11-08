"""Production service token issuer test; fixtures are throwaway local keys."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from tools.activation_runtime.authority import authenticate
from tools.activation_runtime.deploy.issue_service_access import issue

AT=datetime(2026,11,8,23,0,tzinfo=timezone.utc)

class IssuerTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.key=Ed25519PrivateKey.generate()
        self.key_file=self.root/"signer.key"
        self.key_file.write_bytes(self.key.private_bytes(
            Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        os.chmod(self.key_file,0o600)
        self.out=self.root/"service.json"

    def mint(self,**changes):
        return issue(**{
            "private_key":str(self.key_file),"key_id":"service-issuer-1",
            "subject":"netlify-gateway","tenant":"dodo-operations",
            "destination":str(self.out),"minutes":30,"now":AT,
            **changes,
        })

    def test_only_read_scope_and_expires(self):
        info=self.mint()
        self.assertFalse(info["token_value_emitted"])
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode),0o600)
        envelope=json.loads(self.out.read_text())
        trust={"service-issuer-1":self.key.public_key()}
        principal=authenticate(envelope,trust,as_of=(AT+timedelta(minutes=20)).isoformat(),scope="read")
        self.assertEqual(principal.tenant,"dodo-operations")
        self.assertEqual(principal.scopes,frozenset({"read"}))
        for scope in ("write","review","admin"):
            with self.subTest(scope=scope),self.assertRaises((PermissionError,ValueError)):
                authenticate(envelope,trust,as_of=AT.isoformat(),scope=scope)
        with self.assertRaises((PermissionError,ValueError)):
            authenticate(envelope,trust,as_of=(AT+timedelta(hours=1)).isoformat(),scope="read")

    def test_refuses_world_readable_key_and_token_overwrite(self):
        os.chmod(self.key_file,0o644)
        with self.assertRaises(PermissionError):
            self.mint()
        os.chmod(self.key_file,0o600)
        self.mint()
        with self.assertRaises(FileExistsError):
            self.mint()

    def test_rejects_invalid_lifetimes_and_key_symlinks(self):
        with self.assertRaises(ValueError):
            self.mint(minutes=360)
        alias=self.root/"alias.key"
        alias.symlink_to(self.key_file)
        with self.assertRaises(PermissionError):
            self.mint(private_key=str(alias))
        self.assertFalse(self.out.exists())

if __name__=="__main__":
    unittest.main()
