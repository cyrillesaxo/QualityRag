"""False-admission benchmark for the QualityRag gate on SQuAD 2.0.

Pipeline per question: retrieve top-k paragraphs from the question's article
(lexical ranking) -> label each paragraph for "contains the answer" -> gate
with one requirement -> ADMIT (answer) or not (abstain).

Ground truth is about the *retrieved context*, which is what the gate sees:

* positive  - the question is answerable and a gold answer string appears in a retrieved paragraph
* negative  - the question is unanswerable (SQuAD 2.0 adversarial "impossible" questions),
              or answerable but retrieval missed every paragraph containing the answer

Reported per labeler: answer rate on positives, false-admission rate on negatives
(split by cause), admit precision, and span hit rate (admitted spans that contain
a gold answer). Baselines: no gate (always answer) and an oracle labeler.

Data: SQuAD 2.0 dev set (CC BY-SA 4.0), downloaded on first run and cached; it is
not committed to this repository.

    PYTHONPATH=sdk/python python examples/squad2-gate/run_benchmark.py --n 500
    PYTHONPATH=sdk/python python examples/squad2-gate/run_benchmark.py --n 200 --llm   # ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import urllib.request
from pathlib import Path

from qualityrag.labeling import (Label, LexicalLabeler, LLMLabeler, Requirement, anthropic_completer,
                                 assess, content_terms)

SQUAD_URL = "https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/dataset/dev-v2.0.json"
DEFAULT_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "qualityrag" / "squad-dev-v2.0.json"
AS_OF = "2026-01-01T00:00:00Z"
PACK = {"id": "squad2-answer-present", "version": "1.0",
        "requirements": [{"id": "answer-present", "min_independent_sources": 1}]}


def load_squad(path: Path | None, download: bool = True) -> tuple[dict, str]:
    path = path or DEFAULT_CACHE
    if not path.exists():
        if not download:
            raise FileNotFoundError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {SQUAD_URL} -> {path}", file=sys.stderr)
        with urllib.request.urlopen(SQUAD_URL, timeout=60) as r:
            path.write_bytes(r.read())
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def questions(squad: dict):
    for article in squad["data"]:
        paragraphs = [p["context"] for p in article["paragraphs"]]
        for pi, p in enumerate(article["paragraphs"]):
            for qa in p["qas"]:
                yield {"id": qa["id"], "question": qa["question"], "title": article["title"],
                       "paragraphs": paragraphs, "gold_paragraph": pi,
                       "answers": sorted({a["text"] for a in qa.get("answers", [])}),
                       "is_impossible": bool(qa.get("is_impossible"))}


def retrieve(question: str, paragraphs: list[str], k: int) -> list[int]:
    q = content_terms(question)
    scored = [(len(q & content_terms(p)), -i) for i, p in enumerate(paragraphs)]
    return [-i for s, i in sorted(scored, reverse=True)[:k]]


def contains_answer(text: str, answers: list[str]) -> bool:
    low = text.lower()
    return any(a.lower() in low for a in answers)


class OracleLabeler:
    """Labels SUPPORTS exactly when a gold answer is in the passage. Upper bound, not a method."""
    name = "oracle"

    def __init__(self):
        self.answers: list[str] = []

    def label(self, requirement: Requirement, passage: str) -> Label:
        for a in self.answers:
            i = passage.lower().find(a.lower())
            if i >= 0:
                return Label("SUPPORTS", (i, i + len(a)), passage[i:i + len(a)], 1.0, self.name)
        return Label("UNKNOWN", labeler=self.name)


def evaluate_labeler(items: list[dict], labeler, k: int) -> dict:
    counts = {"pos": 0, "pos_admit": 0, "neg_impossible": 0, "neg_impossible_admit": 0,
              "neg_retrieval_miss": 0, "neg_retrieval_miss_admit": 0, "span_hits": 0}
    for item in items:
        idx = retrieve(item["question"], item["paragraphs"], k)
        passages = [{"id": f"{item['id']}#p{i}", "text": item["paragraphs"][i], "origin": item["title"],
                     "source_ref": f"squad:{item['title']}#{i}"} for i in idx]
        positive = (not item["is_impossible"]) and any(contains_answer(p["text"], item["answers"]) for p in passages)
        if isinstance(labeler, OracleLabeler):
            labeler.answers = item["answers"] if not item["is_impossible"] else []
        claims = {"answer-present": {"text": item["question"], "kind": "question"}}
        result = assess(PACK, claims, passages, labeler, as_of=AS_OF)
        admitted = result["verdict"] == "ADMIT"
        if positive:
            counts["pos"] += 1
            if admitted:
                counts["pos_admit"] += 1
                if any(t["status"] == "SUPPORTS" and contains_answer(t["quote"], item["answers"])
                       for t in result["label_trace"]):
                    counts["span_hits"] += 1
        else:
            bucket = "neg_impossible" if item["is_impossible"] else "neg_retrieval_miss"
            counts[bucket] += 1
            counts[bucket + "_admit"] += int(admitted)
    return summarize(labeler.name, counts)


def summarize(name: str, c: dict) -> dict:
    neg = c["neg_impossible"] + c["neg_retrieval_miss"]
    neg_admit = c["neg_impossible_admit"] + c["neg_retrieval_miss_admit"]
    rate = lambda a, b: round(a / b, 4) if b else None
    return {
        "labeler": name,
        "positives": c["pos"], "negatives": neg,
        "answer_rate": rate(c["pos_admit"], c["pos"]),
        "false_admission_rate": rate(neg_admit, neg),
        "false_admission_rate_impossible": rate(c["neg_impossible_admit"], c["neg_impossible"]),
        "false_admission_rate_retrieval_miss": rate(c["neg_retrieval_miss_admit"], c["neg_retrieval_miss"]),
        "admit_precision": rate(c["pos_admit"], c["pos_admit"] + neg_admit),
        "span_hit_rate": rate(c["span_hits"], c["pos_admit"]),
        "counts": c,
    }


def no_gate(items: list[dict], k: int) -> dict:
    c = {"pos": 0, "pos_admit": 0, "neg_impossible": 0, "neg_impossible_admit": 0,
         "neg_retrieval_miss": 0, "neg_retrieval_miss_admit": 0, "span_hits": 0}
    for item in items:
        idx = retrieve(item["question"], item["paragraphs"], k)
        positive = (not item["is_impossible"]) and any(contains_answer(item["paragraphs"][i], item["answers"]) for i in idx)
        if positive:
            c["pos"] += 1; c["pos_admit"] += 1
        else:
            b = "neg_impossible" if item["is_impossible"] else "neg_retrieval_miss"
            c[b] += 1; c[b + "_admit"] += 1
    out = summarize("no-gate", c)
    out["span_hit_rate"] = None
    return out


def sample(squad: dict, n: int, seed: int) -> list[dict]:
    allq = list(questions(squad))
    rng = random.Random(seed)
    rng.shuffle(allq)
    return allq[:n]


def render(rows: list[dict]) -> str:
    cols = ["labeler", "answer_rate", "false_admission_rate", "false_admission_rate_impossible",
            "false_admission_rate_retrieval_miss", "admit_precision", "span_hit_rate"]
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    fmt = lambda v: "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    return head + "".join("| " + " | ".join(fmt(r[c]) for c in cols) + " |\n" for r in rows)


def run(squad: dict, n: int, seed: int, k: int, thresholds, llm_complete=None) -> dict:
    items = sample(squad, n, seed)
    rows = [no_gate(items, k), evaluate_labeler(items, OracleLabeler(), k)]
    rows += [evaluate_labeler(items, LexicalLabeler(t), k) for t in thresholds]
    if llm_complete is not None:
        rows.append(evaluate_labeler(items, LLMLabeler(llm_complete, name="llm"), k))
    return {"n": len(items), "seed": seed, "k": k, "rows": rows}


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="SQuAD 2.0 false-admission benchmark for the QualityRag gate")
    ap.add_argument("--data", type=Path, help="path to dev-v2.0.json (downloaded and cached if omitted)")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--k", type=int, default=1, help="paragraphs retrieved per question")
    ap.add_argument("--thresholds", type=float, nargs="+", default=[0.4, 0.6, 0.8, 1.0])
    ap.add_argument("--llm", action="store_true", help="add the LLM labeler (needs anthropic + ANTHROPIC_API_KEY)")
    ap.add_argument("--json", type=Path, help="write the full report here")
    args = ap.parse_args(argv)
    squad, digest = load_squad(args.data)
    report = run(squad, args.n, args.seed, args.k, args.thresholds,
                 anthropic_completer() if args.llm else None)
    report["dataset"] = {"name": "SQuAD 2.0 dev", "sha256": digest, "license": "CC BY-SA 4.0"}
    print(f"SQuAD 2.0 dev sha256={digest[:12]} n={report['n']} seed={args.seed} k={args.k}\n")
    print(render(report["rows"]))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
