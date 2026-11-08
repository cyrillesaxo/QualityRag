"""No-cloud regression tests for guarded DigitalOcean deployment."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE=Path(__file__).with_name("provision_digitalocean.py")
spec=importlib.util.spec_from_file_location("do_provision",MODULE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestGatedProvision(unittest.TestCase):
    ADMIN="8.8.8.8/32" # public documentation test value only
    FINGERPRINT="aa:bb:cc:dd:ee:ff:01:02:03:04:05:06:07:08:09:0a"

    def test_rejects_nonpublic_or_broad_ssh_ingress(self):
        for value in ("", "127.0.0.1/32", "10.0.0.2/32",
                      "192.168.1.1/32", "0.0.0.0/0","8.8.8.0/24",
                      "2001:4860:4860::8888/128"):
            with self.subTest(value=value),self.assertRaises(ValueError):
                mod.validate_ip_range(value)

    def test_ssh_must_reference_known_fingerprint(self):
        self.assertEqual(mod.validate_fingerprint(self.FINGERPRINT),self.FINGERPRINT)
        with self.assertRaises(ValueError):mod.validate_fingerprint("root")
        with self.assertRaises(ValueError):mod.validate_fingerprint("")

    def test_droplet_stays_unconfigured_and_firewall_is_bounded(self):
        planned=mod.droplet_payload(self.ADMIN,self.FINGERPRINT)
        firewall=mod.firewall_payload(self.ADMIN)
        self.assertEqual(planned["image"],"ubuntu-24-04-x64")
        self.assertEqual(planned["size"],"s-1vcpu-2gb")
        self.assertTrue(planned["monitoring"])
        self.assertFalse(planned["backups"])
        self.assertEqual(planned["ssh_keys"],[self.FINGERPRINT])
        self.assertEqual(firewall["inbound_rules"][0]["sources"]["addresses"],[self.ADMIN])
        self.assertFalse(any(rule.get("ports")=="8769" for rule in firewall["inbound_rules"]))
        cloud=planned["user_data"]
        self.assertIn("ufw",cloud)
        self.assertIn("systemctl\", \"disable\", \"--now\", \"caddy",cloud)
        self.assertNotIn("QUALITYRAG_API_TOKEN_JSON",cloud)
        self.assertNotIn("PRIVATE KEY",cloud)

    def test_duplicate_host_prevents_paid_creation(self):
        called=[]
        def fake(method,path,token,body=None):
            called.append((method,path))
            if method=="GET" and path.startswith("/droplets"):
                return {"droplets":[{"name":mod.DROPLET_NAME}]}
            raise AssertionError("Should never proceed past existing named host")
        with patch.object(mod,"api",fake):
            with self.assertRaisesRegex(RuntimeError,"refusing duplicate"):
                mod.provision(self.ADMIN,self.FINGERPRINT,"opaque-test-token")
        self.assertEqual(len(called),1)

    def test_unknown_ssh_key_blocks_firewall_and_host(self):
        calls=[]
        def fake(method,path,token,body=None):
            calls.append((method,path))
            if path.startswith("/droplets"):return {"droplets":[]}
            if path.startswith("/account/keys"):return {"ssh_keys":[]}
            raise AssertionError("Unexpected write")
        with patch.object(mod,"api",fake):
            with self.assertRaisesRegex(RuntimeError,"SSH key fingerprint"):
                mod.provision(self.ADMIN,self.FINGERPRINT,"opaque-test-token")
        self.assertEqual(len(calls),2)

if __name__=="__main__":
    unittest.main()
