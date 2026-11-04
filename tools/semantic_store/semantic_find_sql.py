"""SQL-like FIND surface for indexed Semantic Codex directories.

The grammar is intentionally small and deterministic, not general SQL or
natural-language identity inference. Queries operate only on already indexed
records under an explicit source-level authorizer.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Callable

from directory_codex import search_store
from semantic_codex import CodexError
from store import SemanticStore

_PATTERN = re.compile(
    r"""\A\s*FIND\s+'(?P<term>(?:''|[^'])*)'\s+IN\s+'(?P<namespace>(?:''|[^'])*)'
    (?:\s+LIMIT\s+(?P<limit>[0-9]+))?\s*;?\s*\Z""",
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class DirectoryFindPlan:
    term: str
    namespace: str
    max_hits: int

    def as_dict(self) -> dict:
        return {
            "schema": "qualityrag.directory-find-plan/v0.2",
            "operation": "INDEXED_LEXICAL_FIND",
            "term": self.term,
            "namespace": self.namespace,
            "max_hits": self.max_hits,
            "read_only": True,
            "source_coverage": "INDEXED_RECORDS_ONLY",
            "semantic_verification": "NOT_PERFORMED",
        }


def compile_find(statement: str) -> DirectoryFindPlan:
    if not isinstance(statement, str) or len(statement) > 4096:
        raise CodexError("FIND must be a string under 4097 characters")
    match = _PATTERN.fullmatch(statement)
    if not match:
        raise CodexError("Expected FIND 'term' IN 'namespace' [LIMIT 1..100];")
    term = match["term"].replace("''", "'")
    namespace = match["namespace"].replace("''", "'")
    max_hits = int(match["limit"] or "30")
    if not 1 <= max_hits <= 100:
        raise CodexError("FIND limit must be 1..100")
    # Allow arbitrary words inside the search term, but safe named namespaces.
    if not 1 <= len(term.strip()) <= 128:
        raise CodexError("FIND term must be 1..128 characters")
    if not (1 <= len(namespace) <= 80 and
            all(c.isascii() and (c.isalnum() or c in "-_") for c in namespace)):
        raise CodexError("FIND namespace must contain ASCII letters, digits, - or _")
    return DirectoryFindPlan(term, namespace, max_hits)


def execute_find(
    store: SemanticStore, statement: str, *,
    principal: str,
    authorize_source: Callable[[str, str, str], bool],
) -> dict:
    plan = compile_find(statement)
    result = search_store(
        store, plan.term, namespace=plan.namespace,
        principal=principal, authorize_source=authorize_source,
        max_hits=plan.max_hits)
    return {"schema": "qualityrag.directory-find-sql-result/v0.2",
            "plan": plan.as_dict(), "result": result,
            "admission": "INCONCLUSIVE", "can_generate": False}
