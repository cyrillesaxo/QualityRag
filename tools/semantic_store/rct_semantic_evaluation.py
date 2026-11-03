"""Version-bound adversarial semantic evaluation with explicit abstention accounting.

A reviewed label says whether the candidate changed a consequential meaning
distinction, not whether a detector ought to accept the candidate. Detectors
can only REFUSE or INCONCLUSIVE; INCONCLUSIVE is an abstention, NEVER "safe".
No semantic admission or generation is possible. Native APX runs are optional
but never substituted or counted as passed when unavailable.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

from store import digest

SCHEMA = "rct.semantic-drift-evaluation/v1"
DATASET_SCHEMA = "rct.adversarial-text-corpus/v1"
MAX_CASES = 500
MAX_TEXT_BYTES = 8192
DOMAINS = frozenset({"nursing", "hvac", "driving", "legal", "finance", "everyday"})
LABELS = frozenset({"DRIFT", "NO_DRIFT"})


def load_corpus(path: str | Path) -> dict:
    raw = Path(path).read_bytes()
    if len(raw) > 1_500_000:
        raise ValueError("Corpus exceeds bounded byte budget")
    corpus = json.loads(raw)
    validate_corpus(corpus)
    return corpus


def validate_corpus(corpus: dict) -> None:
    if (not isinstance(corpus, dict) or set(corpus) != {"schema", "cases"}
            or corpus.get("schema") != DATASET_SCHEMA
            or not isinstance(corpus.get("cases"), list)
            or not 2 <= len(corpus["cases"]) <= MAX_CASES):
        raise ValueError("Invalid bounded semantic drift corpus")
    seen = set()
    counts = Counter()
    for case in corpus["cases"]:
        if (not isinstance(case, dict)
                or set(case) != {"id", "domain", "source", "candidate",
                                "label", "critical_distinction"}):
            raise ValueError("Corpus cases require exact versioned fields")
        identifier = case["id"]
        if (not isinstance(identifier, str) or not identifier or identifier in seen
                or len(identifier) > 96 or case["domain"] not in DOMAINS
                or case["label"] not in LABELS
                or not isinstance(case["critical_distinction"], str)
                or not case["critical_distinction"]
                or any(not isinstance(case[k], str) or not case[k]
                       or len(case[k].encode("utf-8")) > MAX_TEXT_BYTES
                       for k in ("source", "candidate"))):
            raise ValueError("Invalid or duplicate case")
        seen.add(identifier)
        counts[case["label"]] += 1
    if not all(counts[x] for x in LABELS):
        raise ValueError("Both consequential drift and controls are mandatory")


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _wilson_95(successes: int, n: int) -> list[float] | None:
    """Descriptive 95% binomial Wilson interval for a finite labeled sample.

    No inference to a production/document population is justified unless
    cases are independently sampled from that target population.
    """
    if not n:
        return None
    from math import sqrt
    z = 1.959963984540054
    p = successes / n
    denom = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, mid - half), 6),
            round(min(1.0, mid + half), 6)]


def evaluate_corpus(corpus: dict, detector: Callable[[str, str], dict], *,
                    detector_id: str) -> dict:
    validate_corpus(corpus)
    if not callable(detector) or not isinstance(detector_id, str) or not detector_id:
        raise ValueError("A named detector callable is required")
    observed = Counter()
    per_domain = {}
    misses = []
    flagged_controls = []
    results = []
    for case in corpus["cases"]:
        result = detector(case["source"], case["candidate"])
        if (not isinstance(result, dict)
                or result.get("verdict") not in ("REFUSE", "INCONCLUSIVE")
                or result.get("qualityrag_admission") != "INCONCLUSIVE"
                or result.get("can_generate") is not False
                or result.get("source_sha256") != sha256(
                    case["source"].encode()).hexdigest()
                or result.get("candidate_sha256") != sha256(
                    case["candidate"].encode()).hexdigest()):
            raise ValueError("Detector result fails source-version or admission contract")
        domain = case["domain"]
        by = per_domain.setdefault(domain, Counter())
        predicted = result["verdict"]
        label = case["label"]
        if label == "DRIFT":
            metric = "consequential_detected" if predicted == "REFUSE" else "consequential_abstained"
            if predicted != "REFUSE":
                misses.append(case["id"])
        else:
            metric = "control_flagged" if predicted == "REFUSE" else "control_abstained"
            if predicted == "REFUSE":
                flagged_controls.append(case["id"])
        observed[metric] += 1
        by[metric] += 1
        results.append({
            "case_id": case["id"], "domain": domain, "label": label,
            "detector_verdict": predicted, "outcome": metric,
            "source_sha256": result["source_sha256"],
            "candidate_sha256": result["candidate_sha256"],
        })
    positive = observed["consequential_detected"] + observed["consequential_abstained"]
    controls = observed["control_flagged"] + observed["control_abstained"]
    total = positive + controls
    assert total == len(corpus["cases"])
    report = {
        "schema": SCHEMA,
        "detector_id": detector_id,
        "corpus_sha256": digest(corpus),
        "cases": total,
        "consequential_cases": positive,
        "control_cases": controls,
        "counts": {
            k: observed[k] for k in (
                "consequential_detected", "consequential_abstained",
                "control_flagged", "control_abstained")
        },
        "consequential_detection_rate_lower_bound": _rate(
            observed["consequential_detected"], positive),
        "consequential_abstention_rate": _rate(
            observed["consequential_abstained"], positive),
        "control_flag_rate": _rate(observed["control_flagged"], controls),
        "control_abstention_rate": _rate(observed["control_abstained"], controls),
        "consequential_detection_wilson_95": _wilson_95(
            observed["consequential_detected"], positive),
        "control_flag_wilson_95": _wilson_95(
            observed["control_flagged"], controls),
        "cases_not_detected": sorted(misses),
        "controls_flagged": sorted(flagged_controls),
        "domain_counts": {
            domain: {name: counts[name] for name in (
                "consequential_detected", "consequential_abstained",
                "control_flagged", "control_abstained")}
            for domain, counts in sorted(per_domain.items())
        },
        "case_outcomes": results,
        "critical_limits": [
            "Labels are curated examples, not independently authenticated standards",
            "INCONCLUSIVE is abstention; it is not a true negative or safe admission",
            "Lower-bound drift detection treats every inconclusive consequential case as missed",
            "Wilson intervals describe finite counts only; cases are not random population samples",
            "No semantic completeness or production false-negative-rate bound follows",
            "No generator is invoked and no successful test authorizes semantic ADMIT",
        ],
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
    }
    report["fingerprint"] = digest(report)
    return report


def lexical_change_baseline(before: str, after: str) -> dict:
    """Deliberately naive high-recall comparator for measuring false alarms."""
    return {
        "verdict": "REFUSE" if before != after else "INCONCLUSIVE",
        "source_sha256": sha256(before.encode()).hexdigest(),
        "candidate_sha256": sha256(after.encode()).hexdigest(),
        "qualityrag_admission": "INCONCLUSIVE",
        "can_generate": False,
    }


def evaluate_native_corpus(corpus: dict, *, apx_packages_root: str) -> dict:
    """Actually run the canonical native host. Missing APX is a hard failure."""
    from rct_native_semantic_host import inspect_native_semantics
    return evaluate_corpus(
        corpus,
        lambda before, after: inspect_native_semantics(
            before, after, apx_packages_root=apx_packages_root),
        detector_id="ORIGINAL_APX_NATIVE_SEMANTIC_SOURCE_COMPARATOR")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(
        Path(__file__).resolve().parent / "data" / "semantic_adversarial_v1.json"))
    parser.add_argument("--native-root", default=None,
                        help="Absolute path to separately built original private APX packages")
    args = parser.parse_args()
    dataset = load_corpus(args.corpus)
    result = (evaluate_native_corpus(dataset, apx_packages_root=args.native_root)
              if args.native_root else
              evaluate_corpus(dataset, lexical_change_baseline,
                              detector_id="TEXT_INEQUALITY_BASELINE"))
    print(json.dumps(result, indent=2, sort_keys=True))
