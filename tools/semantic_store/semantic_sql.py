"""Small, read-only SQL-like surface over the existing bounded semantic graph API.

This is NOT a general SQL engine or an authoritative semantic reasoner. A query
must specify an exact object and revision, so there is no unbounded table scan.
Only literal equality predicates in the declared grammar are accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from query import query_context
from store import SemanticStore

# No interpolation into SQL: this parser builds a typed plan, and the graph
# API handles parameterized persistence access plus per-object authorization.
_GRAMMAR = re.compile(
    r"""\A\s*SELECT\s+\*\s+FROM\s+facts\s+WHERE\s+
    object_id\s*=\s*'(?P<object_id>(?:''|[^'])*)'\s+AND\s+
    revision\s*=\s*'(?P<revision>(?:''|[^'])*)'
    (?:\s+AND\s+layer\s*=\s*'(?P<layer>KNOWLEDGE|WITNESS|REGIME)')?
    (?:\s+GOVERNED\s+BY\s+(?P<packspec>[A-Za-z][A-Za-z0-9_-]{0,127}))?
    (?:\s+(?:(?P<expand>EXPAND)(?:\s+(?P<hops>[0-5]))?|(?P<collapse>COLLAPSE)))?
    (?:\s+LIMIT\s+(?P<limit>[0-9]+))?
    \s*;?\s*\Z""",
    re.IGNORECASE | re.VERBOSE,
)
_ALLOWED_LAYER = {"KNOWLEDGE", "WITNESS", "REGIME"}


class SemanticSqlError(ValueError):
    pass


@dataclass(frozen=True)
class SemanticQueryPlan:
    object_id: str
    revision: str
    layers: tuple[str, ...]
    max_nodes: int
    max_hops: int = 1
    governance_ref: str | None = None
    projection: str = "CONTEXT"

    def as_dict(self) -> dict:
        return {
            "schema": "qualityrag.semantic-sql-plan/v0.1",
            "operation": "BOUNDED_GRAPH_CONTEXT",
            "root": {"object_id": self.object_id, "revision": self.revision},
            "layers": list(self.layers),
            "limits": {"max_nodes": self.max_nodes, "max_hops": self.max_hops},
            "read_only": True,
            "governance": {"reference": self.governance_ref, "evaluation": "NOT_PERFORMED"},
            "projection": self.projection,
        }


def compile_sql(statement: str) -> SemanticQueryPlan:
    """Compile the tiny SQL-like subset into an explicit typed execution plan."""
    if not isinstance(statement, str) or len(statement) > 4096:
        raise SemanticSqlError("Query must be text up to 4096 characters")
    match = _GRAMMAR.fullmatch(statement)
    if not match:
        raise SemanticSqlError(
            "Supported: SELECT * FROM facts WHERE object_id = 'id' "
            "AND revision = 'rev' [AND layer = 'KNOWLEDGE|WITNESS|REGIME'] "
            "[GOVERNED BY packspec1] [EXPAND [0..5] | COLLAPSE] [LIMIT 1..100];"
        )
    obj = match["object_id"].replace("''", "'")
    rev = match["revision"].replace("''", "'")
    if not obj.strip() or not rev.strip() or len(obj) > 256 or len(rev) > 256:
        raise SemanticSqlError("Non-empty object_id and revision of at most 256 chars required")
    bound = int(match["limit"] or "30")
    if bound < 1 or bound > 100:
        raise SemanticSqlError("LIMIT must be between 1 and 100")
    layer = match["layer"].upper() if match["layer"] else None
    if layer is not None and layer not in _ALLOWED_LAYER:
        raise SemanticSqlError("Unknown semantic layer")
    return SemanticQueryPlan(
        object_id=obj, revision=rev,
        layers=(layer,) if layer else ("KNOWLEDGE", "WITNESS"),
        max_nodes=bound,
        max_hops=int(match["hops"] or "1") if match["expand"] else 0 if match["collapse"] else 1,
        governance_ref=match["packspec"],
        projection="COLLAPSE" if match["collapse"] else "EXPAND" if match["expand"] else "CONTEXT",
    )


def execute_sql(
    store: SemanticStore,
    statement: str,
    *,
    principal: str,
    authorize: Callable[[str, str, str], bool],
    resolve_packspec: Callable[[str, str], dict] | None = None,
) -> dict:
    """Execute only via authorized graph context; never forward raw SQL."""
    plan = compile_sql(statement)
    binding = None
    if plan.governance_ref is not None:
        if not callable(resolve_packspec):
            raise SemanticSqlError("GOVERNED BY requires an authenticated PackSpec resolver; refusing ungoverned execution")
        binding = resolve_packspec(principal, plan.governance_ref)
        if not (isinstance(binding, dict)
                and binding.get("id") == plan.governance_ref
                and isinstance(binding.get("digest"), str)
                and len(binding["digest"]) == 64
                and all(x in "0123456789abcdef" for x in binding["digest"])
                and binding.get("authorized") is True):
            raise PermissionError("Requested PackSpec is missing, unauthorized or has no revision digest")
        # Binding establishes which reviewed policy was selected; it does not
        # execute policy evaluation or prove any semantic projection loss-safe.
    result = query_context(
        store, principal=principal, authorize=authorize,
        object_id=plan.object_id, revision=plan.revision,
        max_hops=plan.max_hops, max_nodes=plan.max_nodes,
        layers=plan.layers,
    )
    if plan.projection == "COLLAPSE":
        # Structural display only: no semantic compression or omission license.
        result = dict(result)
        result["edges"] = []
        result["nodes"] = result["nodes"][:1]
        result["limits"] = dict(result.get("limits", {}),
                                projection_truncated=True)
        result["projection_warning"] = "STRUCTURAL_ROOT_ONLY_NOT_MEANING_PRESERVING"
    return {"schema": "qualityrag.semantic-sql-result/v0.1",
            "plan": plan.as_dict(),
            "result": result,
            "packspec_binding": ({"id": binding["id"], "digest": binding["digest"],
                                   "evaluation": "NOT_PERFORMED"} if binding else None),
            "admission": "INCONCLUSIVE",
            "can_generate": False}
