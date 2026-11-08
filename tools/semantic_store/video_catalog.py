"""Local authorized video evidence catalog for a future MCP adapter.

Only media within an allowlisted directory may be analyzed. Evidence is
candidate-only, never independently verified or a sufficient final answer.
No remote URLs, crawlers, platform scrapers or identity recognition.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from video_evidence import inspect_constraints, VideoEvidenceError

MAX_MEDIA_BYTES = 512 * 1024 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
TOKEN = re.compile(r"[\w-]{2,}", re.UNICODE)


class CatalogError(ValueError):
    pass


def _root(value: str) -> Path:
    root = Path(value).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise CatalogError("Authorized media root must be a directory")
    return root


def _within(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def permitted_media(root: str, relative_path: str) -> Path:
    base = _root(root)
    if not isinstance(relative_path, str) or not relative_path or Path(relative_path).is_absolute():
        raise CatalogError("Provide an approved relative file path")
    item = (base / relative_path).resolve(strict=True)
    if not _within(base, item) or not item.is_file() or item.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise CatalogError("Media outside allowlisted root or unsupported")
    if item.stat().st_size > MAX_MEDIA_BYTES:
        raise CatalogError("Media size budget exceeded")
    return item


def _catalog_dir(root: str) -> Path:
    base = _root(root)
    # Catalog cannot be redirected by a source URL, filename or arbitrary ID.
    out = base / ".video-evidence"
    if out.is_symlink():
        raise CatalogError("Refusing catalog symlink")
    out.mkdir(exist_ok=True)
    return out


def _artifact_id(source_id: str) -> str:
    if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
        raise CatalogError("Invalid source ID")
    return source_id


def write_evidence(root: str, artifact: dict) -> dict:
    if not isinstance(artifact, dict):
        raise CatalogError("Artifact must be a dictionary")
    inspect_constraints(artifact)  # validates canonical fingerprint and schema
    ident = _artifact_id(artifact["source"]["source_id"])
    directory = _catalog_dir(root)
    destination = directory / (ident + ".json")
    encoded = json.dumps(artifact, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise CatalogError("Artifact size budget exceeded")
    # Avoid silent replacement of a different source revision.
    if destination.exists():
        existing = read_evidence(root, ident)
        if existing["fingerprint"] != artifact["fingerprint"]:
            raise CatalogError("Source ID already exists with different evidence; use a new revision-qualified ID")
        return {"source_id": ident, "fingerprint": existing["fingerprint"], "status": "ALREADY_INDEXED"}
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=directory, prefix=".part-", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(encoded)
        os.replace(temp, destination)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return {"source_id": ident, "fingerprint": artifact["fingerprint"], "status": "INDEXED"}


def read_evidence(root: str, source_id: str) -> dict:
    file = _catalog_dir(root) / (_artifact_id(source_id) + ".json")
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_ARTIFACT_BYTES:
        raise CatalogError("Unknown or unsafe catalog entry")
    try:
        artifact = json.loads(file.read_text(encoding="utf-8"))
        inspect_constraints(artifact)
        return artifact
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise CatalogError("Invalid or modified evidence entry") from exc


def search_evidence(root: str, query: str, *, limit: int = 10, modality: str = "all",
                    source_ids: frozenset[str] | None = None) -> dict:
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 200:
        raise CatalogError("Query must be 2-200 characters")
    if type(limit) is not int or not 1 <= limit <= 30 or modality not in {"all", "audio", "video", "ocr", "sensor"}:
        raise CatalogError("Invalid search filters")
    terms = set(TOKEN.findall(query.lower()))
    if not terms:
        raise CatalogError("No searchable query terms")
    if source_ids is not None and (not isinstance(source_ids, frozenset) or
                                   any(not isinstance(v, str) for v in source_ids)):
        raise CatalogError("Invalid source filter")
    matches = []
    directory = _catalog_dir(root)
    for file in sorted(directory.glob("*.json"))[:1000]:
        if file.name in {"hybrid-index.json", "sources.json"} or file.is_symlink():
            continue
        if source_ids is not None and file.stem not in source_ids:
            continue
        try:
            artifact = read_evidence(root, file.stem)
        except CatalogError:
            continue
        for witness in artifact.get("witnesses", []):
            if modality != "all" and witness["modality"] != modality:
                continue
            hit = terms.intersection(TOKEN.findall(witness["text"].lower()))
            if not hit:
                continue
            interval = witness["interval"]
            matches.append({
                "source_id": artifact["source"]["source_id"],
                "revision": artifact["source"]["revision"],
                "media_sha256": artifact["source"]["media_sha256"],
                "witness_id": witness["id"],
                "modality": witness["modality"],
                "start_ms": interval["start_ms"],
                "end_ms": interval["end_ms"],
                "observation": witness["text"][:1000],
                "score_matched_terms": len(hit),
                "admission": "UNVERIFIED_OBSERVATION",
                "frame_sha256": witness.get("frame_sha256"),
            })
    matches.sort(key=lambda m: (-m["score_matched_terms"],m["source_id"],m["start_ms"],m["witness_id"]))
    return {"query":query,"search_type":"LEXICAL_BASELINE_NOT_SEMANTIC",
            "results":matches[:limit],"count":len(matches[:limit]),
            "governance":"Candidate results only; no assertions verified; unobserved does not mean absent"}


def analyze_authorized_media(root: str, relative_path: str, *, source_id: str,
                             revision: str = "r1", asr_model: str | None = None,
                             vision_model: str | None = None,
                             interval_ms: int = 5000, max_frames: int = 60) -> dict:
    media = permitted_media(root, relative_path)
    if asr_model is None and vision_model is None:
        raise CatalogError("Explicit ASR or vision model selection required")
    if not isinstance(revision, str) or not 1 <= len(revision) <= 80:
        raise CatalogError("Invalid revision")
    if type(interval_ms) is not int or not 1000 <= interval_ms <= 60000 or type(max_frames) is not int or not 1 <= max_frames <= 120:
        raise CatalogError("Inference budget exceeded")
    _artifact_id(source_id)
    from video_inference import compile_local_media
    artifact = compile_local_media(
        media, source_id=source_id, revision=revision,
        asr_model=asr_model, vision_model=vision_model,
        interval_ms=interval_ms, max_frames=max_frames)
    receipt = write_evidence(root, artifact)
    return {**receipt,"modalities": sorted({w["modality"] for w in artifact["witnesses"]}),
            "witness_count":len(artifact["witnesses"]),
            "evidence_admission":"INCONCLUSIVE",
            "human_review_required":True}
