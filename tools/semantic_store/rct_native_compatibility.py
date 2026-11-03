"""Research-only verifier for a version-pinned original APX stress run.

This checks consistency of an evidence manifest, local corpus, and optional
retrieved original APX scorecard. It does not establish runtime authenticity,
semantic completeness, annotation truth, or production admission.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "data" / "apx_native_compatibility_v1.json"
CORPUS = ROOT / "data" / "semantic_role_binding_stress_v1.json"
SCHEMA = "qualityrag.apx-native-compatibility-evidence/v1"
PINNED_APX_COMMIT = "52018f0677f53eccd75fc0951e16af5247c8f8fe"
COUNTS = {
    "consequential_cases": 12,
    "consequential_detected": 0,
    "consequential_abstained": 12,
    "control_cases": 6,
    "control_flagged": 0,
    "control_abstained": 6,
}


class CompatibilityEvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityEvidenceError(message)


def verify(manifest_path: Path = MANIFEST, corpus_path: Path = CORPUS,
           scorecard_path: Path | None = None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(manifest.get("schema") == SCHEMA, "Invalid compatibility schema")
    _require(manifest.get("status") == "RESEARCH_ONLY", "Research boundary changed")
    apx, qr, assurance = (manifest.get(k, {}) for k in ("apx", "qualityrag", "assurance"))
    _require(apx.get("repository") == "cyrillesaxo/apx", "Wrong APX source")
    _require(isinstance(apx.get("commit"), str) and
             len(apx["commit"]) == 40 and
             all(c in "0123456789abcdef" for c in apx["commit"]), "Unpinned APX revision")
    _require(apx.get("commit") == PINNED_APX_COMMIT, "APX commit substitution")
    _require(apx.get("artifact_id") == 13274960886 and
             apx.get("artifact_sha256") == "aaf8bb74610216665951a162f91d70df48f5ba1ea4bdfdf9a618fc3c4a234bcd",
             "Original workflow artifact identity mismatch")
    _require(apx.get("workflow_run_id") == 41726055119,
             "Unexpected original native workflow")
    _require(apx.get("engine_schema") == "apx.semantic-text-transition/v0.1",
             "Changed engine contract")
    _require(apx.get("scorecard_schema") == "apx.qualityrag-native-stress-scorecard/v1",
             "Changed scorecard contract")
    _require(qr.get("governance_schema") ==
             "rct.native-relational-semantic-governance/v0.1",
             "Changed governance contract")
    _require(qr.get("corpus_path") ==
             "tools/semantic_store/data/semantic_role_binding_stress_v1.json",
             "Wrong corpus path")
    raw = corpus_path.read_bytes()
    _require(sha256(raw).hexdigest() == qr.get("corpus_sha256"),
             "Corpus digest mismatch: do not rewrite old evidence")
    corpus = json.loads(raw)
    cases = corpus.get("cases")
    _require(corpus.get("schema") == "rct.adversarial-text-corpus/v1" and
             isinstance(cases, list) and len(cases) == 18, "Unexpected stress corpus")
    _require(len({c["id"] for c in cases}) == len(cases), "Duplicate case ID")
    _require(sum(c["label"] == "DRIFT" for c in cases) == 12 and
             sum(c["label"] == "NO_DRIFT" for c in cases) == 6 and
             all(c["label"] in ("DRIFT", "NO_DRIFT") for c in cases),
             "Stress labels changed")
    _require(manifest.get("observed") == COUNTS, "Observed run result altered")
    _require(assurance.get("native_build_independently_attested") is False and
             assurance.get("combined_native_signed_pipeline_executed") is False and
             assurance.get("annotation_extraction_independently_validated") is False and
             assurance.get("semantic_completeness") == "UNKNOWN" and
             assurance.get("source_authority") == "NOT_ESTABLISHED" and
             assurance.get("production_admission") == "NOT_AUTHORIZED" and
             assurance.get("can_generate") is False,
             "Forbidden semantic/production assurance escalation")
    if scorecard_path is not None:
        score = json.loads(scorecard_path.read_text(encoding="utf-8"))
        _require(score.get("schema") == apx["scorecard_schema"],
                 "Original native scorecard schema mismatch")
        _require(score.get("source_corpus_sha256") == qr["corpus_sha256"],
                 "Original native scorecard corpus mismatch")
        counts = score.get("counts", {})
        _require(all(counts.get(k) == v for k, v in COUNTS.items()
                     if k not in ("consequential_cases", "control_cases")),
                 "Original scorecard counts do not match pinned run")
        outcomes = score.get("case_outcomes")
        _require(isinstance(outcomes, list) and len(outcomes) == 18 and
                 len({x.get("case_id") for x in outcomes}) == 18 and
                 {x.get("case_id") for x in outcomes} == {c["id"] for c in cases},
                 "Original native scorecard case mismatch")
        by_id = {c["id"]: c for c in cases}
        _require(all(x.get("label") == by_id[x["case_id"]]["label"] and
                     x.get("source_sha256") == sha256(by_id[x["case_id"]]["source"].encode()).hexdigest() and
                     x.get("candidate_sha256") == sha256(by_id[x["case_id"]]["candidate"].encode()).hexdigest()
                     for x in outcomes), "Original native scorecard document mismatch")
        _require(all(x.get("verdict") == "INCONCLUSIVE" and
                     x.get("outcome") == ("consequential_abstained" if x["label"] == "DRIFT" else "control_abstained")
                     for x in outcomes), "Native case verdict contradicts pinned observations")
        _require(score.get("cases") == 18 and
                 score.get("consequential_cases") == 12 and
                 score.get("control_cases") == 6 and
                 score.get("compression_authorized") is False,
                 "Original scorecard dimensions or compression boundary changed")
        _require(score.get("qualityrag_admission") == "INCONCLUSIVE" and
                 score.get("can_generate") is False and
                 score.get("semantic_completeness") == "UNKNOWN",
                 "Original scorecard claims unauthorized admission")
    return {
        "status": "CONSISTENT_RESEARCH_EVIDENCE",
        "apx_commit": apx["commit"],
        "corpus_sha256": qr["corpus_sha256"],
        "scorecard_cross_checked": scorecard_path is not None,
        "production_admission": "NOT_AUTHORIZED",
        "semantic_completeness": "UNKNOWN",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scorecard", type=Path, default=None,
                   help="Path to original APX workflow stress-scorecard JSON")
    args = p.parse_args()
    print(json.dumps(verify(scorecard_path=args.scorecard), indent=2))
