"""Research-only verifier for the corrected original APX native run.

Provenance refers to a single GitHub workflow artifact; no semantic admission.
The JSON artifact is supplied by the reviewer, not downloaded implicitly.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "data/apx_native_compatibility_v2.json"
CORPUS = ROOT / "data/semantic_role_binding_stress_v1.json"
RUN_SHA = "ce5a65671a17b373281e3ee4d187d1e5d481e414"
ARCHIVE_SHA = "818bbd1753ee958f027005f01c5b9e8a04b7e0a9ab0d58a1ffa3aa80d295d3ec"
CORPUS_SHA = "cb01d8f9f0fc9f86e560f9f771cdae1d99be5cf01153c5a7657a69a391392ecd"


class ResearchEvidenceError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ResearchEvidenceError(message)


def verify(manifest_path=MANIFEST, corpus_path=CORPUS, scorecard_path=None):
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    a, q, assurance = m["apx"], m["qualityrag"], m["assurance"]
    require(m["schema"] == "qualityrag.apx-native-compatibility-evidence/v2"
            and m["status"] == "RESEARCH_ONLY", "Invalid research record")
    require(a["repository"] == "cyrillesaxo/apx"
            and a["run_commit"] == RUN_SHA
            and a["merged_fix_commit"] == "9a4f8a3e4a3fe77d576369217525e54d0162b8b0"
            and a["workflow_run_id"] == 41731710651
            and a["artifact_id"] == 13277955469
            and a["artifact_sha256"] == ARCHIVE_SHA
            and a["artifact_json_valid"] is True
            and a["engine_schema"] == "apx.semantic-text-transition/v0.1"
            and a["scorecard_schema"] == "apx.qualityrag-native-stress-scorecard/v1",
            "Native artifact identity or format substitution")
    require(q["repository"] == "cyrillesaxo/QualityRag"
            and q["corpus_sha256"] == CORPUS_SHA
            and q["governance_schema"] == "rct.native-relational-semantic-governance/v0.1",
            "Governance/corpus substitution")
    raw = Path(corpus_path).read_bytes()
    require(sha256(raw).hexdigest() == CORPUS_SHA, "Corpus byte mismatch")
    cases = json.loads(raw)["cases"]
    require(len(cases) == 18 and len({x["id"] for x in cases}) == 18,
            "Invalid corpus identity")
    expected = {"consequential_cases":12,"consequential_detected":0,
                "consequential_abstained":12,"control_cases":6,
                "control_flagged":0,"control_abstained":6}
    require(m["observed"] == expected, "Score inflation or observation rewrite")
    require(assurance["production_admission"] == "NOT_AUTHORIZED"
            and assurance["can_generate"] is False
            and assurance["semantic_completeness"] == "UNKNOWN"
            and assurance["combined_native_signed_pipeline_executed"] is False
            and assurance["native_build_independently_attested"] is False,
            "Attempted assurance escalation")
    checked = False
    if scorecard_path is not None:
        score = json.loads(Path(scorecard_path).read_text(encoding="utf-8"))
        require(score["schema"] == a["scorecard_schema"]
                and score["source_corpus_sha256"] == CORPUS_SHA
                and score["cases"] == 18
                and score["consequential_cases"] == 12
                and score["control_cases"] == 6
                and score["counts"] == {k:v for k,v in expected.items()
                                        if k not in ("consequential_cases","control_cases")}
                and score["can_generate"] is False
                and score["compression_authorized"] is False
                and score["semantic_completeness"] == "UNKNOWN"
                and score["qualityrag_admission"] == "INCONCLUSIVE",
                "Scorecard aggregate or safety mismatch")
        rows = score["case_outcomes"]
        by_id = {x["id"]:x for x in cases}
        require(len(rows) == 18 and len({x["case_id"] for x in rows}) == 18
                and {x["case_id"] for x in rows} == set(by_id),
                "Missing, duplicate or substituted scorecard case")
        for row in rows:
            case = by_id[row["case_id"]]
            require(row["label"] == case["label"]
                    and row["source_sha256"] == sha256(case["source"].encode()).hexdigest()
                    and row["candidate_sha256"] == sha256(case["candidate"].encode()).hexdigest()
                    and row["verdict"] == "INCONCLUSIVE"
                    and row["outcome"] == ("consequential_abstained" if case["label"] == "DRIFT"
                                         else "control_abstained"),
                    "Case-level native observation differs from pinned corpus")
        checked = True
    return {"status":"CONSISTENT_RESEARCH_EVIDENCE",
            "native_run_id":41731710651,
            "scorecard_cross_checked":checked,
            "production_admission":"NOT_AUTHORIZED",
            "semantic_completeness":"UNKNOWN"}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--scorecard", type=Path)
    args = p.parse_args()
    print(json.dumps(verify(scorecard_path=args.scorecard), indent=2))
