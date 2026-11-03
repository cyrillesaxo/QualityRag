"""Conservative APX PackSpec source inspector and approved evidence projection compiler.

Never infers that semantic clauses become executable just because text was found.
Input formats: YAML, JSON, and text-bearing PDFs. Image-only PDFs require OCR
outside this tool; no automatic admission or fallback is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "qualityrag.source-inspection/v1"
MAPPING_SCHEMA = "qualityrag.manual-mapping/v1"
MAX_BYTES = 2_000_000
MAX_PAGES = 200
MAX_CANDIDATES = 240
ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
RULE_TERMS = re.compile(r"\b(must|shall|required|requires|never|only|prohibited|cannot|constraint|invariant)\b",re.I)


class CompileError(ValueError):
    """Invalid, incomplete, ambiguous or unapproved compilation input."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _bounded(path: Path) -> bytes:
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise CompileError("Source missing or exceeds size limit")
    raw = path.read_bytes()
    if not raw:
        raise CompileError("Empty source")
    return raw


def _flatten(value: Any, pointer: str = "", depth: int = 0):
    """Yield source-addressable text leaves from structured packs without guessing semantics."""
    if depth > 16:
        raise CompileError("Nested source exceeds inspection depth")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise CompileError("Non-string key cannot be referenced")
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from _flatten(child, pointer + "/" + escaped, depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _flatten(child, pointer + "/" + str(index), depth + 1)
    elif isinstance(value, str) and value.strip():
        yield pointer or "/", " ".join(value.split())


def _source_identity(value: Any, suffix: str, default: str) -> tuple[str, str]:
    if not isinstance(value, dict):
        return default, "unknown"
    if suffix == ".json":
        p = value.get("pack")
        if isinstance(p, dict):
            return str(p.get("id", default)), str(p.get("version", "unknown"))
    return str(value.get("pack_id", value.get("id", default))), str(value.get("version", "unknown"))


def inspect(path: str | Path) -> dict:
    path = Path(path)
    raw = _bounded(path)
    ext = path.suffix.lower()
    items = []
    if ext in (".yaml", ".yml", ".json"):
        if ext == ".json":
            data = json.loads(raw)
        else:
            try:
                import yaml
            except ImportError as e:
                raise CompileError("PyYAML is required for YAML input") from e
            data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise CompileError("Expected mapping at source root")
        pack_id, version = _source_identity(data, ext, path.stem)
        leaves = list(_flatten(data))
        for pointer, text in leaves:
            if RULE_TERMS.search(text) or re.search(r"/(must_constraints|invariants|requirements|probes|required_planes)/", pointer):
                items.append((pointer, text[:1600]))
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise CompileError("pypdf is required for PDF input") from e
        reader = PdfReader(path)
        if len(reader.pages) > MAX_PAGES:
            raise CompileError("PDF exceeds page limit")
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
        if not any(page_texts):
            raise CompileError("Image-only/empty PDF: OCR and manual source verification required")
        pack_id, version = path.stem, "unverified-from-pdf"
        for number, page_text in enumerate(page_texts, 1):
            lines = [" ".join(line.split()) for line in page_text.splitlines()]
            for line_no, line in enumerate(lines, 1):
                if len(line) >= 16 and RULE_TERMS.search(line):
                    items.append((f"page:{number}:line:{line_no}", line[:1600]))
    else:
        raise CompileError("Supported file types: .yaml .yml .json .pdf")

    # Preserve source-address and exact extracted quotation. No semantic simplification.
    unique = set()
    candidates = []
    for location, quotation in items:
        key = (location, quotation)
        if key in unique:
            continue
        unique.add(key)
        if len(candidates) >= MAX_CANDIDATES:
            break
        candidates.append({
            "candidate_id": f"C{len(candidates)+1:04d}",
            "location": location,
            "quotation": quotation,
            "quotation_sha256": digest(quotation.encode("utf-8")),
            "classification": "REVIEW_REQUIRED",
            "reason": "Source text alone does not establish enforceability, authority, or evidence sufficiency",
        })
    return {
        "schema": SCHEMA,
        "source": {
            "filename": path.name, "format": ext.removeprefix("."),
            "sha256": digest(raw), "bytes": len(raw),
            "pack_id": pack_id, "version": version,
        },
        "limits": {
            "candidate_limit": MAX_CANDIDATES,
            "truncated": len(unique) > MAX_CANDIDATES,
            "pdf_ocr_performed": False,
        },
        "candidate_constraints": candidates,
        "enforceability": {
            "automatically_enforceable": 0,
            "review_required": len(candidates),
            "supported_projection": "Evidence-presence requirements ONLY after explicit human-approved mapping",
            "not_implemented": [
                "Full APX semantic predicates and governance lifecycle",
                "Source authority, applicability, independence, version drift",
                "Proof of truth from witness metadata",
                "PDF OCR, diagrams, formulas and table interpretation",
            ],
        },
    }


def draft_mapping(report: dict, limit: int = 15) -> dict:
    """Create an inert review worksheet: no requirement is preapproved."""
    return {
        "schema": MAPPING_SCHEMA,
        "source_sha256": report["source"]["sha256"],
        "policy_id": "reviewed-source-projection",
        "policy_version": "1.0",
        "rules": [{
            "candidate_id": candidate["candidate_id"],
            "requirement_id": "",
            "reviewed_by": "",
            "approved": False,
            "rationale": "",
        } for candidate in report["candidate_constraints"][:limit]],
        "notes": "Delete irrelevant items, read the source in full and verify scope, then approve specific evidence-presence mappings. No automatic approval.",
    }


def project(report: dict, mapping: dict) -> dict:
    """Produce only an explicitly approved *evidence-presence* projection.

    The output cannot claim to enforce the original rich source semantics.
    """
    if report.get("schema") != SCHEMA or mapping.get("schema") != MAPPING_SCHEMA:
        raise CompileError("Unsupported report or mapping schema")
    source = report["source"]
    if mapping.get("source_sha256") != source["sha256"]:
        raise CompileError("Source fingerprint mismatch: approval cannot transfer")
    rules = mapping.get("rules")
    if not isinstance(rules, list) or not rules:
        raise CompileError("Mapping must contain reviewed rules")
    by_id = {c["candidate_id"]: c for c in report["candidate_constraints"]}
    used, requirements, receipts = set(), [], []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("approved") is not True:
            raise CompileError("Every selected mapping requires explicit approval")
        candidate = by_id.get(rule.get("candidate_id"))
        requirement_id = rule.get("requirement_id")
        reviewer = rule.get("reviewed_by")
        rationale = rule.get("rationale")
        if candidate is None:
            raise CompileError("Mapping references unknown source constraint")
        if not isinstance(requirement_id, str) or not ID.fullmatch(requirement_id):
            raise CompileError("Invalid requirement identifier")
        if requirement_id in used:
            raise CompileError("Duplicate projected evidence requirement")
        if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(rationale, str) or len(rationale.strip()) < 12:
            raise CompileError("Reviewer and substantive rationale required")
        count = rule.get("min_independent_sources", 1)
        if type(count) is not int or not 1 <= count <= 20:
            raise CompileError("Invalid source count")
        used.add(requirement_id)
        requirements.append({"id": requirement_id, "min_independent_sources": count})
        receipts.append({
            "requirement_id": requirement_id,
            "candidate_id": candidate["candidate_id"],
            "source_location": candidate["location"],
            "quotation_sha256": candidate["quotation_sha256"],
            "reviewed_by": reviewer,
            "rationale": rationale,
            "semantic_enforcement": "NOT_IMPLEMENTED",
            "enforced_check": "DECLARED_EVIDENCE_PRESENCE",
        })
    policy = {
        "id": mapping.get("policy_id", "source-projection"),
        "version": mapping.get("policy_version", "1.0"),
        "requirements": requirements,
    }
    if not isinstance(policy["id"], str) or not ID.fullmatch(policy["id"]) or not isinstance(policy["version"], str) or not policy["version"]:
        raise CompileError("Invalid projected policy metadata")
    return {
        "projection_schema": "qualityrag.approved-evidence-projection/v1",
        "source_sha256": source["sha256"],
        "policy": policy,
        "mapping_receipts": receipts,
        "warning": "ADMIT satisfies declared evidence presence only; original APX semantic constraints are NOT enforced",
    }


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(description="Inspect rich APX PackSpecs without pretending to execute them")
    cli.add_argument("source", help="Local .yaml/.json/.pdf PackSpec")
    cli.add_argument("--out", required=True, help="Output inspection JSON")
    cli.add_argument("--mapping", help="Human-approved candidate mapping JSON")
    cli.add_argument("--draft-mapping-out", help="Write unapproved review worksheet JSON")
    cli.add_argument("--policy-out", help="Optional output standalone QualityRag policy JSON")
    cli.add_argument("--typed-mapping", help="Reviewed mapping with typed constraint kinds")
    cli.add_argument("--typed-draft-out", help="Inert typed-constraint review worksheet")
    cli.add_argument("--ir-out", help="Output typed ConstraintIR JSON; requires --typed-mapping")
    cli.add_argument("--typed-policy-out", help="Evidence-only projection from typed IR")
    cli.add_argument("--typed-policy-id", help="Identifier for projected evidence policy")
    cli.add_argument("--acknowledge-deferred", action="store_true", help="Allow explicitly partial evidence-only projection")
    args = cli.parse_args(argv)
    report = inspect(args.source)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.draft_mapping_out:
        Path(args.draft_mapping_out).write_text(json.dumps(draft_mapping(report), indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    if args.mapping:
        mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
        compiled = project(report, mapping)
        if not args.policy_out:
            raise CompileError("--policy-out required with --mapping")
        Path(args.policy_out).write_text(json.dumps(compiled["policy"], indent=2) + "\n", encoding="utf-8")
        Path(args.out).write_text(json.dumps({**report, "approved_projection": compiled}, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    if args.typed_draft_out or args.typed_mapping:
        from typed_ir import draft_typed_mapping, compile_ir, project_gate, IRValidationError
        if args.typed_draft_out:
            Path(args.typed_draft_out).write_text(
                json.dumps(draft_typed_mapping(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.typed_mapping:
            if not args.ir_out:
                raise CompileError("--ir-out required with --typed-mapping")
            try:
                mapping = json.loads(Path(args.typed_mapping).read_text(encoding="utf-8"))
                ir = compile_ir(report, mapping)
                if args.typed_policy_out:
                    if not args.typed_policy_id:
                        raise CompileError("--typed-policy-id required for typed projection")
                    result = project_gate(ir, args.typed_policy_id, acknowledge_deferred=args.acknowledge_deferred)
                    Path(args.typed_policy_out).write_text(
                        json.dumps(result["policy"], indent=2) + "\n", encoding="utf-8")
                Path(args.ir_out).write_text(
                    json.dumps(ir, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except IRValidationError as e:
                raise CompileError(str(e)) from e
    print(f"Inspect: {len(report['candidate_constraints'])} candidate passages, zero automatic semantic admissions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
