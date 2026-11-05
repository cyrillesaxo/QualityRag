"""Render docs/STORY-CLOSURE-PACKETS.md from capabilities.json and criteria_map.json.

Each open story is placed by its *written acceptance criteria* (criteria_map.json),
not by a hand-picked label: unfinished software first, then criteria that
explicitly require human review, then those needing external input, then
stories whose software criteria are all met. The packet never changes a
status; DONE still requires acceptance that audit.py verifies.

    python -m tools.activation_runtime.closure_packets          # rewrite the doc
    python -m tools.activation_runtime.closure_packets --check  # fail if the doc is stale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES = ROOT / "tools/activation_runtime/capabilities.json"
CRITERIA = ROOT / "tools/activation_runtime/criteria_map.json"
DOC = ROOT / "docs/STORY-CLOSURE-PACKETS.md"

KINDS = {"SOFTWARE", "DOCUMENT", "HUMAN_REVIEW", "EXTERNAL_INPUT", "MERGE"}
STATUSES = {"TESTED", "IMPLEMENTED", "PARTIAL", "GAP", "NEEDS_INPUT"}
MET = {"TESTED", "IMPLEMENTED"}

CATEGORIES = {
    "SOFTWARE_WORK": {
        "title": "Software work remaining",
        "steps": ["Implement the PARTIAL/GAP criteria in the table; these need no outside input.",
                  "Add a test per criterion and record it in criteria_map.json."],
    },
    "HUMAN_REVIEW": {
        "title": "A written criterion requires human review",
        "steps": ["Only the HUMAN_REVIEW criteria need a person; the rest is listed with its evidence.",
                  "The reviewer records findings, including failures, and signs the completion receipt (see *Signing*)."],
    },
    "EXTERNAL_INPUT": {
        "title": "Needs external input",
        "steps": ["Supply the input named in the table (licensed data, device, private source or merge).",
                  "Run the existing harness on it; keep raw outputs and negative results."],
    },
    "DOCUMENT": {
        "title": "Document check only",
        "steps": ["A reader confirms the DOCUMENT criteria against the named file; no special qualification is implied by the criteria."],
    },
    "READY": {
        "title": "Written software criteria met",
        "steps": ["Every written criterion is TESTED or IMPLEMENTED on this branch.",
                  "Remaining: merge, then record acceptance. Where the inventory's *blocking* text asks for more than the written criteria, that is flagged."],
    },
}

NOTES = {
    "US-007": "Original APX WitnessGraph source and a pinned golden fixture are now integrated. The custody-root adapter refuses canonical grouping discrepancies; declared independence is not authenticated source independence. See docs/CANONICAL-WITNESS-GRAPH.md.",
    "US-009": "Legal: CUAD (510 contracts, CC BY 4.0) supplies real role-binding clauses for adversarial scoring.",
    "US-021": "Needs the original canonical FF-RCT reconstruction interface from the private APX tree; only the author can supply it.",
    "US-022": "Blocked only on PR #69 (reviewed; fixes in c1408f7). PR #69 + PR #70 merge cleanly onto main. Run on the PR #69 branch: `python -m unittest discover -s tools/semantic_store/tests -p 'test_activation_constraints.py' -v`.",
    "US-028": "Candidate corpus: Blender Studio open films (CC BY; check each asset's licence text; Tears of Steel is CC BY 3.0 with a credit-scroll requirement, its soundtrack CC BY-ND) and the public-domain sequences in Xiph's derf collection (FourPeople, Johnny, KristenAndSara, vidyo1/3/4). Netflix Chimera/El Fuente clips there are marked Copyright.",
    "US-029": "AV1: SVT-AV1 or libaom. Learned codec: CompressAI (code BSD-3-Clause-Clear); confirm the pretrained weights' licence separately.",
    "US-037": "Duplicate detection is exact-statement only; paraphrase detection would need a semantic labeler.",
    "US-049": "Contract demo: CUAD (CC BY 4.0). Nursing: OpenStax Clinical Nursing Skills is CC BY-NC-SA 4.0 (research only). Child-to-clinician: no open source identified.",
}


def load_criteria(path: Path = CRITERIA) -> dict:
    data = json.loads(Path(path).read_text())
    if data.get("schema") != "qualityrag.criteria-map/v1":
        raise ValueError("Invalid criteria map")
    for sid, rows in data["stories"].items():
        for row in rows:
            if row.get("kind") not in KINDS or row.get("status") not in STATUSES:
                raise ValueError(f"Invalid kind/status in {sid} criterion {row.get('n')}")
    return data["stories"]


def classify(rows: list[dict]) -> str:
    if any(r["kind"] in ("SOFTWARE", "DOCUMENT") and r["status"] in ("PARTIAL", "GAP") for r in rows):
        return "SOFTWARE_WORK"
    if any(r["kind"] == "HUMAN_REVIEW" for r in rows):
        return "HUMAN_REVIEW"
    if any(r["kind"] in ("EXTERNAL_INPUT", "MERGE") and r["status"] not in MET for r in rows):
        return "EXTERNAL_INPUT"
    if any(r["kind"] == "DOCUMENT" and r["status"] not in MET for r in rows):
        return "DOCUMENT"
    return "READY"


def _command(entry: str) -> str:
    """Turn a `test_or_receipt` entry (paths separated by ';') into runnable commands."""
    parts = [p.strip() for p in entry.split(";") if p.strip()]
    # Tests import siblings (e.g. test_runtime), so they must run through discover from their own directory.
    py = [p for p in parts if p.endswith(".py") and "/tests/" in p]
    commands = []
    if py:
        commands.append("`" + " && ".join(
            f"python -m unittest discover -s {Path(p).parent} -p '{Path(p).name}'" for p in py) + "`")
    for p in parts:
        if p.endswith(".mjs"):
            # The TypeScript SDK tests import the compiled dist/, so build through npm first.
            commands.append("`(cd sdk/typescript && npm ci && npm test)`" if p.startswith("sdk/typescript/")
                            else "`node --test " + p + "`")
    commands += ["see " + p for p in parts if not (p.endswith(".mjs") or (p.endswith(".py") and "/tests/" in p))]
    return "; ".join(commands)


def render(capabilities: Path = CAPABILITIES, criteria: Path = CRITERIA) -> str:
    inventory = json.loads(Path(capabilities).read_text())
    stories = {s["story_id"]: s for s in inventory["stories"]}
    cmap = load_criteria(criteria)
    open_ids = sorted(sid for sid, s in stories.items() if s["status"] != "DONE")
    if sorted(cmap) != open_ids:
        raise ValueError("criteria_map.json must cover exactly the open stories")
    for sid in open_ids:
        if [r["n"] for r in cmap[sid]] != [c["number"] for c in stories[sid]["criteria"]]:
            raise ValueError("criteria_map.json criterion numbers differ for " + sid)
    groups = {key: [] for key in CATEGORIES}
    for sid in open_ids:
        groups[classify(cmap[sid])].append(sid)
    counts = {}
    for s in stories.values():
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    tally = {}
    for rows in cmap.values():
        for r in rows:
            tally[(r["kind"], r["status"])] = tally.get((r["kind"], r["status"]), 0) + 1
    lines = [
        "# Story closure packets",
        "",
        "<!-- Generated by `python -m tools.activation_runtime.closure_packets`; do not edit by hand. -->",
        "",
        "What each open FR.MD story still needs, judged criterion by criterion against its *written* acceptance "
        "criteria (`tools/activation_runtime/criteria_map.json`). This page changes no status.",
        "",
        "Inventory: " + ", ".join(f"{counts[k]} {k}" for k in sorted(counts)) + f". Open: {len(open_ids)}, "
        f"with {sum(len(r) for r in cmap.values())} criteria.",
        "",
        "| Category | Stories |",
        "|---|---|",
    ]
    for key, cat in CATEGORIES.items():
        lines.append(f"| {cat['title']} ({len(groups[key])}) | {', '.join(groups[key]) or '—'} |")
    lines += ["", "Criteria by kind and status:", "", "| Kind | " + " | ".join(sorted(STATUSES)) + " |",
              "|---|" + "---|" * len(STATUSES)]
    for kind in sorted(KINDS):
        lines.append(f"| {kind} | " + " | ".join(str(tally.get((kind, st), 0)) for st in sorted(STATUSES)) + " |")
    lines += [
        "",
        "## Signing",
        "",
        "A reviewer holds their own Ed25519 key (for example `openssl genpkey -algorithm ed25519 -out reviewer.pem`). "
        "The tooling never generates or stores reviewer keys.",
        "",
        "```bash",
        "# 1. Publish the public key: add the output to tools/activation_runtime/reviewer-trust.json in a reviewed PR",
        "python -m tools.activation_runtime.story_completion pubkey --key reviewer.pem --key-id <id> \\",
        "    --github-login <login> --valid-from <YYYY-MM-DDTHH:MM:SSZ> --subject \"<name>\"",
        "# 2. Draft the exact receipt audit.py expects, read it, and attest only if every criterion is met",
        "python -m tools.activation_runtime.story_completion draft --story US-0XX --implementation-commit <sha> \\",
        "    --merge-commit <sha> --ci-url https://github.com/cyrillesaxo/QualityRag/actions/runs/<id> \\",
        "    --ci-receipt-sha256 <hex> --attest-all-criteria-met > receipt.json",
        "# 3. Sign, with issued-at = now (UTC, after the CI run finished)",
        "python -m tools.activation_runtime.story_completion sign --receipt receipt.json --key reviewer.pem \\",
        "    --key-id <id> --issued-at <now> --expires-at <now + up to 30 days> > envelope.json",
        "# 4. Check it exactly as CI will, then record it (sets DONE)",
        "python -m tools.activation_runtime.story_completion verify --story US-0XX --implementation-commit <sha> --envelope envelope.json",
        "python -m tools.activation_runtime.story_completion attach --story US-0XX --implementation-commit <sha> --envelope envelope.json",
        "```",
        "",
        "## How CI verifies a completion",
        "",
        "`python -m tools.activation_runtime.audit` (an existing CI step) loads `reviewer-trust.json` and re-verifies every "
        "signed DONE story on each run. A receipt is a **historical record**: it does not lapse when its signature window "
        "ends. Because its issue time is self-declared, CI bounds it with evidence the reviewer cannot set:",
        "",
        "- the referenced CI run (`actions/runs/<id>` in this repository) must have passed on the implementation commit, and the "
        "receipt cannot be issued before that run finished, nor in the future;",
        "- the implementation commit must be contained in the merge commit, and the merge commit must be on `main`;",
        "- the reviewer's GitHub login must differ from the implementation commit's author;",
        "- the key must be in the trust store and its window must cover the issue time: `active`, or `retired` with "
        "`retired_at` after the issue time (routine rotation keeps earlier receipts valid); a `compromised` key invalidates "
        "every receipt it signed;",
        "- the receipt is bound to the story's acceptance text and module hashes, so any later change to those modules "
        "invalidates it and the story must be re-reviewed.",
        "",
        "Residual risk: someone holding a *retired* key could still sign a receipt dated between a run's completion and the "
        "retirement time. If a retired key may be in other hands, mark it `compromised`.",
        "",
    ]
    for key, cat in CATEGORIES.items():
        if not groups[key]:
            continue
        lines += [f"## {cat['title']}", ""]
        lines += [f"{i}. {step}" for i, step in enumerate(cat["steps"], 1)]
        lines.append("")
        for sid in groups[key]:
            s = stories[sid]
            texts = {c["number"]: c["text"] for c in s["criteria"]}
            lines += [f"### {sid} · {s['title']} ({s['status']})", ""]
            lines += ["| # | Criterion | Kind | Status | Evidence / note |", "|---|---|---|---|---|"]
            for r in cmap[sid]:
                ev = ", ".join("`" + e + "`" for e in r.get("evidence", []))
                note = r.get("note", "")
                cell = "; ".join(x for x in (ev, note) if x) or "—"
                lines.append(f"| {r['n']} | {texts[r['n']].replace('|', '/')} | {r['kind']} | {r['status']} | {cell.replace('|', '/')} |")
            lines += ["", f"- **Exercise the software:** {_command(s['test_or_receipt'])}",
                      f"- **Inventory blocking text:** {s['remaining']}"]
            if key == "READY":
                lines.append("- **Note:** every written criterion is met; anything above that asks for more goes beyond the criteria.")
            if sid in NOTES:
                lines.append(f"- **Notes:** {NOTES[sid]}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not DOC.exists() or DOC.read_text() != text:
            sys.exit("docs/STORY-CLOSURE-PACKETS.md is stale; run python -m tools.activation_runtime.closure_packets")
        print("closure packets up to date")
        return
    DOC.write_text(text)
    print("wrote", DOC.relative_to(ROOT))


if __name__ == "__main__":
    main()
