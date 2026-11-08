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
a gold answer). Baselines: no gate (always answer), an oracle labeler, and - with
--llm - a plain LLM told to answer from the passages or say it cannot ("self-abstain",
no gate). The question that matters is whether gate + LLM labeler beats self-abstain.

Data: SQuAD 2.0 dev set (CC BY-SA 4.0), downloaded on first run and cached; it is
not committed to this repository.

    PYTHONPATH=sdk/python python examples/squad2-gate/run_benchmark.py --n 500
    PYTHONPATH=sdk/python python examples/squad2-gate/run_benchmark.py --n 200 --llm   # ANTHROPIC_API_KEY

LLM responses are cached on disk (keyed by model and prompt), so reruns are free and
reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
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
    counts = _new_counts()
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
        _record(counts, item, positive, admitted)
        if positive and admitted and any(t["status"] == "SUPPORTS" and contains_answer(t["quote"], item["answers"])
                                         for t in result["label_trace"]):
            counts["span_hits"] += 1
    return summarize(labeler.name, counts)


SELF_ABSTAIN_PROMPT = (
    "Answer the question using only the passages below. If the passages do not contain the "
    "answer, reply with UNANSWERABLE.\n\nQuestion: {question}\n\nPassages:\n{passages}\n\n"
    'Respond with JSON only: {{"answer": "<short answer copied from the passages, or UNANSWERABLE>"}}'
)
_ABSTAIN = {"", "unanswerable", "unknown", "none", "n/a"}


def _parse_answer(raw: str) -> str:
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        value = json.loads(m.group(0)).get("answer", "") if m else ""
    except (json.JSONDecodeError, AttributeError):
        value = ""
    return value.strip() if isinstance(value, str) else ""


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def answer_matches(answer: str, gold: list[str]) -> bool:
    a = _norm(answer)
    return bool(a) and any(g and (g in a or a in g) for g in map(_norm, gold))


def self_abstain(items: list[dict], k: int, complete) -> dict:
    """No gate: the model itself decides to answer or abstain. Errors count as abstentions."""
    c = _new_counts()
    for item in items:
        idx = retrieve(item["question"], item["paragraphs"], k)
        texts = [item["paragraphs"][i] for i in idx]
        positive = (not item["is_impossible"]) and any(contains_answer(t, item["answers"]) for t in texts)
        prompt = SELF_ABSTAIN_PROMPT.format(question=item["question"],
                                            passages="\n\n".join(f"[{n+1}] {t}" for n, t in enumerate(texts)))
        try:
            answer = _parse_answer(complete(prompt))
        except Exception:
            answer = ""
        admitted = answer.lower().strip(" .") not in _ABSTAIN
        _record(c, item, positive, admitted)
        if positive and admitted and answer_matches(answer, item["answers"]):
            c["answer_matches"] += 1
    out = summarize("llm-self-abstain (no gate)", c)
    out["span_hit_rate"] = None
    return out


class CachedCompleter:
    """Disk cache for ``complete(prompt)``: one JSON line per (tag, prompt) hash."""

    def __init__(self, complete, path: Path, tag: str):
        self.complete, self.path, self.tag = complete, Path(path), tag
        self.hits = self.misses = 0
        self._cache: dict[str, str] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                try:
                    row = json.loads(line)
                    self._cache[row["key"]] = row["response"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

    def __call__(self, prompt: str) -> str:
        key = hashlib.sha256(f"{self.tag}\0{prompt}".encode()).hexdigest()
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        response = self.complete(prompt)  # exceptions propagate and are not cached
        self.misses += 1
        self._cache[key] = response
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({"key": key, "tag": self.tag, "response": response}) + "\n")
        return response


def _new_counts() -> dict:
    return {"pos": 0, "pos_admit": 0, "neg_impossible": 0, "neg_impossible_admit": 0,
            "neg_retrieval_miss": 0, "neg_retrieval_miss_admit": 0, "span_hits": 0, "answer_matches": 0}


def _record(c: dict, item: dict, positive: bool, admitted: bool) -> None:
    if positive:
        c["pos"] += 1
        c["pos_admit"] += int(admitted)
    else:
        bucket = "neg_impossible" if item["is_impossible"] else "neg_retrieval_miss"
        c[bucket] += 1
        c[bucket + "_admit"] += int(admitted)


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
        "answer_match_rate": rate(c["answer_matches"], c["pos_admit"]) if c["answer_matches"] else None,
        "counts": c,
    }


def no_gate(items: list[dict], k: int) -> dict:
    c = _new_counts()
    for item in items:
        idx = retrieve(item["question"], item["paragraphs"], k)
        positive = (not item["is_impossible"]) and any(contains_answer(item["paragraphs"][i], item["answers"]) for i in idx)
        _record(c, item, positive, True)
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
            "false_admission_rate_retrieval_miss", "admit_precision", "span_hit_rate", "answer_match_rate"]
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    fmt = lambda v: "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    return head + "".join("| " + " | ".join(fmt(r[c]) for c in cols) + " |\n" for r in rows)


def run(squad: dict, n: int, seed: int, k: int, thresholds, llm_complete=None) -> dict:
    items = sample(squad, n, seed)
    rows = [no_gate(items, k), evaluate_labeler(items, OracleLabeler(), k)]
    rows += [evaluate_labeler(items, LexicalLabeler(t), k) for t in thresholds]
    if llm_complete is not None:
        rows.append(evaluate_labeler(items, LLMLabeler(llm_complete, name="gate + llm labeler"), k))
        rows.append(self_abstain(items, k, llm_complete))
    return {"n": len(items), "seed": seed, "k": k, "rows": rows}


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="SQuAD 2.0 false-admission benchmark for the QualityRag gate")
    ap.add_argument("--data", type=Path, help="path to dev-v2.0.json (downloaded and cached if omitted)")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--k", type=int, default=1, help="paragraphs retrieved per question")
    ap.add_argument("--thresholds", type=float, nargs="+", default=[0.4, 0.6, 0.8, 1.0])
    ap.add_argument("--llm", action="store_true",
                    help="add gate + LLM labeler and the self-abstain LLM baseline (needs anthropic + ANTHROPIC_API_KEY)")
    ap.add_argument("--model", default=os.environ.get("QUALITYRAG_LLM_MODEL", "claude-sonnet-5-5"))
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE.with_name("llm-cache.jsonl"),
                    help="LLM response cache (JSON lines)")
    ap.add_argument("--json", type=Path, help="write the full report here")
    args = ap.parse_args(argv)
    squad, digest = load_squad(args.data)
    llm = CachedCompleter(anthropic_completer(model=args.model), args.cache, args.model) if args.llm else None
    report = run(squad, args.n, args.seed, args.k, args.thresholds, llm)
    if llm is not None:
        report["llm"] = {"model": args.model, "cache": str(args.cache), "cache_hits": llm.hits, "api_calls": llm.misses}
    report["dataset"] = {"name": "SQuAD 2.0 dev", "sha256": digest, "license": "CC BY-SA 4.0"}
    print(f"SQuAD 2.0 dev sha256={digest[:12]} n={report['n']} seed={args.seed} k={args.k}\n")
    print(render(report["rows"]))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
