"""Signed JWT and independent per-principal ACL tests; no external IdP."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_auth import TokenVerifier,TokenAccessError


class TokenValidationTests(unittest.TestCase):
    def setUp(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        self.jwt=jwt
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private.public_key()))
        public.update({"kid":"test-key","alg":"RS256","use":"sig"})
        self.jwks=Path(self.tmp.name)/"keys.json"
        self.acl=Path(self.tmp.name)/"acl.json"
        self.jwks.write_text(json.dumps({"keys":[public]}))
        self.acl.write_text(json.dumps({"subjects":{"user-a":["video-a","video-c"],
                                                      "user-b":["video-b"]}}))
        self.verifier=TokenVerifier(issuer="https://issuer.example",
            audience="qualityrag-video",jwks_file=str(self.jwks),
            acl_file=str(self.acl),
            operator_source_ids=frozenset({"video-a","video-b"}))

    def token(self, **overrides):
        now=int(time.time())
        data={"sub":"user-a","iss":"https://issuer.example",
              "aud":"qualityrag-video","iat":now,"exp":now+300,
              "scope":"video:read"}
        data.update(overrides)
        return self.jwt.encode(data,self.private,algorithm="RS256",
                               headers={"kid":"test-key"})

    def test_user_scopes_intersect_operator_allowlist(self):
        self.assertEqual(self.verifier.authorize(self.token())["source_ids"],frozenset({"video-a"}))
        self.assertEqual(self.verifier.authorize(self.token(sub="user-b"))["source_ids"],
                         frozenset({"video-b"}))
        self.assertEqual(self.verifier.authorize(self.token(sub="unknown"))["source_ids"],frozenset())

    def test_rejects_expired_wrong_audience_issuer_and_missing_scope(self):
        cases=[
            dict(exp=int(time.time())-300),
            dict(aud="other-service"),
            dict(iss="https://malicious.example"),
            dict(scope="other:scope"),
        ]
        for claims in cases:
            with self.subTest(claims=claims),self.assertRaises(TokenAccessError):
                self.verifier.authorize(self.token(**claims))

    def test_rejects_unsigned_and_unknown_public_key(self):
        none=self.jwt.encode({"sub":"user-a"},"",algorithm="none")
        with self.assertRaises(TokenAccessError):
            self.verifier.authorize(none)
        token=self.jwt.encode({"sub":"user-a","iss":"https://issuer.example",
                               "aud":"qualityrag-video","iat":int(time.time()),
                               "exp":int(time.time())+300,"scope":"video:read"},
                               self.private,algorithm="RS256",headers={"kid":"unknown"})
        with self.assertRaises(TokenAccessError):
            self.verifier.authorize(token)

    def test_refuses_incomplete_jwks_and_invalid_acl(self):
        self.acl.write_text(json.dumps({"subjects":{"user-a":["../escape"]}}))
        with self.assertRaises(TokenAccessError):
            TokenVerifier(issuer="https://issuer.example",audience="qualityrag-video",
                          jwks_file=str(self.jwks),acl_file=str(self.acl),
                          operator_source_ids=frozenset({"video-a"}))


if __name__=="__main__":
    unittest.main()
