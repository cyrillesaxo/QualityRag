"""Finite, source-anchored typed role-binding grammar for RCT falsification.

Unlike lexical-atom multiset comparison, this compares explicitly annotated
predicate-role-entity edges. Reviewers or trusted annotation tools must supply
and later sign the roles and identities; this module does NOT extract or verify
semantic truth from arbitrary natural language.

Examples: PAY(OBLIGOR=Alice,BENEFICIARY=Bob) vs role inversion;
THRESHOLD(VALUE=5,UNIT=psi) vs changed unit;
ACTION_ORDER(FIRST=verify,SECOND=administer) vs changed order.

Only observed counterexamples REFUSE. Exact graph equality remains INCONCLUSIVE.
"""
from __future__ import annotations

from hashlib import sha256
import re

from store import digest

SCHEMA = "rct.typed-role-binding-audit/v0.1"
ATOM = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,95}$")
ENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
MAX_DOC_BYTES = 200_000
MAX_FACTS = 128
MAX_BINDINGS = 24


def _span(document: str, item: dict) -> str:
    if not isinstance(item, dict) or set(item) != {"start", "end", "quote"}:
        raise ValueError("Exact source anchor required")
    start, end, quote = item["start"], item["end"], item["quote"]
    if (type(start) is not int or type(end) is not int
            or not isinstance(quote, str)
            or not 0 <= start < end <= len(document)
            or document[start:end] != quote):
        raise ValueError("Role anchor does not match exact document bytes")
    return quote


def _facts(document: str, facts: list[dict], *, side: str) -> dict:
    if (not isinstance(facts, list) or not 1 <= len(facts) <= MAX_FACTS):
        raise ValueError("Bounded nonempty fact inventory required")
    by_id = {}
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {"id", "predicate", "bindings"}:
            raise ValueError("Invalid typed fact schema")
        fid, predicate, bindings = fact["id"], fact["predicate"], fact["bindings"]
        if (not isinstance(fid, str) or not ATOM.fullmatch(fid)
                or fid in by_id or not isinstance(predicate, str)
                or not ATOM.fullmatch(predicate)
                or not isinstance(bindings, list)
                or not 1 <= len(bindings) <= MAX_BINDINGS):
            raise ValueError("Invalid or duplicate fact ID, predicate or bindings")
        roles = set()
        normal = []
        for binding in bindings:
            if (not isinstance(binding, dict)
                    or set(binding) != {"role", "entity", "span"}):
                raise ValueError("Invalid role binding schema")
            role, entity = binding["role"], binding["entity"]
            if (not isinstance(role, str) or not ATOM.fullmatch(role)
                    or role in roles or not isinstance(entity, str)
                    or not ENTITY.fullmatch(entity)):
                raise ValueError("Duplicate role or invalid entity identity")
            roles.add(role)
            quote = _span(document, binding["span"])
            normal.append({
                "role": role, "entity": entity,
                "quote_sha256": sha256(quote.encode("utf-8")).hexdigest(),
            })
        by_id[fid] = {
            "id": fid,
            "predicate": predicate,
            "binding_values": {x["role"]: x["entity"] for x in normal},
            "anchor_hashes": {x["role"]: x["quote_sha256"] for x in normal},
        }
    return by_id


def audit_typed_role_graph(*, source: str, candidate: str,
                           source_facts: list[dict],
                           candidate_facts: list[dict],
                           source_sha256: str, candidate_sha256: str,
                           source_inventory_sha256: str,
                           candidate_inventory_sha256: str) -> dict:
    """Audit two explicit source-anchored role graphs; never admit meaning.

    The facts are annotations, not NLP output certified by this function.
    Hashes make a record reproducible; only external signed reviewer/custody
    workflows can authenticate who approved these annotations.
    """
    if (not isinstance(source, str) or not isinstance(candidate, str)
            or not source or not candidate
            or len(source.encode("utf-8")) > MAX_DOC_BYTES
            or len(candidate.encode("utf-8")) > MAX_DOC_BYTES):
        raise ValueError("Bounded original and candidate text required")
    if (sha256(source.encode()).hexdigest() != source_sha256
            or sha256(candidate.encode()).hexdigest() != candidate_sha256
            or digest(source_facts) != source_inventory_sha256
            or digest(candidate_facts) != candidate_inventory_sha256):
        raise ValueError("Source/candidate or role inventory version mismatch")
    before = _facts(source, source_facts, side="source")
    after = _facts(candidate, candidate_facts, side="candidate")
    findings = []
    refused = False
    for fid in sorted(set(before) | set(after)):
        a, b = before.get(fid), after.get(fid)
        if a is None:
            status = "ADDED_FACT_UNREVIEWED"
        elif b is None:
            status = "REQUIRED_FACT_MISSING"
        elif a["predicate"] != b["predicate"]:
            status = "PREDICATE_CHANGED"
        elif a["binding_values"] != b["binding_values"]:
            status = "ROLE_BINDING_CHANGED"
        else:
            status = "DECLARED_ROLE_BINDINGS_PRESERVED"
        if status in ("REQUIRED_FACT_MISSING", "PREDICATE_CHANGED",
                      "ROLE_BINDING_CHANGED"):
            refused = True
        findings.append({
            "id":fid,
            "status":status,
            "predicate_before":a["predicate"] if a else None,
            "predicate_after":b["predicate"] if b else None,
            "changed_roles":sorted(
                role for role in set(a["binding_values"]) | set(b["binding_values"])
                if a["binding_values"].get(role) != b["binding_values"].get(role)
            ) if status == "ROLE_BINDING_CHANGED" else [],
            "anchor_verification":"EXACT_SUBSTRING_ONLY",
            "semantic_identity_independently_verified":False,
        })
    receipt = {
        "schema": SCHEMA,
        "source_sha256": source_sha256,
        "candidate_sha256":candidate_sha256,
        "source_inventory_sha256":source_inventory_sha256,
        "candidate_inventory_sha256":candidate_inventory_sha256,
        "source_facts":len(before),
        "candidate_facts":len(after),
        "findings":findings,
        "verdict":"REFUSE" if refused else "INCONCLUSIVE",
        "qualityrag_admission":"INCONCLUSIVE",
        "can_generate":False,
        "semantic_completeness":"UNKNOWN",
        "source_authority":"NOT_ESTABLISHED",
        "annotation_authority":"NOT_AUTHENTICATED",
        "boundary":"Explicit role facts, not inferred sentence meaning; unannotated changes may be missed",
    }
    receipt["fingerprint"]=digest(receipt)
    return receipt
