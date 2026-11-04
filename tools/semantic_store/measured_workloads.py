"""Measured finite repeated-workload experiment, not a modeled break-even claim.

Runs on PRIVATE temporary copies of a supplied, reviewed flat image directory:
 - durable SQLite filename metadata baseline,
 - existing Semantic Codex source + optional vision-text vectors,
 - first-in-process and repeated alternating-order queries,
 - one explicitly specified pixel update and physical SQLite storage changes.
The two arms have different information capabilities. Media inference model
loading, verification, energy, environment variability and person identity
are not measured or certified.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path
import shutil
import sqlite3
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from PIL import Image

from paired_benchmark import _validate_manifest, _scores
from directory_codex import index_directory
from semantic_codex import CodexError
from store import SemanticStore, digest
from visual_semantic import index_visual_semantics, find_visual_scenes

SCHEMA = "qualityrag.measured-workload/v0.9"


def _timed(fn):
    begin=perf_counter_ns()
    result=fn()
    return result,(perf_counter_ns()-begin)/1_000_000


def _stats(samples):
    if not samples:
        raise CodexError("Missing measured query samples")
    ordered=sorted(samples)
    return {"count":len(samples),"median_ms":round(median(samples),6),
            "min_ms":round(ordered[0],6),
            "p95_nearest_rank_ms":round(ordered[math.ceil(.95*len(samples))-1],6),
            "max_ms":round(ordered[-1],6)}


def _database_bytes(path: Path, db: sqlite3.Connection) -> int:
    # Force WAL checkpoint only if used (these experiments use default journaling).
    db.commit()
    return path.stat().st_size


def _update_png(source: Path):
    """Modify a temporary image at a known pixel, preserving name and dimensions."""
    with Image.open(source) as raw:
        image=raw.convert("RGB")
        if image.width<2 or image.height<2:
            raise CodexError("Fixture image too small")
        r,g,b=image.getpixel((0,0))
        image.putpixel((0,0),((r+127)%256,g,b))
        out=BytesIO()
        image.save(out,format="PNG")
    source.write_bytes(out.getvalue())


def run_measured_workload(root: Path, manifest: dict, *, encoder,
                          principal: str, authorize_source,
                          repetitions: int = 5, k: int = 1,
                          update_path: str | None = None) -> dict:
    items, queries=_validate_manifest(manifest)
    if (type(repetitions) is not int or not 2<=repetitions<=40
            or type(k) is not int or not 1<=k<=len(items)
            or not principal or not callable(authorize_source)):
        raise CodexError("Invalid bounded measurement configuration")
    if not isinstance(root,Path) or root.is_symlink() or not root.is_dir():
        raise CodexError("Expected regular local directory")
    declared={item["path"] for item in items}
    if not declared:
        raise CodexError("Empty source inventory")
    if update_path is not None and (
        update_path not in declared or Path(update_path).suffix.lower()!=".png"):
        raise CodexError("The mutation experiment needs an existing PNG in the manifest")
    actual={p.name for p in root.iterdir() if p.is_file()}
    if actual != declared:
        raise CodexError("Directory must contain exactly the labeled image files")
    if any((root/name).is_symlink() or (root/name).stat().st_size>2_000_000
           for name in declared):
        raise CodexError("Symlink or oversized source")
    with TemporaryDirectory(prefix="qualityrag-measured-") as tmp:
        work=Path(tmp)
        images=work/"media"
        images.mkdir()
        for name in sorted(declared):
            # Re-check symlink after the inventory check: benchmark operates on
            # temporary copies and never mutates the user's originals.
            src=root/name
            if src.is_symlink():
                raise CodexError("Source symlink not allowed")
            shutil.copyfile(src,images/name,follow_symlinks=False)
        baseline_path=work/"filename.sqlite3"
        visual_path=work/"visual.sqlite3"
        base=sqlite3.connect(baseline_path)
        visual_db=sqlite3.connect(visual_path)
        store=SemanticStore(visual_db)
        store.initialize()
        try:
            base.execute("CREATE TABLE filenames(name TEXT PRIMARY KEY, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL)")
            def filename_index():
                base.executemany("INSERT INTO filenames VALUES(?,?,?)",[
                    (name,(images/name).stat().st_size,(images/name).stat().st_mtime_ns)
                    for name in sorted(declared)])
                base.commit()
            _,base_index_ms=_timed(filename_index)
            def visual_index():
                result=index_directory(store,images,namespace="bench",
                    principal=principal,authorize_source=authorize_source)
                if (result["truncated"] or result["coverage"]["indexed"]!=len(items)
                        or result["coverage"]["failed"] or result["coverage"]["denied"]
                        or result["coverage"]["unsupported"]):
                    raise CodexError("Incomplete source indexing")
                second=index_visual_semantics(store,images,namespace="bench",
                    principal=principal,authorize_source=authorize_source,
                    encoder=encoder)
                if (second["truncated"] or second["failed_sources"]
                        or second["indexed_sources"]!=len(items)):
                    raise CodexError("Incomplete visual indexing")
            _,visual_index_ms=_timed(visual_index)
            before={"filename_database_bytes":_database_bytes(baseline_path,base),
                    "visual_database_bytes":_database_bytes(visual_path,visual_db)}
            runs=[]
            baseline_times=[]
            visual_times=[]
            for rep in range(repetitions):
                for query in queries:
                    qid,prompt,terms=query["id"],query["prompt"],query["lexical_terms"]
                    truth={item["path"]:item["relevance"][qid] for item in items}
                    def lex():
                        names=[r[0] for r in base.execute("SELECT name FROM filenames")]
                        return sorted(names,key=lambda name:(
                            -sum(t.casefold() in name.casefold() for t in terms),name))
                    def vis():
                        result=find_visual_scenes(store,prompt,namespace="bench",
                            principal=principal,authorize_source=authorize_source,
                            encoder=encoder,max_hits=100,max_records=600)
                        if (result["truncated"] or
                                result["evaluated_authorized_frames"]!=len(items) or
                                len(result["results"])!=len(items)):
                            raise CodexError("Incomplete visual query result")
                        return [h["source_id"].removeprefix("bench/") for h in result["results"]]
                    # Alternating order mitigates (but does not remove) cache
                    # effects, which are explicitly disclosed in the receipt.
                    if rep%2:
                        order_visual,vm=_timed(vis)
                        order_base,bm=_timed(lex)
                    else:
                        order_base,bm=_timed(lex)
                        order_visual,vm=_timed(vis)
                    baseline_times.append(bm)
                    visual_times.append(vm)
                    runs.append({"repetition":rep,"query_id":qid,
                        "first_in_process":rep==0,
                        "filename_query_ms":round(bm,6),
                        "visual_query_ms":round(vm,6),
                        "filename_quality":_scores(order_base,truth,k=k),
                        "visual_quality":_scores(order_visual,truth,k=k)})
            updates=None
            after=None
            if update_path is not None:
                target=images/update_path
                _,mutation_ms=_timed(lambda:_update_png(target))
                def update_base():
                    stat=target.stat()
                    base.execute("UPDATE filenames SET size_bytes=?,mtime_ns=? WHERE name=?",
                                 (stat.st_size,stat.st_mtime_ns,update_path))
                    base.commit()
                _,base_update_ms=_timed(update_base)
                def update_visual():
                    indexed=index_directory(store,images,namespace="bench",
                        principal=principal,authorize_source=authorize_source)
                    if (indexed["truncated"] or indexed["coverage"]["indexed"]!=1
                            or indexed["coverage"]["failed"] or indexed["coverage"]["denied"]):
                        raise CodexError("Unexpected changed-source indexing")
                    vectors=index_visual_semantics(store,images,namespace="bench",
                        principal=principal,authorize_source=authorize_source,
                        encoder=encoder)
                    if (vectors["truncated"] or vectors["failed_sources"]
                            or vectors["indexed_sources"]!=1):
                        raise CodexError("Updated visual indexing incomplete")
                _,visual_update_ms=_timed(update_visual)
                updates={"changed_source":update_path,
                         "mutation_ms_shared_excluded_from_update_comparison":round(mutation_ms,6),
                         "filename_metadata_update_ms":round(base_update_ms,6),
                         "codex_and_visual_incremental_index_ms":round(visual_update_ms,6),
                         "version_retention":"APPEND_ONLY_VISUAL_LEDGER"}
                after={"filename_database_bytes":_database_bytes(baseline_path,base),
                       "visual_database_bytes":_database_bytes(visual_path,visual_db)}
            return {
                "schema":SCHEMA,"dataset_fingerprint":digest(manifest),
                "dataset_label_provenance":"CALLER_SUPPLIED_UNVERIFIED",
                "model_id":encoder.model_id,
                "scope":"TEMPORARY_FLAT_IMAGE_COPIES_ONLY",
                "file_count":len(items),"query_count":len(queries),
                "repetitions":repetitions,"k":k,
                "initial_index_ms":{"filename_metadata":round(base_index_ms,6),
                                    "codex_and_visual":round(visual_index_ms,6)},
                "query_samples":runs,
                "cold_first_in_process":{"filename_ms":round(baseline_times[0],6),
                                         "visual_ms":round(visual_times[0],6),
                                         "not_a_new_process":True},
                "warm_query_latency":{"filename":_stats(baseline_times[len(queries):]),
                                      "visual":_stats(visual_times[len(queries):])},
                "storage_after_initial_index":before,
                "source_update":updates,"storage_after_update":after,
                "verification_time":"NOT_MEASURED",
                "model_initialization":"EXCLUDED",
                "energy_network_reviewer_cost":"NOT_MEASURED",
                "full_lifecycle_cost":"NOT_ESTABLISHED",
                "capability_parity":"NOT_ESTABLISHED_FILENAME_ONLY_BASELINE",
                "source_authenticity":"UNVERIFIED",
                "identity_recognition":"NOT_PERFORMED",
                "admission":"INCONCLUSIVE","can_generate":False,
            }
        finally:
            base.close()
            visual_db.close()
