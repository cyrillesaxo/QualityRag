"""Policy tester, governance advisor and policy-branch replay for the QualityRag gate.

All three sit on the v0.1 deterministic gate (``qualityrag.compiler.evaluate_compiled``) and
add nothing to its verdict. The tester explains which spans the gate counted. The advisor
lists conditions the gate does not check (qualifiers inside SUPPORTS spans, single-origin
requirements, an empty reviewer trust store, calibration). Replay compares two packs over
recorded cases. ADMIT remains metadata gate satisfaction, not authorization to act.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SDK = str(ROOT / "sdk" / "python")
if SDK not in sys.path:
    sys.path.insert(0, SDK)

from qualityrag.compiler import compile_pack, evaluate_compiled  # noqa: E402

EXAMPLE = ROOT / "examples" / "enterprise-rag" / "corpus.json"
TRUST = Path(__file__).with_name("reviewer-trust.json")
ADMIT_NOTE = ("ADMIT is metadata gate satisfaction, not authorization to act. Qualifiers inside "
              "supporting spans and source authenticity are not evaluated by the gate.")

# Words that make a supporting span conditional or limited. The gate counts the span anyway.
QUALIFIERS = {
    "condition": ["unless", "except", "excluding", "provided that", "subject to", "conditional on",
                  "if and only if", "only if", "as long as"],
    "limit": ["only"],
    "negation": ["not", "never", "no longer", "without"],
}
_QUALIFIER_RE = [(kind, word, re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE))
                 for kind, words in QUALIFIERS.items() for word in words]
SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}
LIMITS = {"documents": 500, "chunks": 5000, "text": 20000, "cases": 5000, "witnesses": 200}


def qualifiers(text: str) -> list[dict]:
    """Qualifier words in a span, longest match first, non-overlapping, in text order."""
    hits = []
    for kind, word, pattern in sorted(_QUALIFIER_RE, key=lambda x: -len(x[1])):
        for m in pattern.finditer(text):
            if not any(m.start() < h["end"] and h["start"] < m.end() for h in hits):
                hits.append({"kind": kind, "word": text[m.start():m.end()], "start": m.start(), "end": m.end()})
    return sorted(hits, key=lambda h: h["start"])


def _string(value, name, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _chunks(documents):
    if not isinstance(documents, list) or not 0 < len(documents) <= LIMITS["documents"]:
        raise ValueError("documents must be a nonempty list")
    out, total = {}, 0
    for doc in documents:
        if not isinstance(doc, dict) or not isinstance(doc.get("chunks"), list):
            raise ValueError("each document needs chunks")
        _string(doc.get("id"), "document id", 200)
        _string(doc.get("origin"), "document origin", 200)
        for chunk in doc["chunks"]:
            total += 1
            if total > LIMITS["chunks"] or not isinstance(chunk, dict):
                raise ValueError("chunk limit")
            cid = _string(chunk.get("id"), "chunk id", 200)
            if cid in out:
                raise ValueError("duplicate chunk id")
            _string(chunk.get("text"), "chunk text", LIMITS["text"])
            out[cid] = (doc, chunk)
    return out


def policy_test(pack: dict, documents: list, retrieved: list, *, as_of: str, question: str | None = None) -> dict:
    """Run the gate on the retrieved chunks and explain every counted and uncounted span."""
    compile_pack(pack)
    chunks = _chunks(documents)
    if not isinstance(retrieved, list) or not retrieved or len(retrieved) > LIMITS["chunks"]:
        raise ValueError("retrieved must be a nonempty list of chunk ids")
    unknown = [c for c in retrieved if c not in chunks]
    if unknown:
        raise ValueError("retrieved names unknown chunks")
    order = list(dict.fromkeys(retrieved))
    witnesses, unlinked = [], []
    for cid in order:
        doc, chunk = chunks[cid]
        if not chunk.get("requirement_id") or not chunk.get("status"):
            unlinked.append({"chunk_id": cid, "document": doc["id"], "origin": doc["origin"], "text": chunk["text"],
                             "revision": doc.get("revision"), "reason": "No requirement link or status: not counted"})
            continue
        witnesses.append({"id": cid, "requirement_id": chunk["requirement_id"], "origin": doc["origin"],
                          "source_ref": doc["id"] + "#" + cid, "status": chunk["status"],
                          "observed_at": chunk.get("observed_at") or doc.get("observed_at") or as_of,
                          **({"scope": chunk["scope"]} if "scope" in chunk else {}),
                          **({"authority": chunk["authority"]} if "authority" in chunk else {})})
    result = evaluate_compiled(pack, witnesses, as_of=as_of)
    minimum = {o["requirement_id"]: o["min_origins"] for o in result["constraint_ir"]}
    by_req = {}
    for w in witnesses:
        by_req.setdefault(w["requirement_id"], []).append(w)
    requirements = []
    for finding in result["findings"]:
        rid = finding["requirement_id"]
        seen_origin, spans = {}, []
        for w in by_req.get(rid, []):
            doc, chunk = chunks[w["id"]]
            # Exact per-span answer from the gate itself: does this span alone add an origin?
            alone = evaluate_compiled(pack, [w], as_of=as_of)["findings"]
            counted = next(f for f in alone if f["requirement_id"] == rid)["independent_sources"] == 1
            first = seen_origin.setdefault(w["origin"], w["id"]) if counted else None
            spans.append({
                "chunk_id": w["id"], "document": doc["id"], "origin": w["origin"], "status": w["status"],
                "format": doc.get("format"), "revision": doc.get("revision"), "section": chunk.get("section"),
                "text": chunk["text"], "qualifiers": qualifiers(chunk["text"]) if w["status"] == "SUPPORTS" else [],
                "counts_as_origin": bool(counted and first == w["id"]),
                "same_origin_as": first if counted and first != w["id"] else None,
            })
        requirements.append({
            "requirement_id": rid, "verdict": finding["verdict"], "reasons": finding["reasons"],
            "min_independent_sources": minimum[rid], "independent_sources": finding["independent_sources"],
            "missing_sources": finding["missing_sources"], "spans": spans,
            "qualified": any(s["qualifiers"] for s in spans if s["status"] == "SUPPORTS"),
        })
    return {
        "schema": "qualityrag.policy-test/v0.1", "question": question, "as_of": as_of,
        "pack_id": pack["id"], "pack_version": pack["version"], "verdict": result["verdict"],
        "requirements": requirements, "unlinked": unlinked,
        "dependent_groups": result["witness_graph"]["dependent_groups"],
        "summary": {
            "retrieved": len(order), "counted_witnesses": len(witnesses), "unlinked": len(unlinked),
            "documents": len({chunks[c][0]["id"] for c in order}),
            "origins": len({chunks[c][0]["origin"] for c in order}),
            "qualified_requirements": sum(r["qualified"] and r["verdict"] == "ADMIT" for r in requirements),
            "single_origin_requirements": sum(r["verdict"] == "ADMIT" and r["independent_sources"] == 1 for r in requirements),
        },
        "evaluated": "Finite metadata conditions only: requirement links, status, distinct origins, age, scope, authority.",
        "note": ADMIT_NOTE,
    }


def _finding(fid, severity, area, title, where, checked, fix, code):
    return {"id": fid, "severity": severity, "area": area, "title": title, "where": where,
            "checked": checked, "fix": fix, "code": code}


def advise(*, trust_path: Path = TRUST, pack: dict | None = None, test: dict | None = None,
           garden: dict | None = None, benchmark: dict | None = None, far_limit: float = 0.10) -> dict:
    """Governance findings. Suggestions only: none of them changes a verdict or the ledger."""
    findings = []
    from .audit import load_trust
    try:
        trust = load_trust(trust_path)
        active = [k for k, v in trust.items() if v["status"] == "active"]
        compromised = sorted(k for k, v in trust.items() if v["status"] == "compromised")
        if not active:
            findings.append(_finding(
                "trust.no-active-reviewer", "ERROR", "trust",
                "No active reviewer keys: signed completion receipts cannot verify", trust_path.name,
                f"{trust_path.name} lists {len(trust)} reviewer key(s), {len(active)} active. audit.py verifies every "
                "Ed25519 completion receipt against active keys, so every receipt fails closed and stories stay IN_REVIEW.",
                "Generate a reviewer key pair, add the public key with its GitHub login and valid_from, and commit the change for review.",
                "python -m tools.activation_runtime.story_completion pubkey --key reviewer.key \\\n"
                "  --key-id <key-id> --github-login <login> --valid-from <YYYY-MM-DDTHH:MM:SSZ>\n"
                "# add the key to tools/activation_runtime/reviewer-trust.json\npython -m tools.activation_runtime.audit"))
        if compromised:
            findings.append(_finding(
                "trust.compromised", "WARN", "trust", f"{len(compromised)} compromised key(s) still listed", trust_path.name,
                "Keys marked compromised invalidate every receipt they signed: " + ", ".join(compromised) + ".",
                "Re-review the stories those keys signed and attach receipts from an active key.",
                "python -m tools.activation_runtime.audit"))
    except (OSError, ValueError) as exc:
        findings.append(_finding("trust.unreadable", "ERROR", "trust", "Reviewer trust store is unreadable", trust_path.name,
                                 "load_trust refused the file: " + str(exc)[:200] + ".",
                                 "Fix the file so it matches qualityrag.reviewer-trust/v1.", "python -m tools.activation_runtime.audit"))

    if pack is not None:
        obligations = compile_pack(pack)
        tested = {r["requirement_id"]: r for r in (test or {}).get("requirements", [])}
        groups = {}
        for g in (test or {}).get("dependent_groups", []):
            groups.setdefault(g["requirement_id"], []).append(g)
        name = f"{pack['id']}@{pack['version']}"
        single = [o for o in obligations if o.min_origins == 1]
        if single:
            copies = [g for o in single for g in groups.get(o.requirement_id, [])]
            detail = ""
            if copies:
                detail = " In the last test, " + "; ".join(
                    f"{' and '.join(g['witness_ids'])} for {g['requirement_id']} resolve to the same origin, "
                    f"{g['origin']}, and were counted once" for g in copies) + "."
            ids = [o.requirement_id for o in single]
            findings.append(_finding(
                "pack.single-origin", "WARN", "independence",
                f"{len(ids)} requirement(s) can be admitted on a single origin", name,
                "min_independent_sources is 1 for " + ", ".join(ids) + ", so one source and every copy of it "
                f"satisfies each.{detail}",
                "Raise min_independent_sources to 2 where an independent source exists, or record why one "
                "authoritative origin is enough. Replay the change before promoting it.",
                "\n".join(f'{{"id": "{i}", "min_independent_sources": 2}}' for i in ids)))
        ageless = [o.requirement_id for o in obligations if o.max_age_seconds is None]
        if ageless:
            findings.append(_finding(
                "pack.no-max-age", "INFO", "freshness", f"{len(ageless)} requirement(s) accept evidence of any age", name,
                "max_age_seconds is not set for " + ", ".join(ageless) + ", so stale or superseded documents still count.",
                "Set max_age_seconds to the period after which this evidence must be re-checked.",
                "\n".join(f'{{"id": "{i}", "max_age_seconds": 31536000}}' for i in ageless)))
        qualified = []
        for r in tested.values():
            if r["verdict"] != "ADMIT":
                continue
            for s in r["spans"]:
                if s["status"] == "SUPPORTS" and s["qualifiers"]:
                    words = ", ".join(f"“{q['word']}”" for q in s["qualifiers"])
                    qualified.append(f"{s['chunk_id']} ({r['requirement_id']}): {words}")
        if qualified:
            findings.append(_finding(
                "evidence.qualified-support", "WARN", "semantics",
                f"{len(qualified)} supporting span(s) admitted with a qualifier", name,
                "The gate counts SUPPORTS spans without evaluating conditions inside them. " + "; ".join(qualified) + ".",
                "Add a requirement for the condition itself (for example a recorded approval reference), "
                "so the exception path must be evidenced and not just mentioned.",
                '{"id": "approval-reference-recorded", "min_independent_sources": 1}'))

    if benchmark is not None:
        far, rate, n = benchmark.get("false_admission_rate"), benchmark.get("answer_rate"), benchmark.get("n")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (far, rate, n)) or not (0 <= far <= 1 and 0 <= rate <= 1):
            raise ValueError("benchmark needs numeric false_admission_rate, answer_rate and n")
        labeler = str(benchmark.get("labeler", "labeler"))[:80]
        dataset = str(benchmark.get("dataset", "benchmark"))[:120]
        if far > far_limit:
            findings.append(_finding(
                "calibration.false-admission", "ERROR", "calibration",
                f"{labeler} admits {far:.1%} of unanswerable questions", f"{dataset} · n={int(n)}",
                f"False-admission rate {far:.1%} exceeds the {far_limit:.0%} limit; answer rate {rate:.1%}.",
                "Replay a stricter policy branch and compare the trade-off, or benchmark the LLM labeler.",
                "python examples/squad2-gate/run_benchmark.py --n 1000 --seed 0 --thresholds 0.6 0.8\n"
                "python examples/squad2-gate/run_benchmark.py --n 1000 --seed 0 --llm"))

    for branch, info in sorted(((garden or {}).get("branches") or {}).items()):
        events = [garden["events"][e] for e in info.get("events", []) if e in garden.get("events", {})]
        last_challenge = max((i for i, e in enumerate(events) if e["operation"] == "CHALLENGE"), default=None)
        if info.get("active", True) and last_challenge is not None and not any(
                e["operation"] == "TEST" for e in events[last_challenge + 1:]):
            findings.append(_finding(
                f"gardener.open-challenge.{branch}", "INFO", "gardener", f"Open challenge on {branch}", "Semantic Gardener",
                "Challenge: " + events[last_challenge]["statement"][:300] + " No TEST has followed it.",
                "Run the experiment the challenge asks for and record a TEST citing its ledger evidence.",
                f"python -m tools.activation_runtime.cli garden query --open-challenge --lineage-of {branch}"))

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["id"]))
    counts = {s: sum(f["severity"] == s for f in findings) for s in SEVERITY_ORDER}
    return {"schema": "qualityrag.advisor/v0.1", "findings": findings, "counts": counts,
            "blocks_promotion": counts["ERROR"] > 0,
            "note": "Findings are suggestions, not decisions. None changes a verdict, the ledger or the Gardener."}


def _pack_diff(base, branch):
    a = {r["id"]: r for r in base["requirements"]}
    b = {r["id"]: r for r in branch["requirements"]}
    changes = []
    for rid in sorted(set(a) | set(b)):
        if rid not in b:
            changes.append({"requirement_id": rid, "change": "removed"})
        elif rid not in a:
            changes.append({"requirement_id": rid, "change": "added", "to": b[rid]})
        else:
            for key in sorted(set(a[rid]) | set(b[rid])):
                if a[rid].get(key) != b[rid].get(key):
                    changes.append({"requirement_id": rid, "change": "modified", "field": key,
                                    "from": a[rid].get(key), "to": b[rid].get(key)})
    return changes


def replay(base: dict, branch: dict, cases: list, *, as_of: str) -> dict:
    """Evaluate the same recorded cases under two packs and report every verdict that changed.

    A case is {"id", "evidence": [witness rows], "expect_admit": true|false (optional)}. Rates
    use only labeled cases: answer rate over expect_admit=true, false-admission rate over false.
    """
    compile_pack(base)
    compile_pack(branch)
    if not isinstance(cases, list) or not 0 < len(cases) <= LIMITS["cases"]:
        raise ValueError("cases must be a nonempty list")
    ids, flips = set(), []
    tally = {"base": {"admit": 0}, "branch": {"admit": 0}}
    labeled = {True: 0, False: 0}
    hits = {side: {True: 0, False: 0} for side in ("base", "branch")}
    effects = {"false_admission_removed": 0, "correct_answer_lost": 0, "false_admission_added": 0,
               "correct_answer_gained": 0, "unlabeled": 0}
    for case in cases:
        if not isinstance(case, dict) or not set(case) <= {"id", "evidence", "expect_admit", "question"}:
            raise ValueError("case needs id, evidence and optional expect_admit and question")
        cid = _string(case.get("id"), "case id", 200)
        if cid in ids:
            raise ValueError("duplicate case id")
        ids.add(cid)
        evidence = case.get("evidence")
        if not isinstance(evidence, list) or len(evidence) > LIMITS["witnesses"]:
            raise ValueError("case evidence must be a list")
        label = case.get("expect_admit")
        if label is not None and not isinstance(label, bool):
            raise ValueError("expect_admit must be true, false or absent")
        verdicts = {side: evaluate_compiled(pack, copy.deepcopy(evidence), as_of=as_of)["verdict"]
                    for side, pack in (("base", base), ("branch", branch))}
        for side, verdict in verdicts.items():
            admitted = verdict == "ADMIT"
            tally[side]["admit"] += admitted
            if label is not None:
                hits[side][label] += admitted
        if label is not None:
            labeled[label] += 1
        if verdicts["base"] != verdicts["branch"]:
            was, now = verdicts["base"] == "ADMIT", verdicts["branch"] == "ADMIT"
            if was == now or label is None:
                effect = "unlabeled" if label is None else "verdict_changed"
            elif was and not label:
                effect = "false_admission_removed"
            elif was and label:
                effect = "correct_answer_lost"
            elif not label:
                effect = "false_admission_added"
            else:
                effect = "correct_answer_gained"
            if effect in effects:
                effects[effect] += 1
            flips.append({"id": cid, "question": case.get("question"), "from": verdicts["base"],
                          "to": verdicts["branch"], "expect_admit": label, "effect": effect})

    def rates(side):
        return {"answer_rate": hits[side][True] / labeled[True] if labeled[True] else None,
                "false_admission_rate": hits[side][False] / labeled[False] if labeled[False] else None}

    return {
        "schema": "qualityrag.policy-replay/v0.1", "as_of": as_of, "cases": len(cases),
        "labeled": {"expect_admit": labeled[True], "expect_refusal": labeled[False]},
        "base": {"pack": f"{base['id']}@{base['version']}", **tally["base"], **rates("base")},
        "branch": {"pack": f"{branch['id']}@{branch['version']}", **tally["branch"], **rates("branch")},
        "pack_diff": _pack_diff(base, branch), "flipped": len(flips), "effects": effects, "flips": flips[:1000],
        "note": "Replay re-evaluates recorded evidence; it does not re-run retrieval or labeling. Promotion is a separate signed review.",
    }


def example() -> dict:
    """The enterprise-rag EU payments scenario, with a stricter branch and its two recorded retrievals."""
    data = json.loads(EXAMPLE.read_text())
    branch = copy.deepcopy(data["pack"])
    branch["version"] = "1.1-two-origins"
    for r in branch["requirements"]:
        if r["id"] == "recovery-procedure":
            r["min_independent_sources"] = 2
    chunks = _chunks(data["documents"])
    observed = "2026-11-02T10:00:00Z"

    def evidence(ids):
        rows = []
        for cid in ids:
            doc, chunk = chunks[cid]
            if chunk.get("requirement_id") and chunk.get("status"):
                rows.append({"id": cid, "requirement_id": chunk["requirement_id"], "origin": doc["origin"],
                             "source_ref": doc["id"] + "#" + cid, "status": chunk["status"], "observed_at": observed})
        return rows

    first, second = data["retrieval"]["initial"], data["retrieval"]["targeted"]
    return {
        "question": data["question"], "pack": data["pack"], "branch_pack": branch, "documents": data["documents"],
        "retrieved": first + second, "as_of": "2026-11-02T10:05:00Z",
        "cases": [{"id": "initial-retrieval", "question": data["question"], "evidence": evidence(first)},
                  {"id": "targeted-retrieval", "question": data["question"], "evidence": evidence(first + second)}],
        "source": "examples/enterprise-rag/corpus.json",
    }
