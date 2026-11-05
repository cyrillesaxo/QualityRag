"""Render docs/STORY-CLOSURE-PACKETS.md from capabilities.json.

Each open story gets: what blocks it, the command that exercises its software,
the evidence a closer must attach, who may sign, and story-specific notes.
The packet never changes a status; DONE still requires a signed receipt that
audit.py verifies.

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
DOC = ROOT / "docs/STORY-CLOSURE-PACKETS.md"

CATEGORIES = {
    "MERGE": {
        "title": "Merge after review",
        "stories": ["US-010", "US-011", "US-022", "US-023", "US-039"],
        "steps": ["Reviewer reads the linked tests and module, runs the command below, and approves the PR.",
                  "Owner merges after required CI passes on the merge commit.",
                  "Reviewer drafts and signs the completion receipt (see *Signing*)."],
        "signer": "Any qualified code reviewer who did not author the story.",
    },
    "MERGE_PLUS": {
        "title": "Merge plus one recorded check",
        "stories": ["US-013", "US-020", "US-034", "US-035", "US-045", "US-047"],
        "steps": ["Do everything in *Merge after review*.",
                  "Perform the extra check in the notes and record it as evidence (a CI run, measurement or review record) before signing."],
        "signer": "A code reviewer who did not author the story; the extra check may need an operator (sandbox host, signing policy, package registry).",
    },
    "REVIEWER": {
        "title": "Independent qualified review",
        "stories": ["US-003", "US-004", "US-005", "US-006", "US-008", "US-012", "US-014", "US-015",
                    "US-018", "US-019", "US-026", "US-030", "US-038", "US-040", "US-050"],
        "steps": ["Reviewer reproduces the command below on a clean checkout of the implementation commit.",
                  "Reviewer checks every acceptance criterion against observed behaviour, not the docs, and writes findings (including failures) to a review record.",
                  "Only if every criterion is met: draft, attest and sign the receipt."],
        "signer": "A domain-qualified reviewer independent of the author (named in the notes where the domain matters).",
    },
    "AUTHORITY": {
        "title": "Real deployment or signing authority",
        "stories": ["US-017", "US-024", "US-036", "US-042", "US-043", "US-044"],
        "steps": ["Owner configures the real authority (keys, principals, trust maps, deployment) outside the repository.",
                  "Operator runs the command below against that configuration and records the result.",
                  "Security/privacy reviewer signs only after observing the configured system."],
        "signer": "Security or platform reviewer with access to the configured deployment.",
    },
    "REAL_WORLD": {
        "title": "Real data, devices or measurements",
        "stories": ["US-007", "US-009", "US-016", "US-021", "US-025", "US-027", "US-028", "US-029", "US-031",
                    "US-032", "US-033", "US-037", "US-041", "US-046", "US-048", "US-049", "US-051"],
        "steps": ["Acquire the input named in the notes (licensed corpus, device, canonical source, real users).",
                  "Run the existing harness on it and keep the raw outputs, including failures and negative results.",
                  "Domain reviewer signs only against the real-input evidence; synthetic fixtures never satisfy these."],
        "signer": "Domain reviewer for the data or device class (see notes).",
    },
}

NOTES = {
    "US-010": "Remaining item is merge + remote CI only.",
    "US-011": "Check that finite SAT never yields `qualityrag_admission=ADMIT` or `can_generate=true` anywhere in the trace.",
    "US-022": "Blocked only on PR #69. Reviewed 2026-11-05: declarations-only checker; fixed silently-accepted misspelled operator keys and PRESERVE/VERIFY fields outside the contract (commit c1408f7). PR #69 + PR #70 merge cleanly onto main and all suites pass on the merged tree. Merge PR #69 first. Run on the PR #69 branch: `python -m unittest discover -s tools/semantic_store/tests -p 'test_activation_constraints.py' -v`.",
    "US-023": "Confirm VERIFY compares actual transformed output and that a failed fallback REFUSEs without releasing output.",
    "US-039": "Check the integration test shows disagreement escalating, not forced consensus.",
    "US-013": "Extra check: run the sandboxed search on a supported Linux host (seccomp/RLIMIT available) and record the host and result.",
    "US-020": "Extra check: a configured production signing key and minimum-version policy, then a tested authorized rollback.",
    "US-034": "Extra check: independent restart replay — kill the service mid-run, restart, and confirm `gardener/state` replays identically.",
    "US-035": "Extra check: a reviewer exercises PROPOSE/CHALLENGE/TEST/SYNTHESIZE/PRUNE/REOPEN through the UI or API (TEST via `evidence_ids` since commit 51f3e0e) and records continuity.",
    "US-045": "Extra check: package/release acceptance of the Python and TypeScript clients (published or tagged artefacts).",
    "US-047": "Extra check: the CI audit must load `reviewer-trust.json` before any signed receipt can count (see *Wiring gap*). This story is the natural place to do that.",
    "US-003": "Reviewer: someone outside the project replays `run_research.py` on the pinned environment lock.",
    "US-004": "Reviewer: a codec/knowledge-compilation researcher assessing `research/prior-art.md`; no priority claim is made.",
    "US-005": "Reviewer: domain owner per profile (clinical, legal, education, video).",
    "US-006": "Reviewer must hold a real signing key bound to a qualified source/policy; the test keys in fixtures do not count.",
    "US-008": "Reviewer records an omission review for at least one real optional distinction before it is discarded.",
    "US-012": "Reviewer checks the finite source-to-target mapping and the no-invented-labels round trip.",
    "US-014": "Needs measured amortization beyond authored fixtures; an independent replay of cache invalidation.",
    "US-015": "Reviewer confirms the declared finite query vocabulary and that results are not generalized.",
    "US-018": "Reviewer runs the adapters on representative real PDFs/CSVs (duplicated headings, malformed input) and checks span anchors.",
    "US-019": "Reviewer: authorized role-extraction reviewer; candidates stay quarantined until then.",
    "US-026": "Reviewer checks the normalized RGB/PCM32/timestamp profile byte-for-byte on the provided fixtures and one real clip.",
    "US-030": "Reviewer confirms the payload is the palette/residual reference, not learned semantics or FF-RCT, and that decode plays.",
    "US-038": "Reviewer: security review of the sandbox on a supported host.",
    "US-040": "Needs independently adjudicated family-hidden real cases; authored false-accept counts do not generalize.",
    "US-050": "Reviewer: external peer review of `research/paper/report.md`; no validated compression improvement is claimed.",
    "US-017": "Needs deployed persistent custody with trusted host authorization.",
    "US-024": "Needs a real release-signing authority and supported-runtime approval.",
    "US-036": "Needs real, scope-bounded validation evidence through the ledger's host verifier (SQLite and PostgreSQL paths exist).",
    "US-042": "Needs a measured energy/total-cost frontier and a real signed promotion authority.",
    "US-043": "Needs configured real tenant principals and a deployment privacy review.",
    "US-044": "Needs real release/reviewer trust maps, durable deployment and an independent replay/revocation review.",
    "US-007": "Needs real source ancestry/custody evidence; origin labels alone are insufficient.",
    "US-009": "Clinical and video profiles need scored adversarial cases from independent domain reviewers. Legal: CUAD (510 contracts, CC BY 4.0) supplies real role-binding clauses.",
    "US-016": "Needs canonical K/B/C/T source/API parity, which only the private APX source can supply, plus independent annotation review.",
    "US-021": "Needs the original canonical FF-RCT reconstruction interface from the private APX tree; only the author can supply it.",
    "US-025": "Needs a physical device with GPU/energy instrumentation for cold and sustained sparse-versus-full runs.",
    "US-027": "Needs a supported device for old/new-runtime A/B and interrupted update/rollback measurements.",
    "US-028": "Candidate corpus: Blender Studio open films (CC BY, check each asset's licence text; Tears of Steel is CC BY 3.0 with a credit-scroll requirement, its soundtrack CC BY-ND) and the public-domain sequences in Xiph's derf collection (FourPeople, Johnny, KristenAndSara, vidyo1/3/4). Netflix Chimera/El Fuente clips there are marked Copyright. 100 annotated clips with family-disjoint splits are still required.",
    "US-029": "AV1: SVT-AV1 or libaom. Learned codec: CompressAI (code BSD-3-Clause-Clear); the pretrained weights' licence must be confirmed separately before use.",
    "US-031": "Depends on US-028; blinded human assessment cannot be done by the author or an agent.",
    "US-032": "Needs measured lifecycle inputs per real catalog/viewer/device cohort.",
    "US-033": "Needs network/device startup, buffering and seek measurements against conventional playback.",
    "US-037": "Needs real user feedback; duplicate detection is exact-statement only, so paraphrase detection would need a semantic labeler first.",
    "US-041": "Depends on US-028 and US-029, with all search/training compute counted.",
    "US-046": "Needs two physical device classes (mobile and TV) with thermal, sustained-power and update-traffic instrumentation.",
    "US-048": "Register the final protocol only after US-028's corpus and sample plan exist, before opening the holdout.",
    "US-049": "Contract demo: CUAD clauses (CC BY 4.0). Nursing demo: OpenStax Clinical Nursing Skills is CC BY-NC-SA 4.0 — fine for research, not for a commercial product. Child-to-clinician: no open source identified; inputs must be authored and clinician-reviewed.",
    "US-051": "Last in order: requires the security/privacy/licensing/fidelity reviews and measured pilot economics above.",
}


def _story_category() -> dict[str, str]:
    out = {}
    for key, cat in CATEGORIES.items():
        for sid in cat["stories"]:
            if sid in out:
                raise ValueError("Story in two categories: " + sid)
            out[sid] = key
    return out


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


def render(capabilities: Path = CAPABILITIES) -> str:
    inventory = json.loads(Path(capabilities).read_text())
    stories = {s["story_id"]: s for s in inventory["stories"]}
    category = _story_category()
    open_ids = sorted(sid for sid, s in stories.items() if s["status"] != "DONE")
    missing = sorted(set(open_ids) - set(category))
    stale = sorted(sid for sid in category if stories.get(sid, {}).get("status") == "DONE")
    if missing or stale:
        raise ValueError(f"Category map out of date: uncategorized={missing} done={stale}")
    counts = {}
    for s in stories.values():
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    lines = [
        "# Story closure packets",
        "",
        "<!-- Generated by `python -m tools.activation_runtime.closure_packets`; do not edit by hand. -->",
        "",
        "What each open FR.MD story needs to reach DONE, and who can provide it. This page changes no status. "
        "DONE still requires a completion receipt signed by an independent reviewer and verified by `audit.py`.",
        "",
        "Inventory: " + ", ".join(f"{counts[k]} {k}" for k in sorted(counts)) + f". Open: {len(open_ids)}.",
        "",
        "| Category | Stories |",
        "|---|---|",
    ]
    for key, cat in CATEGORIES.items():
        lines.append(f"| {cat['title']} ({len(cat['stories'])}) | {', '.join(cat['stories'])} |")
    lines += [
        "",
        "## Signing",
        "",
        "A reviewer holds their own Ed25519 key (for example `openssl genpkey -algorithm ed25519 -out reviewer.pem`). "
        "The tooling never generates or stores reviewer keys.",
        "",
        "```bash",
        "# 1. Publish the public key: add the output to tools/activation_runtime/reviewer-trust.json in a reviewed PR",
        "python -m tools.activation_runtime.story_completion pubkey --key reviewer.pem --key-id <id> --subject \"<name>\"",
        "# 2. Draft the exact receipt audit.py expects, read it, and attest only if every criterion is met",
        "python -m tools.activation_runtime.story_completion draft --story US-0XX --implementation-commit <sha> \\",
        "    --merge-commit <sha> --ci-url <https://github.com/...> --ci-receipt-sha256 <hex> --attest-all-criteria-met > receipt.json",
        "# 3. Sign (validity is at most 30 days, enforced by signed_bundles)",
        "python -m tools.activation_runtime.story_completion sign --receipt receipt.json --key reviewer.pem \\",
        "    --key-id <id> --issued-at <iso> --expires-at <iso> > envelope.json",
        "# 4. Check it exactly as audit.py would",
        "python -m tools.activation_runtime.story_completion verify --story US-0XX --implementation-commit <sha> --envelope envelope.json",
        "```",
        "",
        "A receipt is bound to the story's acceptance text and module hashes. Any later change to those modules invalidates it, "
        "and the draft must be redone.",
        "",
        "## Wiring gap (must be closed before any receipt counts)",
        "",
        "1. The CI step `python -m tools.activation_runtime.audit` calls `audit()` without reviewer keys, so any story beyond "
        "US-001/US-002 marked DONE fails CI even with a valid receipt. `audit.py`'s entry point needs to load "
        "`reviewer-trust.json` and pass `as_of` = now.",
        "2. `audit.py` and the activation workflow are pinned modules of the DONE stories US-001 and US-002. Changing either "
        "requires renewing their completion evidence (new implementation commit, passing CI run, updated "
        "`completion_evidence`), as was done when US-002 landed.",
        "3. Decide receipt lifetime. Signed envelopes are capped at 30 days and the audit checks them against the current "
        "time, so a DONE story would fail CI a month later unless re-signed. Either accept monthly re-signing, or verify "
        "receipts at their issue time and rely on removing keys from the trust store for revocation.",
        "",
    ]
    for key, cat in CATEGORIES.items():
        lines += [f"## {cat['title']}", "", "Steps:", ""]
        lines += [f"{i}. {step}" for i, step in enumerate(cat["steps"], 1)]
        lines += ["", f"Who signs: {cat['signer']}", ""]
        for sid in cat["stories"]:
            s = stories[sid]
            lines += [
                f"### {sid} · {s['title']} ({s['status']})",
                "",
                f"- **Blocking:** {s['remaining']}",
                f"- **Exercise the software:** {_command(s['test_or_receipt'])}",
                f"- **Modules bound into the receipt:** {len(s['modules'])} file(s)",
            ]
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
