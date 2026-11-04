"""Paired, scope-matched lexical-vs-visual retrieval experiment.

Uses existing immutable directory Codex and optional contrastive encoder.
A supplied label manifest is NOT independently authenticated. Only eligible,
fully indexed and labeled IMAGE records are scored; videos await frame-level
ground truth and are explicitly out of scope for this v0.7 experiment.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from typing import Any

from directory_codex import index_directory
from semantic_codex import CodexError
from store import SemanticStore, digest
from visual_codex import IMAGE_FORMATS
from visual_semantic import index_visual_semantics, find_visual_scenes

SCHEMA="qualityrag.paired-visual-benchmark/v0.7"
MAX_ITEMS=50
MAX_QUERIES=20


def _validate_manifest(manifest: dict) -> tuple[list[dict],list[dict]]:
    if (not isinstance(manifest,dict) or set(manifest)!={"schema","items","queries"}
            or manifest["schema"]!="qualityrag.paired-benchmark-input/v0.7"):
        raise CodexError("Invalid paired benchmark manifest schema")
    items,queries=manifest["items"],manifest["queries"]
    if (not isinstance(items,list) or not 2<=len(items)<=MAX_ITEMS
            or not isinstance(queries,list) or not 1<=len(queries)<=MAX_QUERIES):
        raise CodexError("Unbounded benchmark inventory")
    names=set()
    for item in items:
        if not isinstance(item,dict) or set(item)!={"path","relevance"}:
            raise CodexError("Expected file path and per-query relevance map")
        name=item["path"]
        if (not isinstance(name,str) or not name or
                Path(name).name!=name or name.startswith(".")
                or Path(name).suffix.lower().lstrip(".") not in IMAGE_FORMATS
                or name in names):
            raise CodexError("Only unique flat image filenames permitted")
        names.add(name)
    query_ids=set()
    for query in queries:
        if (not isinstance(query,dict) or set(query)!={"id","prompt","lexical_terms"}
                or not isinstance(query["id"],str) or not 1<=len(query["id"])<=80
                or query["id"] in query_ids
                or not isinstance(query["prompt"],str) or not 1<=len(query["prompt"].strip())<=256
                or not isinstance(query["lexical_terms"],list)
                or not 1<=len(query["lexical_terms"])<=10
                or any(not isinstance(x,str) or not x.strip() or len(x)>80
                       for x in query["lexical_terms"])):
            raise CodexError("Invalid query and predefined lexical baseline")
        query_ids.add(query["id"])
    for item in items:
        if set(item["relevance"])!=query_ids or any(v not in ("RELEVANT","NOT_RELEVANT","UNCERTAIN")
                                                      for v in item["relevance"].values()):
            raise CodexError("Every eligible image needs a label for every query")
    return items,queries


def _scores(order: list[str], truth: dict[str,str], *, k: int) -> dict:
    # Only a complete ordering of a complete labeled universe qualifies for recall.
    if len(order)!=len(truth) or set(order)!=set(truth) or len(order)!=len(set(order)):
        raise CodexError("Missing, duplicate or inaccessible candidate in paired evaluation")
    if "UNCERTAIN" in truth.values():
        return {"status":"INCONCLUSIVE_UNCERTAIN_LABELS",
                "precision_at_k":None,"recall_at_k":None}
    top=order[:k]
    relevant=sum(x=="RELEVANT" for x in truth.values())
    hits=sum(truth[x]=="RELEVANT" for x in top)
    return {"status":"FINITE_LABELED_EVALUATION",
            "precision_at_k":hits/len(top) if top else None,
            "recall_at_k":hits/relevant if relevant else None,
            "relevant_in_pool":relevant}


def compare_directory(
    root: Path, manifest: dict, *, encoder,
    principal: str, authorize_source, k: int = 5,
) -> dict:
    """Compare lexical filenames vs semantic pixels on precisely same set.

    Timings are measurements of this run, not isolated CPU benchmarking.
    'bytes_read' is explicit source-byte accounting for index phases only;
    query data and model-load time are NOT included. No model score is a fact.
    """
    items,queries=_validate_manifest(manifest)
    if type(k) is not int or not 1<=k<=len(items):
        raise CodexError("k exceeds finite pool")
    if not principal or not callable(authorize_source):
        raise PermissionError("Explicit source authorization required")
    if not isinstance(root,Path) or not root.is_dir() or root.is_symlink():
        raise CodexError("Local directory not found")
    root=root.resolve(strict=True)
    declared={x["path"] for x in items}
    present={p.name for p in root.iterdir() if p.is_file() and
             p.suffix.lower().lstrip(".") in IMAGE_FORMATS}
    if declared!=present:
        raise CodexError("Manifest inventory does not equal eligible image directory")
    with TemporaryDirectory() as temp:
        store=SemanticStore(sqlite3.connect(":memory:"))
        store.initialize()
        try:
            indexed_at=perf_counter_ns()
            directory=index_directory(store,root,namespace="bench",
                            principal=principal,authorize_source=authorize_source,
                            max_files=200)
            directory_ms=(perf_counter_ns()-indexed_at)/1_000_000
            if (directory["truncated"] or directory["coverage"]["failed"]
                    or directory["coverage"]["denied"]
                    or directory["coverage"]["indexed"]!=len(items)
                    or directory["coverage"]["unsupported"]):
                raise CodexError("Incomplete directory indexing prevents comparison")
            # Indexing records may include document types besides images. The
            # manifest guarantees image-only membership.
            visual_at=perf_counter_ns()
            semantic_index=index_visual_semantics(
                store,root,namespace="bench",principal=principal,
                authorize_source=authorize_source,encoder=encoder,max_sources=100)
            visual_ms=(perf_counter_ns()-visual_at)/1_000_000
            if (semantic_index["truncated"] or semantic_index["failed_sources"]
                    or semantic_index["indexed_sources"]!=len(items)):
                raise CodexError("Incomplete semantic visual indexing prevents comparison")
            baseline=[]
            semantic=[]
            query_timings=[]
            for query in queries:
                qid,prompt,terms=query["id"],query["prompt"],query["lexical_terms"]
                truth={x["path"]:x["relevance"][qid] for x in items}
                # Conventional baseline only sees filenames. It cannot know image pixels.
                start=perf_counter_ns()
                lexical_rank=sorted(declared,
                    key=lambda name:(-sum(t.casefold() in name.casefold() for t in terms),name))
                lexical_ms=(perf_counter_ns()-start)/1_000_000
                start=perf_counter_ns()
                visual=find_visual_scenes(
                    store,prompt,namespace="bench",principal=principal,
                    authorize_source=authorize_source,encoder=encoder,
                    max_hits=100,max_records=600)
                semantic_ms=(perf_counter_ns()-start)/1_000_000
                if (visual["truncated"] or visual["evaluated_authorized_frames"]!=len(items)
                        or len(visual["results"])!=len(items)):
                    raise CodexError("Model candidate coverage incomplete")
                semantic_rank=[x["source_id"].removeprefix("bench/")
                               for x in visual["results"]]
                baseline.append({"query_id":qid,**_scores(lexical_rank,truth,k=k)})
                semantic.append({"query_id":qid,**_scores(semantic_rank,truth,k=k)})
                query_timings.append({"query_id":qid,"filename_lexical_ms":round(lexical_ms,4),
                                      "visual_query_ms":round(semantic_ms,4)})
            report={
                "schema":SCHEMA,"dataset_label_provenance":"CALLER_SUPPLIED_UNVERIFIED",
                "dataset_fingerprint":digest(manifest),
                "model_id":encoder.model_id,
                "scope":"FLAT_IMAGE_FILES_ONLY_COMPLETE_FINITE_LABELED_POOL",
                "file_count":len(items),"query_count":len(queries),"k":k,
                "baseline":"FILENAME_TOKEN_MATCH_NOT_FULL_TEXT_OR_CONTENT_SEARCH",
                "baseline_metrics":baseline,"visual_metrics":semantic,
                "timings":{"directory_index_ms":round(directory_ms,3),
                           "visual_index_ms":round(visual_ms,3),
                           "queries":query_timings,
                           "method":"WALL_CLOCK_NON_ISOLATED_ONE_RUN",
                           "model_initialization_included":False},
                "source_bytes_indexed":directory["coverage"]["bytes_indexed"],
                "source_reads_for_visual_embedding":"NOT_INSTRUMENTED",
                "total_cost_comparison":"NOT_ESTABLISHED",
                "identity_recognition":"NOT_PERFORMED",
                "generalization":"UNMEASURED",
                "admission":"INCONCLUSIVE","can_generate":False,
            }
            return report
        finally:
            store.db.close()
