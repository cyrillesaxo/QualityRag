"""Index bounds are checked even for an authentically signed malformed release."""
import base64
from copy import deepcopy
from hashlib import sha256
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.artifacts import ArtifactStore
from tools.activation_runtime.scene_codec import canon,digest
from tools.activation_runtime.streaming import package,release,sign_release,StreamSession


class StreamingBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=ArtifactStore(self.temp.name,tenant="a")
        self.model={"schema":"qualityrag.scene-palette/v1","algorithm":"flat-backdrop-rgb-xor/v1","palette":[[1,2,3]]}
        self.frames=[bytes([v]*12) for v in (1,2,3)]
        self.payload={"schema":"qualityrag.scene-video/v1","codec":"scene-palette-rgb/v1","runtime_abi":"python-scene-reference/v1",
                      "model_sha256":digest(self.model),"source_sha256":"b"*64,"width":2,"height":2,"frame_count":3,
                      "fps":"4/1","source_frame_pts":["0","1/4","1/2"],"normalized_profile":"RGB24_CFR_AND_PCM32_AUDIO",
                      "audio_wav":None,"frames":[{"index":i,"backdrop":0,"mode":"raw","data":base64.b64encode(raw).decode(),
                      "frame_sha256":sha256(raw).hexdigest()} for i,raw in enumerate(self.frames)]}
        self.address,self.index=package(self.payload,self.model,self.store)
        self.manifest=release(self.address,self.index,tenant="a",policy_ir_sha256="a"*64,run_id="run1",sequence=2)
        self.key=Ed25519PrivateKey.generate()

    def session(self,index=None,*,floor=1):
        manifest=deepcopy(self.manifest)
        if index is not None:manifest["index_sha256"]=self.store.put(canon(index))
        signed=sign_release(manifest,self.key,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
        return StreamSession(self.store,signed_release=signed,keys={"release":self.key.public_key()},
                             expected_policy_sha256="a"*64,minimum_sequence=floor,as_of="2026-11-04T12:00:00Z",fallback_ref="authorized-baseline")

    def test_cold_start_fetches_only_index_model_and_requested_frame(self):
        session=self.session();self.assertEqual(len(session.loads),2)
        row=session.seek(1,2);self.assertEqual(row["frames"],self.frames[1:2])
        self.assertEqual(row["frame_times"],["1/4"]);self.assertEqual(row["downloaded_segments"],1)
        self.assertEqual(len(session.loads),3)
        self.assertEqual(session.seek(2,3,variant="raw")["frames"],self.frames[2:3])

    def test_signed_unbounded_or_wrong_typed_dimensions_refuse_at_start(self):
        for field,value in (("frame_count",10**12),("frame_count",True),("width",513),("height",None)):
            index=deepcopy(self.index);index["header"][field]=value
            with self.assertRaises(ValueError):self.session(index)
        index=deepcopy(self.index);index["header"].update(width=512,height=512,frame_count=120)
        with self.assertRaises(ValueError):self.session(index)

    def test_missing_duplicate_reordered_and_bad_dependency_indices_refuse(self):
        mutations=[lambda d:d["segments"].pop(),lambda d:d["segments"].reverse(),
                   lambda d:d["segments"][1].update(index=True),lambda d:d["segments"][0].update(dependencies=[]),
                   lambda d:d["segments"][0]["variants"].update(reference="../outside"),
                   lambda d:d["segments"][0].update(frame_sha256=None)]
        for mutate in mutations:
            index=deepcopy(self.index);mutate(index)
            with self.assertRaises(ValueError):self.session(index)

    def test_variant_and_model_contracts_refuse_before_frame_loads(self):
        for mutate in (lambda d:d.update(variants=["reference"]),lambda d:d.update(model_object="c"*64),
                       lambda d:d["segments"][0]["variants"].update(extra="d"*64),lambda d:d.update(schema="unknown")):
            index=deepcopy(self.index);mutate(index)
            with self.assertRaises(ValueError):self.session(index)

    def test_invalid_missing_and_shifted_timing_refuse(self):
        for times in (["0"],["0","0","1/2"],["0","0.3","1/2"],["0","nan","1/2"],
                      ["0","1/0","1/2"],["0",True,"1/2"],["0","1"*65,"1/2"]):
            index=deepcopy(self.index);index["header"]["source_frame_pts"]=times
            with self.assertRaises(ValueError):self.session(index)
        for fps in ("0","31","1/100","nan",True):
            index=deepcopy(self.index);index["header"]["fps"]=fps
            with self.assertRaises(ValueError):self.session(index)

    def test_timestamp_precision_is_preserved_within_declared_cfr_tolerance(self):
        index=deepcopy(self.index);index["header"]["source_frame_pts"][1]="0.250001"
        self.assertEqual(self.session(index).seek(1,2)["frame_times"],["0.250001"])

    def test_release_requires_matching_index_address_and_bounded_sequence(self):
        for address,sequence in (("f"*64,2),(self.address,0),(self.address,True),(self.address,10**10)):
            with self.assertRaises(ValueError):release(address,self.index,tenant="a",policy_ir_sha256="a"*64,run_id="run1",sequence=sequence)
        for floor in (0,True,3,10**10):
            with self.assertRaises(ValueError):self.session(floor=floor)

    def test_missing_and_malformed_frame_records_fallback_without_position_advance(self):
        for data in (b'[]',b'{"index":0,"index":1}',b'{"index":0}',b'{"index":0,"frame_sha256":null}'):
            index=deepcopy(self.index);index["segments"][0]["variants"]["reference"]=self.store.put(data)
            session=self.session(index);before=session.position
            row=session.seek(0,1)
            self.assertEqual(row["action"],"FALLBACK");self.assertEqual(row["frames"],[])
            self.assertEqual(session.position,before);self.assertFalse(row["can_generate"])
        session=self.session();(self.store.root/self.index["segments"][0]["variants"]["reference"]).unlink()
        self.assertEqual(session.seek(0,1)["action"],"FALLBACK")

    def test_corrupt_object_or_wrong_frame_identity_cannot_play(self):
        session=self.session();path=self.store.root/self.index["segments"][0]["variants"]["reference"]
        path.write_bytes(b"changed")
        self.assertEqual(session.seek(0,1)["action"],"FALLBACK")
        index=deepcopy(self.index);record=deepcopy(self.payload["frames"][1]);record["index"]=0
        index["segments"][0]["variants"]["reference"]=self.store.put(canon(record))
        self.assertEqual(self.session(index).seek(0,1)["action"],"FALLBACK")

    def test_package_refuses_invalid_timeline_before_publishing_index(self):
        payload=deepcopy(self.payload);payload["source_frame_pts"][1]="0.3"
        with self.assertRaises(ValueError):package(payload,self.model,self.store)

    def open(self,**changes):
        from tools.activation_runtime.streaming import open_stream
        signed=sign_release(self.manifest,self.key,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
        args={"signed_release":signed,"keys":{"release":self.key.public_key()},"expected_policy_sha256":"a"*64,
              "minimum_sequence":1,"as_of":"2026-11-04T12:00:00Z","fallback_ref":"authorized-baseline"}
        args.update(changes)
        return open_stream(self.store,**args)

    def test_host_open_selects_fallback_for_missing_index_or_model(self):
        self.assertEqual(self.open()["action"],"READY")
        for address in (self.index["model_object"],self.address):
            path=self.store.root/address;raw=path.read_bytes();path.unlink()
            row=self.open();self.assertEqual(row["action"],"FALLBACK")
            self.assertIsNone(row["session"]);self.assertEqual(row["reference"],"authorized-baseline")
            self.assertFalse(row["can_generate"]);self.store.put(raw)

    def test_host_open_selects_fallback_for_revocation_expiry_or_floor(self):
        for changes in ({"keys":{}},{"minimum_sequence":3},{"as_of":"2026-11-06T00:00:00Z"},
                        {"expected_policy_sha256":"b"*64}):
            row=self.open(**changes)
            self.assertEqual(row["action"],"FALLBACK");self.assertIsNone(row["session"])
