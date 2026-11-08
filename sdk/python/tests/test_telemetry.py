import io
import json
import unittest
from unittest.mock import patch

from qualityrag.telemetry import emit_evidence, EvidenceTelemetryError


def witness():
    return {
        "id": "ev_" + "a" * 32,
        "requirement_id": "governing-rule",
        "origin": "org_" + "b" * 32,
        "source_ref": "src_" + "c" * 32,
        "status": "SUPPORTS",
        "observed_at": "2026-11-08T11:56:00.000Z",
    }


def output(verdict="INCONCLUSIVE"):
    return io.BytesIO(json.dumps({
        "declaredOriginsOnly": True,
        "verdict": verdict,
        "id": "local-eval-id",
        "findings": [],
    }).encode())


class EvidenceTelemetryTests(unittest.TestCase):
    def kwargs(self):
        return dict(
            service_id="claims-api",
            environment="dev",
            request_id="test-001",
            trace_id="trace-001",
            evidence=[witness()],
        )

    @patch("qualityrag.telemetry.urllib.request.urlopen")
    def test_metadata_only_and_explicit_emission(self, urlopen):
        urlopen.return_value = output()
        result = emit_evidence(
            "http://127.0.0.1:5055", "secret-test-token",
            expected_verdict="INCONCLUSIVE", **self.kwargs()
        )
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        request = urlopen.call_args.args[0]
        sent = json.loads(request.data)
        self.assertEqual(set(sent), {"serviceId", "environment", "requestId", "traceId", "evidence"})
        self.assertEqual(sent["evidence"][0]["source_ref"], "src_" + "c" * 32)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:5055/v1/evidence/evaluations"
        )

    @patch("qualityrag.telemetry.urllib.request.urlopen")
    def test_no_secret_or_full_source_text(self, urlopen):
        details = self.kwargs()
        details["evidence"][0]["text"] = "customer private data"
        with self.assertRaisesRegex(ValueError, "metadata"):
            emit_evidence("http://127.0.0.1:5055", "token", **details)
        urlopen.assert_not_called()

    @patch("qualityrag.telemetry.urllib.request.urlopen")
    def test_external_cleartext_transport_refused(self, urlopen):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            emit_evidence("http://collector.example.com", "token", **self.kwargs())
        urlopen.assert_not_called()

    @patch("qualityrag.telemetry.urllib.request.urlopen")
    def test_local_registry_divergence_is_explicit(self, urlopen):
        urlopen.return_value = output("ADMIT")
        with self.assertRaisesRegex(EvidenceTelemetryError, "verdict mismatch"):
            emit_evidence(
                "http://localhost:5055", "token",
                expected_verdict="REFUSE", **self.kwargs()
            )

    @patch("qualityrag.telemetry.urllib.request.urlopen")
    def test_missing_evidence_can_be_reported(self, urlopen):
        urlopen.return_value = output()
        details = self.kwargs()
        details["evidence"] = []
        result = emit_evidence("http://localhost:5055", "token", **details)
        self.assertEqual(result["verdict"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
