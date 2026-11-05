from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.artifacts import ArtifactStore
from tools.activation_runtime.streaming import package,release,sign_release,StreamSession
from tools.activation_runtime.playback_benchmark import _play,benchmark_playback
from tools.activation_runtime.media import benchmark_av1
import test_scene_codec as fixture


class PlaybackBenchmarkTests(unittest.TestCase):
    setUp=fixture.SceneCodecTests.setUp

    def test_actual_av1_and_signed_stream_startup_buffer_and_seek_measurements(self):
        with tempfile.TemporaryDirectory() as root:
            baseline=Path(root)/"baseline.mkv"
            benchmark_av1(self.source,baseline,rights_ref="owned-generated-test-pattern",split_family="fixture")
            store=ArtifactStore(Path(root)/"store",tenant="a")
            address,index=package(self.payload,self.model,store)
            manifest=release(address,index,tenant="a",policy_ir_sha256="a"*64,run_id="run1",sequence=1)
            key=Ed25519PrivateKey.generate()
            signed=sign_release(manifest,key,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
            factory=lambda:StreamSession(store,signed_release=signed,keys={"release":key.public_key()},
                expected_policy_sha256="a"*64,minimum_sequence=1,as_of="2026-11-04T12:00:00Z",fallback_ref="baseline")
            report=benchmark_playback(factory,baseline,indices=[0,2])
            self.assertTrue(report["comparison_qualified"],report)
            self.assertEqual(report["scope"],"LOCAL_BOUNDED_PLAYBACK")
            self.assertEqual(report["network_performance"],"UNMEASURED")
            self.assertEqual(len(report["seek"]["rows"]),2)
            for arm in report["arms"].values():
                self.assertGreater(arm["startup_ns"],0)
                self.assertEqual(arm["buffer_capacity_frames"],2)
                self.assertEqual(arm["frames"],4)
                self.assertEqual(len(arm["frame_waits_ns"]),3)
                self.assertEqual(arm["buffer_wait_ns"],sum(arm["frame_waits_ns"]))


class BufferWaitTests(unittest.TestCase):
    def test_observed_late_frame_produces_real_rebuffer_wait(self):
        def slow(publish,stop):
            publish(b"first")
            stop.wait(.15)
            publish(b"second")
        report=_play(slow,frame_count=2,fps=30)
        self.assertEqual(report["rebuffer_events"],1)
        self.assertGreater(report["buffer_wait_ns"],50_000_000)

    def test_missing_frame_and_unbounded_profiles_refuse(self):
        for count,fps,buffer in ((121,4,2),(2,0,2),(2,4,0)):
            with self.assertRaises(ValueError):
                _play(lambda publish,stop:None,frame_count=count,fps=fps,buffer_frames=buffer)
