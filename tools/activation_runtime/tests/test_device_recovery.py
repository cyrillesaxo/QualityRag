"""Real filesystem restart, racing writers and signed rollback boundaries."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.activation_runtime.artifacts import make_manifest,sign_manifest
from tools.activation_runtime.common import canonical
from tools.activation_runtime.device import ModuleUpdater


class DeviceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.up=ModuleUpdater(self.temp.name,tenant="a")
        self.data=canonical({"schema":"qualityrag.grammar-module/v1","dependencies":[],"data":{"version":1}})
        self.address=sha256(self.data).hexdigest()

    def append(self,chunk=None,offset=0,total=None):
        return self.up.append(self.address,self.data if chunk is None else chunk,
                              offset=offset,total=len(self.data) if total is None else total)

    def test_restart_reports_exact_persisted_offset_and_total(self):
        self.assertEqual(self.up.progress(self.address)["status"],"NOT_STARTED")
        row=self.append(self.data[:10]);self.assertEqual(row["written_bytes"],10)
        self.up=ModuleUpdater(self.temp.name,tenant="a")
        self.assertEqual(self.up.progress(self.address),{"status":"PARTIAL","downloaded_bytes":10,
                         "total":len(self.data),"cached_object_bytes":0})
        self.append(self.data[10:],offset=10)
        self.assertEqual(self.up.progress(self.address)["cached_object_bytes"],len(self.data))

    def test_changed_total_or_stale_offset_cannot_mutate_partial(self):
        self.append(self.data[:10])
        for offset,total in ((10,len(self.data)+1),(0,len(self.data)),(11,len(self.data))):
            with self.assertRaises(ValueError):self.append(b"x",offset=offset,total=total)
            self.assertEqual(self.up.progress(self.address)["downloaded_bytes"],10)
        self.append(self.data[10:],offset=10)

    def test_zero_length_objects_and_boolean_sizes_refuse(self):
        for offset,total in ((0,0),(False,len(self.data)),(0,True)):
            with self.assertRaises(ValueError):self.append(b"",offset=offset,total=total)
        self.assertEqual(self.up.progress(self.address)["status"],"NOT_STARTED")

    def test_completed_retry_verifies_bytes_and_reuses_cache(self):
        self.append()
        row=self.append();self.assertTrue(row["cache_hit"]);self.assertEqual(row["written_bytes"],0)
        self.assertEqual(row["received_bytes"],len(self.data))
        self.assertTrue(self.append(self.data[10:],offset=10)["cache_hit"])
        with self.assertRaises(ValueError):self.append(b"bad")
        with self.assertRaises(ValueError):self.append(b"",total=len(self.data)+1)
        self.assertEqual(self.up.store.get(self.address),self.data)

    def test_publication_failure_preserves_complete_partial_for_retry(self):
        with patch.object(self.up.store,"put",side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):self.append()
        self.assertEqual(self.up.progress(self.address)["downloaded_bytes"],len(self.data))
        self.assertFalse(self.append(b"",offset=len(self.data))["cache_hit"])
        self.assertEqual(self.up.store.get(self.address),self.data)

    def test_lost_publication_reply_recovers_without_rewriting_object(self):
        put=self.up.store.put
        def publish_then_fail(data):
            put(data)
            raise OSError("lost reply")
        with patch.object(self.up.store,"put",side_effect=publish_then_fail):
            with self.assertRaises(OSError):self.append()
        restarted=ModuleUpdater(self.temp.name,tenant="a")
        row=restarted.append(self.address,self.data,offset=0,total=len(self.data))
        self.assertTrue(row["cache_hit"])
        self.assertFalse((restarted.state/(self.address+".partial")).exists())
        self.assertFalse((restarted.state/(self.address+".download.json")).exists())

    def test_corrupt_completion_cleans_transfer_and_allows_clean_restart(self):
        with self.assertRaises(ValueError):self.append(b"x"*len(self.data))
        self.assertEqual(self.up.progress(self.address)["status"],"NOT_STARTED")
        self.append();self.assertEqual(self.up.store.get(self.address),self.data)

    def test_legacy_partial_requires_explicit_discard(self):
        (self.up.state/(self.address+".partial")).write_bytes(self.data[:10])
        with self.assertRaises(ValueError):self.append(self.data[10:],offset=10)
        with self.assertRaises(ValueError):self.up.progress(self.address)
        self.up.discard_partial(self.address);self.append()
        self.up.discard_partial(self.address)
        self.assertEqual(self.up.store.get(self.address),self.data)

    def test_concurrent_same_offset_writers_do_not_double_append(self):
        gate=Barrier(2)
        def write():
            up=ModuleUpdater(self.temp.name,tenant="a");gate.wait()
            try:return up.append(self.address,self.data[:10],offset=0,total=len(self.data))["status"]
            except ValueError:return "REFUSED"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:write(),range(2)))
        self.assertEqual(sorted(results),["PARTIAL","REFUSED"])
        self.assertEqual(self.up.progress(self.address)["downloaded_bytes"],10)
        self.append(self.data[10:],offset=10)

    def test_busy_writer_refuses_without_waiting_or_mutating(self):
        with self.up._locked():
            with self.assertRaisesRegex(ValueError,"busy"):
                ModuleUpdater(self.temp.name,tenant="a").append(self.address,self.data,offset=0,total=len(self.data))
        self.assertEqual(self.up.progress(self.address)["status"],"NOT_STARTED")

    def test_symlink_state_is_never_followed(self):
        outside=Path(self.temp.name)/"outside";outside.write_bytes(b"unchanged")
        for suffix in (".partial",".download.json"):
            path=self.up.state/(self.address+suffix);path.symlink_to(outside)
            with self.assertRaises(ValueError):self.append()
            self.assertEqual(outside.read_bytes(),b"unchanged");path.unlink()
        lock=self.up.state/"update.lock";lock.unlink();lock.symlink_to(outside)
        with self.assertRaises(OSError):self.append()
        self.assertEqual(outside.read_bytes(),b"unchanged")

    def releases(self):
        self.append();source=self.up.store.put(b"source");artifact=self.up.store.put(b"artifact")
        self.key=Ed25519PrivateKey.generate();self.keys={"release":self.key.public_key()}
        self.binding={"policy_ir_sha256":"a"*64,"source_sha256":source,"artifact_sha256":artifact}
        def signed(address,sequence):
            manifest=make_manifest(tenant="a",sequence=sequence,dependencies=[address],**self.binding)
            return sign_manifest(manifest,self.key,key_id="release",issued_at="2026-11-04T00:00:00Z",expires_at="2026-11-05T00:00:00Z")
        other=canonical({"schema":"qualityrag.grammar-module/v1","dependencies":[],"data":{"version":2}})
        address=self.up.store.put(other)
        return signed(self.address,1),address,signed(address,2)

    def activate(self,address,signed,**changes):
        args={"signed_manifest":signed,"trusted_keys":self.keys,"binding":self.binding,
              "minimum_sequence":1,"as_of":"2026-11-04T12:00:00Z"};args.update(changes)
        return self.up.activate(address,**args)

    def test_actual_signed_old_new_and_authorized_rollback_after_restart(self):
        old,new_address,new=self.releases()
        self.activate(self.address,old);self.activate(new_address,new)
        self.up=ModuleUpdater(self.temp.name,tenant="a")
        row=self.activate(self.address,old)
        self.assertEqual((row["address"],row["previous"],row["sequence"]),(self.address,new_address,1))
        self.assertEqual(row["cached_object_bytes"],len(self.data))

    def test_floor_revocation_expiry_and_binding_refusals_preserve_active_pointer(self):
        old,new_address,new=self.releases();self.activate(new_address,new)
        pointer=self.up.state/"active.json";before=pointer.read_bytes()
        for changes in ({"minimum_sequence":2},{"trusted_keys":{}},{"as_of":"2026-11-06T00:00:00Z"},
                        {"binding":{**self.binding,"policy_ir_sha256":"b"*64}}):
            with self.assertRaises(ValueError):self.activate(self.address,old,**changes)
            self.assertEqual(pointer.read_bytes(),before)

    def test_failed_pointer_publication_keeps_prior_activation(self):
        old,new_address,new=self.releases();self.activate(self.address,old)
        pointer=self.up.state/"active.json";before=pointer.read_bytes()
        with patch("tools.activation_runtime.device.os.replace",side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):self.activate(new_address,new)
        self.assertEqual(pointer.read_bytes(),before)
        self.assertEqual(self.activate(new_address,new)["previous"],self.address)
