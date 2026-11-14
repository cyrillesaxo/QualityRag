"""Compaction with a residual manifest (US-078).

When a runtime drops turns from the assistant's context, the manifest lists what was left
out, so the assistant knows it exists without holding it. A compaction that drops a span
with no manifest entry fails. The manifest is bounded; when it cannot fit, it fails instead
of dropping entries.

Probe checks here are mechanical: a probe names the spans its answer needs, and it fails
when those are not loaded. No model answers a question in this module.
"""
from __future__ import annotations

from .tree import SCHEMA
from .triggers import CRITICAL_FAMILIES, families

DEFAULT_MAX_ENTRIES = 400
STUB_CHARS = 80


def _unloaded_spans(tree, branch, loaded):
    ledger = tree.ledger(branch)
    visible = set(tree.visible_turns(branch))
    return ledger, [s for s in ledger["spans"] if s["turn_id"] in visible and s["turn_id"] not in loaded]


def manifest(tree, branch, *, loaded, max_entries=DEFAULT_MAX_ENTRIES):
    """List every in-scope span the assistant is not holding. Bounded; never silently truncated."""
    if type(max_entries) is not int or not 1 <= max_entries <= 5000:
        raise ValueError("Invalid manifest bound")
    loaded = set(loaded)
    ledger, spans = _unloaded_spans(tree, branch, loaded)
    texts = {t["turn_id"]: t["content"] for t in tree.turns()}

    def entry(span, folded=None):
        text = "" if span["rule"] == "NOT_UTF8_TEXT" else \
            texts[span["turn_id"]].decode("utf-8")[span["start"]:span["end"]]
        found = families(text) if text else []
        return {"id": "%s:%d-%d" % (span["turn_id"], span["start"], span["end"]),
                "turn_id": span["turn_id"], "start": span["start"], "end": span["end"],
                "actor": span["actor"], "disposition": span["disposition"], "rule": span["rule"],
                "obligation_id": span["obligation_id"], "families": found,
                "critical": span["rule"] == "STANDING_RULE" or (
                    span["actor"] == "USER" and bool(CRITICAL_FAMILIES.intersection(found))),
                "stub": " ".join(text.split())[:STUB_CHARS], "folded_spans": folded}

    entries = [entry(span) for span in spans]
    if len(entries) > max_entries:
        # Fold non-critical residual spans of a turn into one entry; keep every critical span.
        kept, folded = [], {}
        for item in entries:
            if item["critical"] or item["disposition"] != "RESIDUAL":
                kept.append(item)
            else:
                group = folded.setdefault(item["turn_id"], {**item, "folded_spans": 0, "stub": item["stub"]})
                group["end"], group["folded_spans"] = item["end"], group["folded_spans"] + 1
                group["id"] = "%s:%d-%d" % (group["turn_id"], group["start"], group["end"])
        entries = sorted(kept + list(folded.values()), key=lambda e: (e["turn_id"], e["start"]))
        if len(entries) > max_entries:
            raise ValueError("Manifest bound exceeded; load more turns or raise the bound")
    return {"schema": SCHEMA, "branch": branch, "snapshot": ledger["snapshot"],
            "packspec_version": ledger["packspec_version"], "bound": max_entries,
            "loaded": sorted(loaded), "entries": entries,
            "critical_unloaded": sum(1 for e in entries if e["critical"])}


def verify(tree, branch, *, loaded, candidate):
    """Fail when a compaction dropped an in-scope span without a manifest entry, or the manifest is stale."""
    ledger, spans = _unloaded_spans(tree, branch, set(loaded))
    if candidate.get("snapshot") != ledger["snapshot"] or candidate.get("branch") != branch:
        raise ValueError("Manifest does not describe the current branch state")
    covered = {}
    for item in candidate.get("entries", []):
        covered.setdefault(item["turn_id"], []).append((item["start"], item["end"]))
    missing = [s for s in spans
               if not any(a <= s["start"] and s["end"] <= b for a, b in covered.get(s["turn_id"], []))]
    if missing:
        raise ValueError("Compaction dropped %d span(s) with no manifest entry" % len(missing))
    return {"status": "MANIFEST_COVERS_ALL_UNLOADED_SPANS", "unloaded_spans": len(spans)}


def probe(*, loaded, probes, compactor):
    """Check independently sourced probes against what is loaded. Failed probes name what to load."""
    loaded = set(loaded)
    results, promote = [], []
    for item in probes:
        if item.get("source") in (None, "", compactor):
            raise ValueError("Probe must come from a source other than the compactor")
        needs = item.get("needs") or []
        if not needs:
            raise ValueError("Probe must name the spans its answer needs")
        absent = [n for n in needs if n["turn_id"] not in loaded]
        results.append({"probe_id": item["probe_id"], "status": "FAIL" if absent else "PASS"})
        promote.extend(n for n in absent if n not in promote)
    return {"results": results, "promote": promote,
            "method": "SPAN_AVAILABILITY_ONLY", "answered_by_model": False}
