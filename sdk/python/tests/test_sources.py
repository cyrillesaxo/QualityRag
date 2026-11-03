import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from qualityrag.sources import internal, property_source, file_source, studio_source, from_properties

PACK = {"id": "eu", "version": "1", "requirements": [{"id": "general"}, {"id": "eu-control"}]}

class Response:
    status = 200
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit): return self.value[:limit]

class SourceTests(unittest.TestCase):
    def test_internal_snapshot_and_property(self):
        original = json.loads(json.dumps(PACK))
        source = internal(original)
        original["id"] = "changed"
        self.assertEqual(source()["id"], "eu")
        self.assertEqual(property_source(json.dumps(PACK))()["version"], "1")
        self.assertRaises(ValueError, property_source, "{}")
    def test_file_reload_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "policy.json"
            path.write_text(json.dumps(PACK))
            source = file_source(path)
            self.assertEqual(source()["id"], "eu")
            path.write_text("{}")
            self.assertRaises(ValueError, source)
            path.unlink()
            self.assertRaises(FileNotFoundError, source)
    def test_studio_approval_integrity_and_fail_closed(self):
        digest = hashlib.sha256(json.dumps(PACK, separators=(",", ":")).encode()).hexdigest()
        payload = {"serviceId": "app", "environment": "dev",
                   "status": "APPROVED", "policy": PACK, "sha256": digest}
        source = studio_source("http://127.0.0.1:5055", "secret", "app", "dev")
        with patch("qualityrag.sources.urllib.request.urlopen", return_value=Response(json.dumps(payload).encode())):
            self.assertEqual(source()["id"], "eu")
        payload["sha256"] = "0" * 64
        with patch("qualityrag.sources.urllib.request.urlopen", return_value=Response(json.dumps(payload).encode())):
            self.assertRaises(RuntimeError, source)
        self.assertRaises(ValueError, studio_source, "http://registry.example.com", "secret", "app", "prod")
    def test_configuration_requires_explicit_mode(self):
        self.assertRaises(ValueError, from_properties, {})
        loader = from_properties({"qualityrag.packspec.source":"internal"}, PACK)
        self.assertEqual(loader()["id"],"eu")

if __name__ == "__main__": unittest.main()
