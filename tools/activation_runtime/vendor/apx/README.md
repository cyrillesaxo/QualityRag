# Pinned original APX source subset

These four unmodified source files (WBC, RCoC and WitnessGraph evidence) come from cyrillesaxo/apx at commit
9a4f8a3e4a3fe77d576369217525e54d0162b8b0 under Apache-2.0 (see LICENSE).
Original author/research lineage: Cyrille Eloundou / APX. No NOTICE file exists
at that upstream revision. PROVENANCE.json records the exact source digests.

The existing Python and Node native runners independently enforce their pinned
SHA-256 values before executing this source. This subset removes the need for
a private cross-repository checkout credential in CI. It does not establish
FF-RCT parity, semantic truth or independent source admission.

To update, review the exact upstream commit and source changes, preserve the
license, update both runner pins, and rerun positive and negative golden cases.
