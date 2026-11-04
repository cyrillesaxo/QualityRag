from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.artifacts import make_manifest,sign_manifest
from tools.activation_runtime.common import canonical
from tools.activation_runtime.device import ModuleUpdater,sparse_plan


class DeviceTests(unittest.TestCase):
    def test_sparse_closure_and_hard_budget(self):
        modules={"required":{"dependencies":["base"],"memory_bytes":4,"compute_units":2,"hash":"a"*64},
                 "base":{"dependencies":[],"memory_bytes":2,"compute_units":1,"hash":"b"*64},
                 "unneeded":{"dependencies":[],"memory_bytes":100,"compute_units":100,"hash":"c"*64}}
        selected=sparse_plan(modules,["required"],max_memory_bytes=6,max_compute_units=3)
        self.assertEqual(selected["selected"],["base","required"])
        self.assertEqual(selected["action"],"ACTIVATE")
        self.assertEqual(sparse_plan(modules,["required"],max_memory_bytes=5,max_compute_units=3)["action"],"FALLBACK")

    def test_resume_atomic_activation_and_authorized_rollback_floor(self):
        with tempfile.TemporaryDirectory() as root:
            updater=ModuleUpdater(root,tenant="a")
            data=canonical({"schema":"qualityrag.grammar-module/v1","dependencies":[],"data":{"version":1}})
            address=sha256(data).hexdigest()
            self.assertEqual(updater.append(address,data[:10],offset=0,total=len(data))["status"],"PARTIAL")
            # A new updater resumes the exact same interrupted download.
            restarted=ModuleUpdater(root,tenant="a")
            self.assertEqual(restarted.append(address,data[10:],offset=10,total=len(data))["status"],"COMPLETE")
            source=restarted.store.put(b"source");artifact=restarted.store.put(b"payload")
            manifest=make_manifest(tenant="a",policy_ir_sha256="a"*64,source_sha256=source,
                                   artifact_sha256=artifact,sequence=2,dependencies=[address])
            key=Ed25519PrivateKey.generate()
            signed=sign_manifest(manifest,key,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
            binding={"policy_ir_sha256":"a"*64,"source_sha256":source,"artifact_sha256":artifact}
            result=restarted.activate(address,signed_manifest=signed,trusted_keys={"release":key.public_key()},
                         binding=binding,minimum_sequence=1,as_of="2026-11-04T12:00:00Z")
            self.assertEqual(result["address"],address)
            with self.assertRaises(ValueError):
                restarted.activate(address,signed_manifest=signed,trusted_keys={"release":key.public_key()},
                         binding=binding,minimum_sequence=3,as_of="2026-11-04T12:00:00Z")
            with self.assertRaises(ValueError):
                restarted.append("f"*64,b"bad",offset=0,total=3)


class SparseCompilationTests(unittest.TestCase):
    def test_unused_palette_module_is_compiled_out_without_frame_changes(self):
        import base64
        from hashlib import sha256
        from tools.activation_runtime.scene_codec import digest,decode_frames
        from tools.activation_runtime.device import compile_sparse_scene
        frame=bytes([1,2,3]*4)
        model={"schema":"qualityrag.scene-palette/v1","algorithm":"flat-backdrop-rgb-xor/v1",
               "palette":[[0,0,0],[1,2,3]],"training_sources":[]}
        payload={"schema":"qualityrag.scene-video/v1","codec":"scene-palette-rgb/v1","runtime_abi":"python-scene-reference/v1",
                 "model_sha256":digest(model),"width":2,"height":2,"frame_count":1,
                 "frames":[{"index":0,"backdrop":1,"mode":"raw","data":base64.b64encode(frame).decode(),"frame_sha256":sha256(frame).hexdigest()}]}
        new,new_model,receipt=compile_sparse_scene(payload,model)
        self.assertEqual(len(new_model["palette"]),1)
        self.assertEqual(decode_frames(new,new_model),[frame])
        self.assertEqual(receipt["selected_modules"],[1])
