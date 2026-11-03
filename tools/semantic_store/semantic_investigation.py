"""Research-only semantic SQL investigation clauses atop the v0.1 typed plan.

TRACE EVIDENCE     traverses the WITNESS graph only, subject to per-object ACL.
COMPARE WITH 'v2'  compares authorized, bounded structural snapshots.
FIND GAPS          lists required object IDs *unobserved in a bounded view*,
                   not missing real-world facts or semantic incompleteness.

No statement executes arbitrary SQL, asserts source truth, signs policy, or
authorizes publication. This is not native WBC/HCR/RCOC/FF-RCT execution.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import re
from typing import Callable

from semantic_sql import SemanticSqlError, SemanticQueryPlan, compile_sql, execute_sql
from query import query_context
from store import SemanticStore, canonical_bytes

_SUFFIX = re.compile(
    r"""\s+(?P<op>TRACE\s+EVIDENCE|FIND\s+GAPS|COMPARE\s+WITH\s+'(?P<revision>(?:''|[^'])*)')\s*;?\s*\Z""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InvestigationPlan:
    base: SemanticQueryPlan
    operation: str
    comparison_revision: str | None = None

    def as_dict(self) -> dict:
        base = self.base.as_dict()
        base.update(schema="qualityrag.semantic-investigation-plan/v0.2",
                    operation=self.operation,
                    comparison_revision=self.comparison_revision,
                    assurance="RESEARCH_ONLY")
        return base


def compile_investigation(statement: str) -> InvestigationPlan:
    if not isinstance(statement, str) or len(statement) > 4096:
        raise SemanticSqlError("Query must be text up to 4096 characters")
    match = _SUFFIX.search(statement)
    if not match:
        raise SemanticSqlError("Expected TRACE EVIDENCE, COMPARE WITH 'revision', or FIND GAPS")
    base_statement = statement[:match.start()]
    base = compile_sql(base_statement)
    operator = match["op"].upper()
    if operator.startswith("TRACE"):
        if base.projection == "COLLAPSE":
            raise SemanticSqlError("TRACE EVIDENCE cannot follow a collapsed view")
        base = replace(base, layers=("WITNESS",))
        operation = "TRACE_EVIDENCE"
    elif operator.startswith("FIND"):
        if base.projection == "COLLAPSE":
            raise SemanticSqlError("FIND GAPS requires an uncollapsed bounded context")
        if not base.governance_ref:
            raise SemanticSqlError("FIND GAPS requires GOVERNED BY an authorized PackSpec")
        operation = "FIND_GAPS"
    else:
        if base.projection == "COLLAPSE":
            raise SemanticSqlError("COMPARE WITH requires an uncollapsed bounded context")
        revision = match["revision"].replace("''", "'")
        if not revision.strip() or len(revision) > 256:
            raise SemanticSqlError("Comparison revision must be 1..256 characters")
        operation = "COMPARE_WITH"
        return InvestigationPlan(base, operation, revision)
    return InvestigationPlan(base, operation)


def _binding(principal: str, ref: str, resolve_packspec: Callable | None) -> dict:
    if not callable(resolve_packspec):
        raise SemanticSqlError("GOVERNED BY requires authenticated PackSpec resolution")
    binding = resolve_packspec(principal, ref)
    if not (isinstance(binding, dict)
            and binding.get("id") == ref
            and binding.get("authorized") is True
            and isinstance(binding.get("digest"), str)
            and re.fullmatch("[0-9a-f]{64}", binding["digest"])):
        raise PermissionError("Unauthorized, mismatched or unversioned PackSpec")
    return binding


def _context(store, plan, principal, authorize, revision):
    return query_context(store, principal=principal, authorize=authorize,
                         object_id=plan.object_id, revision=revision,
                         max_nodes=plan.max_nodes, max_hops=plan.max_hops,
                         layers=plan.layers)


