"""Deterministic regression checks for reversible PackSpec accounting."""
import base64
from dataclasses import replace
import unittest

from tools.completeness.reversible import ConservationError, ingest, reconstruct, completeness_status


class ConservationTests(unittest.TestCase):
    def test_unicode(self):
        source = "café — except temps".encode()
        u, p, d = ingest(source, [(0, 3), (5, 9)])
        self.assertEqual(reconstruct(u, p, d), source)
        self.assertEqual(completeness_status(u, p, d)["semantic_completeness"], "UNKNOWN")

    def test_empty(self):
        self.assertEqual(reconstruct(*ingest(b"", [])), b"")

    def test_residual_only(self):
        u, p, d = ingest(b"exception", [])
        self.assertEqual(completeness_status(u, p, d)["residual_bytes"], 9)

    def test_overlap_rejected(self):
        with self.assertRaises(ConservationError):
            ingest(b"abcdef", [(0, 3), (2, 5)])

    def test_missing_span(self):
        u, p, d = ingest(b"abcdef", [(0, 2)])
        with self.assertRaises(ConservationError):
            reconstruct(u, p, replace(d, residual=()))

    def test_tampering(self):
        u, p, d = ingest(b"abcdef", [(0, 3)])
        altered = replace(p.admitted[0], payload_b64=base64.b64encode(b"XYZ").decode())
        with self.assertRaises(ConservationError):
            reconstruct(u, replace(p, admitted=(altered,)), d)

    def test_mixed_versions(self):
        u, p, d = ingest(b"abcdef", [(0, 2)])
        u2, _, _ = ingest(b"another", [])
        with self.assertRaises(ConservationError):
            reconstruct(u2, p, d)

    def test_no_semantic_self_certification(self):
        u, p, d = ingest(b"all except contractors", [(0, 3)])
        with self.assertRaises(ConservationError):
            completeness_status(u, p, replace(d, semantic_verdict="COMPLETE"))

    def test_out_of_bounds(self):
        with self.assertRaises(ConservationError):
            ingest(b"abc", [(0, 4)])


if __name__ == "__main__":
    unittest.main()
