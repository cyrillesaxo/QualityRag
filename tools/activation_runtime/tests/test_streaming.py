from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.artifacts import ArtifactStore
from tools.activation_runtime.streaming import package,release,sign_release,StreamSession
import test_scene_codec as fixture


class StreamingTests(unittest.TestCase):
    setUp=fixture.SceneCodecTests.setUp
    def test_signed_seek_pause_resume_variants_and_missing_segment_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            store=ArtifactStore(root,tenant="a")
            address,index=package(self.payload,self.model,store)
            manifest=release(address,index,tenant="a",policy_ir_sha256="a"*64,run_id="run1",sequence=1)
            key=Ed25519PrivateKey.generate()
            signed=sign_release(manifest,key,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
            session=StreamSession(store,signed_release=signed,keys={"release":key.public_key()},expected_policy_sha256="a"*64,
                                  minimum_sequence=1,as_of="2026-11-04T12:00:00Z",fallback_ref="authorized-av1-baseline")
            one=session.seek(2,3)
            self.assertEqual(one["downloaded_segments"],1)
            self.assertEqual(one["action"],"PLAY")
            raw=session.seek(2,3,variant="raw")
            self.assertEqual(raw["frames"],one["frames"])
            session.pause();self.assertEqual(session.seek(0,1)["action"],"PAUSED")
            session.resume()
            (store.root/index["segments"][0]["variants"]["reference"]).unlink()
            self.assertEqual(session.seek(0,1)["action"],"FALLBACK")
            with self.assertRaises(ValueError):
                StreamSession(store,signed_release=signed,keys={"release":key.public_key()},expected_policy_sha256="b"*64,
                              minimum_sequence=1,as_of="2026-11-04T12:00:00Z",fallback_ref="fallback")