def execute_investigation(
    store: SemanticStore,
    statement: str,
    *,
    principal: str,
    authorize: Callable[[str, str, str], bool],
    resolve_packspec: Callable[[str, str], dict] | None = None,
) -> dict:
    plan = compile_investigation(statement)
    base = plan.base
    binding = _binding(principal, base.governance_ref, resolve_packspec) if base.governance_ref else None
    if plan.operation == "FIND_GAPS":
        # A trusted caller must supply a reviewed finite inventory of IDs. It
        # cannot be inferred from arbitrary text, and not seeing a node in a
        # bounded traversal does not demonstrate that it is missing globally.
        inventory = binding.get("required_object_ids")
        if not (isinstance(inventory, list) and len(inventory) <= 100
                and all(isinstance(x, str) and 0 < len(x) <= 256 for x in inventory)
                and len(set(inventory)) == len(inventory)):
            raise SemanticSqlError("PackSpec must supply a unique finite required_object_ids inventory (max 100)")
    root = _context(store, base, principal, authorize, base.revision)
    receipt = {
        "schema": "qualityrag.semantic-investigation-result/v0.2",
        "plan": plan.as_dict(),
        "admission": "INCONCLUSIVE",
        "verification": "NOT_PERFORMED",
        "can_generate": False,
        "packspec_binding": (
            {"id":binding["id"],"digest":binding["digest"],"evaluation":"NOT_PERFORMED"}
            if binding is not None else None
        ),
    }
    if plan.operation == "TRACE_EVIDENCE":
        receipt["result"] = root
        receipt["interpretation"] = "AUTHORIZED_WITNESS_EDGES_NOT_CORROBORATION"
        return receipt
    if plan.operation == "COMPARE_WITH":
        other = _context(store, base, principal, authorize, plan.comparison_revision)
        if root.get("status") == "NOT_FOUND" or other.get("status") == "NOT_FOUND":
            receipt["comparison"] = {
                "status": "INCONCLUSIVE_MISSING_VERSION",
                "base_revision": base.revision,
                "other_revision": plan.comparison_revision,
                "scope": "NO_DIFFERENCE_INFERENCE_FROM_ABSENT_VERSION",
            }
            return receipt
        # Comparing revision-specific versions by stable object_id. This is a
        # *structural payload* diff, not a semantic or RCOC verdict.
        old_by_id={n["object_id"]:sha256(canonical_bytes(n["payload"])).hexdigest() for n in root["nodes"]}
        new_by_id={n["object_id"]:sha256(canonical_bytes(n["payload"])).hexdigest() for n in other["nodes"]}
        shared=set(old_by_id)&set(new_by_id)
        receipt["comparison"] = {
            "base_revision":base.revision,
            "other_revision":plan.comparison_revision,
            "only_in_base":sorted(set(old_by_id)-set(new_by_id)),
            "only_in_other":sorted(set(new_by_id)-set(old_by_id)),
            "payload_changed":sorted(x for x in shared if old_by_id[x]!=new_by_id[x]),
            "payload_unchanged":sorted(x for x in shared if old_by_id[x]==new_by_id[x]),
            "base_truncated":root.get("limits",{}).get("truncated",True),
            "other_truncated":other.get("limits",{}).get("truncated",True),
            "scope":"BOUNDED_AUTHORIZED_STRUCTURAL_DIFF_NOT_SEMANTIC_EQUIVALENCE",
        }
        return receipt
    observed={n["object_id"] for n in root["nodes"]}
    # Never return an unauthorized node ID just because an authorized policy
    # happened to name it. If caller cannot read it, mark policy check blocked.
    inaccessible=[x for x in inventory if not authorize(principal,x,base.revision)]
    if inaccessible:
        receipt["gap_analysis"]={
            "status":"INCONCLUSIVE_ACCESS_RESTRICTION",
            "required_count":len(inventory),
            "unobserved_ids":[],
            "warning":"Authorization prevented a complete inventory comparison",
        }
        return receipt
    receipt["gap_analysis"]={
        "status":"BOUNDED_PRESENCE_ONLY",
        "required_count":len(inventory),
        "observed_required_ids":sorted(x for x in inventory if x in observed),
        "unobserved_ids":sorted(x for x in inventory if x not in observed),
        "truncated":root.get("limits",{}).get("truncated",True),
        "warning":"Unobserved means absent from returned authorized graph context, not absent from source or universe",
    }
    return receipt
