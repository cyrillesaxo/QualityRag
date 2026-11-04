"""Visual retrieval evaluation v0.6 against independent finite relevance labels.

Evaluation requires an explicitly complete candidate pool and graded labels.
Model rankings are NOT evidence that a scene is true. Metrics apply only to
the supplied labeled scope, not arbitrary real-world media or visual identity.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any

from semantic_codex import CodexError
from store import digest

SCHEMA = "qualityrag.visual-retrieval-benchmark/v0.6"
LABELS = {"RELEVANT", "NOT_RELEVANT", "UNCERTAIN"}


def evaluate_visual_results(result: dict[str, Any], *, labels: list[dict],
                            k: int = 5, benchmark_id: str = "local-reviewed-set") -> dict:
    if not isinstance(result, dict) or result.get("schema") != "qualityrag.visual-semantic-search/v0.5":
        raise CodexError("Expected an actual indexed visual search result")
    if (result.get("truncated") is not False
            or result.get("admission") != "INCONCLUSIVE"
            or result.get("identity_recognition") != "NOT_PERFORMED"):
        raise CodexError("Complete bounded result set required for finite evaluation")
    if (type(k) is not int or not 1 <= k <= 100
            or not isinstance(benchmark_id, str) or not 1 <= len(benchmark_id) <= 120
            or not isinstance(labels, list) or not 1 <= len(labels) <= 600):
        raise CodexError("Invalid bounded evaluation inputs")
    hits = result.get("results")
    if not isinstance(hits, list) or len(hits) != result.get("evaluated_authorized_frames"):
        raise CodexError("Incomplete or mismatched result inventory")
    ids = []
    prior = float("inf")
    for hit in hits:
        if not isinstance(hit, dict) or hit.get("match_type") != "MODEL_RANKED_VISUAL_SCENE_CANDIDATE":
            raise CodexError("Unexpected result type")
        key = (hit.get("source_id"), hit.get("revision"), hit.get("record_id"))
        if any(not isinstance(x, str) or not x for x in key):
            raise CodexError("Missing version-bound record identity")
        score = hit.get("similarity")
        if type(score) not in (int, float) or not math.isfinite(score) or not -1.000001 <= score <= 1.000001:
            raise CodexError("Invalid model similarity")
        if score > prior + 1e-9:
            raise CodexError("Search results must be ranked in descending order")
        prior = score
        ids.append(key)
    if len(ids) != len(set(ids)):
        raise CodexError("Duplicate retrieved visual record")
    ground_truth = {}
    for item in labels:
        if not isinstance(item, dict) or set(item) != {"source_id","revision","record_id","label"}:
            raise CodexError("Labels must contain exact versioned record identity and verdict")
        key = (item["source_id"],item["revision"],item["record_id"])
        if any(not isinstance(x, str) or not x for x in key) or item["label"] not in LABELS:
            raise CodexError("Malformed reviewed label")
        if key in ground_truth:
            raise CodexError("Duplicate relevance label")
        ground_truth[key] = item["label"]
    # With a complete returned candidate set, every retrieved record must have
    # a label, and every label must match exactly one retrieval candidate.
    if set(ids) != set(ground_truth):
        raise CodexError("Candidate/label coverage mismatch; cannot claim recall")
    if not ids:
        raise CodexError("Empty candidate set is not an evaluated search")
    uncertain = sum(v == "UNCERTAIN" for v in ground_truth.values())
    if uncertain:
        return {
            "schema": SCHEMA, "benchmark_id": benchmark_id,
            "prompt": result["prompt"], "model_id": result["model_id"],
            "status": "INCONCLUSIVE_UNCERTAIN_LABELS",
            "candidate_count": len(ids), "uncertain_labels": uncertain,
            "precision_at_k": None, "recall_at_k": None,
            "admission": "INCONCLUSIVE", "can_generate": False,
        }
    positive = sum(v == "RELEVANT" for v in ground_truth.values())
    top = ids[:k]
    true_positives = sum(ground_truth[key] == "RELEVANT" for key in top)
    # No positives: recall is undefined, not zero/perfect.
    recall = (true_positives / positive) if positive else None
    metrics = {
        "schema": SCHEMA, "benchmark_id": benchmark_id,
        "prompt": result["prompt"], "model_id": result["model_id"],
        "status": "FINITE_LABELED_EVALUATION",
        "k": k, "candidate_count": len(ids),
        "retrieved_at_k": len(top), "positive_labels": positive,
        "precision_at_k": true_positives / len(top) if top else None,
        "recall_at_k": recall,
        "labels_fingerprint": digest(labels),
        "result_fingerprint": digest(result),
        "coverage": "LABELED_AUTHORIZED_FINITE_INDEX_ONLY",
        "real_world_generalization": "UNMEASURED",
        "source_authenticity": "UNVERIFIED",
        "admission": "INCONCLUSIVE", "can_generate": False,
    }
    return metrics
