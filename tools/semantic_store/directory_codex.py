"""Bounded local directory -> immutable Semantic Store -> lexical search.

This is a local trusted-host adapter, NOT a public directory API or a source
authorization service. Callers supply explicit access policy for each source.
Only CSV, flat JSON and WebVTT are compiled; unsupported files remain visible
as coverage counts, not silently treated as successfully indexed.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
import stat
from pathlib import Path
from typing import Callable

from semantic_codex import CodexError, SCHEMA
from document_codex import compile_document
from visual_codex import compile_visual, IMAGE_FORMATS, VIDEO_FORMATS, hamming64
from store import SemanticStore, canonical_bytes, digest

EXTENSIONS = {".csv": "csv", ".json": "json", ".vtt": "vtt",
              ".pdf": "pdf", ".docx": "docx", ".html": "html",
              ".htm": "htm", ".txt": "txt", ".png": "png",
              ".jpg": "jpg", ".jpeg": "jpeg", ".webp": "webp",
              ".mp4": "mp4", ".mov": "mov", ".mkv": "mkv"}
MAX_FILES = 200
MAX_BYTES_TOTAL = 20_000_000
MAX_SOURCE_BYTES = 2_000_000


def _valid_namespace(namespace: str) -> bool:
    return (isinstance(namespace, str) and 0 < len(namespace) <= 80
            and all(c.isascii() and (c.isalnum() or c in "-_") for c in namespace))


def persist_codex(store: SemanticStore, artifact: dict) -> dict:
    """Atomic append-only persistence; duplicate revision is a no-op if identical.

    Does not write original bytes. The trusted host must keep source custody.
    """
    if not isinstance(artifact, dict):
        raise CodexError("Missing Codex artifact")
    body = dict(artifact)
    fingerprint = body.pop("fingerprint", None)
    if body.get("schema") != SCHEMA or fingerprint != digest(body):
        raise CodexError("Invalid or modified Codex artifact")
    source = artifact.get("source", {})
    sid, rev = source.get("source_id"), source.get("revision")
    src_hash = source.get("sha256")
    if (not isinstance(sid, str) or not sid or not isinstance(rev, str) or not rev
            or not isinstance(src_hash, str) or len(src_hash) != 64
            or any(c not in "0123456789abcdef" for c in src_hash)):
        raise CodexError("Invalid source identity")
    records = artifact.get("records")
    if not isinstance(records, list) or len(records) > 1000:
        raise CodexError("Invalid record inventory")
    if any(not isinstance(row, dict) or row.get("id") != f"{sid}#{i}"
           or row.get("status") != "STRUCTURAL_CANDIDATE"
           or not isinstance(row.get("fields"), dict)
           or not isinstance(row.get("anchor"), dict)
           for i, row in enumerate(records)):
        raise CodexError("Invalid record identity or shape")
    metadata = {
        "format": source["format"], "codex_fingerprint": fingerprint,
        "source_authenticity": "UNVERIFIED",
        "original_bytes_stored": False,
    }
    with store.db:
        previous = store.db.execute(
            "SELECT source_sha256,metadata_json FROM source_versions "
            "WHERE source_id=? AND revision=?", (sid, rev)).fetchone()
        if previous is not None:
            if previous[0] != src_hash or json.loads(previous[1]) != metadata:
                raise CodexError("Source revision collision or incompatible existing source")
            # Also check ALL expected records and absence of extra record objects.
            actual = store.db.execute(
                "SELECT object_id,payload_json FROM semantic_versions "
                "WHERE source_id=? AND source_revision=? AND kind='CODEX_RECORD' "
                "ORDER BY object_id", (sid, rev)).fetchall()
            expected = [(f"{sid}#{i}", canonical_bytes(row).decode())
                        for i, row in enumerate(records)]
            if actual != sorted(expected):
                raise CodexError("Existing revision has different stored Codex records")
            return {"source_id": sid, "revision": rev, "records": len(records),
                    "persisted": False, "admission": "INCONCLUSIVE"}
        store.db.execute("INSERT INTO source_versions VALUES(?,?,?,?)",
                         (sid, rev, src_hash, canonical_bytes(metadata).decode()))
        for row in records:
            oid = row["id"]
            payload = canonical_bytes(row).decode()
            store.db.execute(
                "INSERT INTO semantic_versions VALUES(?,?,?,?,?,?,?)",
                (oid, rev, sid, rev, "CODEX_RECORD", payload, digest(row)))
    return {"source_id": sid, "revision": rev, "records": len(records),
            "persisted": True, "admission": "INCONCLUSIVE"}


def index_directory(
    store: SemanticStore, root: str | Path, *, namespace: str,
    principal: str, authorize_source: Callable[[str, str, str], bool],
    max_files: int = MAX_FILES,
) -> dict:
    if (not principal or not callable(authorize_source)
            or not _valid_namespace(namespace)):
        raise PermissionError("Principal, authorizer and safe namespace required")
    if type(max_files) is not int or not 1 <= max_files <= MAX_FILES:
        raise CodexError("max_files must be 1..200")
    path = Path(root)
    if path.is_symlink() or not path.is_dir():
        raise CodexError("Directory must exist and must not be a symbolic link")
    root_path = path.resolve(strict=True)
    counters = {"indexed": 0, "unchanged": 0, "unsupported": 0,
                "failed": 0, "denied": 0, "symlinks_skipped": 0,
                "files_considered": 0, "bytes_indexed": 0}
    errors = []
    truncated = False
    folders = [root_path]
    while folders:
        folder = folders.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            counters["failed"] += 1
            continue
        for entry in entries:
            if entry.is_symlink():
                counters["symlinks_skipped"] += 1
                continue
            if entry.is_dir(follow_symlinks=False):
                folders.append(Path(entry.path))
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            if counters["files_considered"] >= max_files:
                truncated = True
                break
            counters["files_considered"] += 1
            fmt = EXTENSIONS.get(Path(entry.name).suffix.lower())
            if fmt is None:
                counters["unsupported"] += 1
                continue
            relative = Path(entry.path).relative_to(root_path).as_posix()
            sid = namespace + "/" + relative
            # Revision is based on bytes. File size/time is not reliable identity.
            if len(sid) > 256:
                counters["failed"] += 1
                continue
            try:
                # A source-level authorization check must precede reading bytes.
                # Revision is unknown until the bytes have been hashed, so this
                # preflight uses '*' and is followed by version-specific check.
                if not authorize_source(principal, sid, "*"):
                    counters["denied"] += 1
                    continue
                if entry.stat(follow_symlinks=False).st_size > MAX_SOURCE_BYTES:
                    counters["failed"] += 1
                    continue
                # Pin the open to a regular file: reject symlink replacement
                # between scandir and open (O_NOFOLLOW where supported).
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(entry.path, flags)
                with os.fdopen(fd, "rb") as handle:
                    details = os.fstat(handle.fileno())
                    if not stat.S_ISREG(details.st_mode):
                        raise CodexError("Not a regular file")
                    data = handle.read(MAX_SOURCE_BYTES + 1)
                if len(data) > MAX_SOURCE_BYTES or counters["bytes_indexed"] + len(data) > MAX_BYTES_TOTAL:
                    counters["failed"] += 1
                    continue
                # If the host cannot authorize the resulting revision, the
                # data is never stored or returned to a search caller.
                rev = sha256(data).hexdigest()
                if not authorize_source(principal, sid, rev):
                    counters["denied"] += 1
                    continue
                artifact = (compile_visual(data, source_id=sid, revision=rev, format=fmt)
                            if fmt in IMAGE_FORMATS | VIDEO_FORMATS else
                            compile_document(data, source_id=sid, revision=rev, format=fmt))
                result = persist_codex(store, artifact)
                counters["indexed" if result["persisted"] else "unchanged"] += 1
                counters["bytes_indexed"] += len(data)
            except (OSError, CodexError, ValueError):
                counters["failed"] += 1
        if truncated:
            break
    return {"schema": "qualityrag.directory-index/v0.2",
            "namespace": namespace, "coverage": counters, "truncated": truncated,
            "supported_formats": sorted(EXTENSIONS.values()),
            "scope": "LOCAL_BOUNDED_STRUCTURAL_INDEX_ONLY",
            "admission": "INCONCLUSIVE"}


def search_store(
    store: SemanticStore, term: str, *, namespace: str,
    principal: str, authorize_source: Callable[[str, str, str], bool],
    max_hits: int = 100, max_records: int = 5000,
) -> dict:
    if not principal or not callable(authorize_source):
        raise PermissionError("Source authorization required")
    if not _valid_namespace(namespace) or not isinstance(term, str) or not 1 <= len(term.strip()) <= 128:
        raise CodexError("Invalid namespace or search term")
    if (type(max_hits) is not int or not 1 <= max_hits <= 100
            or type(max_records) is not int or not 1 <= max_records <= 5000):
        raise CodexError("Invalid search bounds")
    # Exact namespace prefix, not user-controlled LIKE wildcards.
    prefix = namespace + "/"
    rows = store.db.execute(
        "SELECT sv.source_id,sv.source_revision,src.source_sha256,src.metadata_json,sv.payload_json "
        "FROM semantic_versions sv JOIN source_versions src "
        "ON src.source_id=sv.source_id AND src.revision=sv.source_revision "
        "WHERE sv.kind='CODEX_RECORD' AND substr(sv.source_id,1,?)=? "
        "ORDER BY sv.source_id,sv.source_revision,sv.object_id LIMIT ?",
        (len(prefix), prefix, max_records + 1)).fetchall()
    truncated = len(rows) > max_records
    hits = []
    scanned = 0
    visible_sources = set()
    for sid, rev, shash, meta_text, payload_text in rows[:max_records]:
        if not authorize_source(principal, sid, rev):
            continue
        visible_sources.add((sid, rev))
        scanned += 1
        row = json.loads(payload_text)
        metadata = json.loads(meta_text)
        for field, value in row["fields"].items():
            if value.get("type") == "TEXT" and term.casefold() in value["value"].casefold():
                if len(hits) >= max_hits:
                    truncated = True
                    break
                hits.append({"source_id": sid, "revision": rev,
                             "source_sha256": shash, "format": metadata["format"],
                             "record_id": row["id"], "anchor": row["anchor"],
                             "field": field, "matched_text": value["value"],
                             "match_type": "LEXICAL_EXTRACTED_TEXT",
                             "verification": "NOT_PERFORMED"})
        if len(hits) >= max_hits:
            # Conservatively report incomplete coverage even if no further match exists.
            truncated = True
            break
    return {"schema": "qualityrag.directory-search/v0.2",
            "term": term, "hits": hits,
            "visible_source_versions": len(visible_sources),
            "scanned_authorized_records": scanned,
            "truncated": truncated,
            "scope": "INDEXED_RECORDS_ONLY_NOT_ALL_DIRECTORY_CONTENT",
            "visual_identity_recognition": "NOT_PERFORMED",
            "admission": "INCONCLUSIVE", "can_generate": False}


def find_visual_similar(
    store: SemanticStore, *, reference_source_id: str, namespace: str,
    principal: str, authorize_source: Callable[[str, str, str], bool],
    max_distance: int = 10, max_hits: int = 50, max_records: int = 5000,
) -> dict:
    """Find images/video frames resembling an already indexed source image.

    Perceptual hash is a *whole-frame appearance* proxy. A similar score says
    nothing about who is present, whether two people are the same, or meaning.
    """
    if not principal or not callable(authorize_source):
        raise PermissionError("Source-level authorization is required")
    if (not _valid_namespace(namespace) or not isinstance(reference_source_id,str)
            or not reference_source_id.startswith(namespace+"/")
            or type(max_distance) is not int or not 0 <= max_distance <= 64
            or type(max_hits) is not int or not 1 <= max_hits <= 100
            or type(max_records) is not int or not 1 <= max_records <= 5000):
        raise CodexError("Invalid visual reference or search bounds")
    prefix = namespace + "/"
    rows = store.db.execute(
        "SELECT s.source_id,s.source_revision,v.payload_json,m.metadata_json "
        "FROM semantic_versions v JOIN source_versions m "
        "ON m.source_id=v.source_id AND m.revision=v.source_revision "
        "JOIN (SELECT source_id,source_revision FROM semantic_versions "
        "WHERE kind='CODEX_RECORD' GROUP BY source_id,source_revision) s "
        "ON s.source_id=v.source_id AND s.source_revision=v.source_revision "
        "WHERE v.kind='CODEX_RECORD' AND substr(v.source_id,1,?)=? "
        "ORDER BY s.source_id,s.source_revision,v.object_id LIMIT ?",
        (len(prefix), prefix, max_records+1)).fetchall()
    truncated = len(rows)>max_records
    reference=[]
    candidates=[]
    for sid, rev, payload, metadata in rows[:max_records]:
        # Check permissions before parsing/disclosing source values.
        if not authorize_source(principal,sid,rev):
            continue
        fmt=json.loads(metadata).get("format")
        if fmt not in IMAGE_FORMATS | VIDEO_FORMATS:
            continue
        record=json.loads(payload)
        key=record.get("fields",{}).get("visual_hash",{}).get("value")
        if not isinstance(key,str) or len(key)!=16:
            raise CodexError("Malformed indexed visual hash")
        item={"source_id":sid,"revision":rev,"format":fmt,
              "anchor":record["anchor"],"hash":key}
        candidates.append(item)
        if sid==reference_source_id and fmt in IMAGE_FORMATS:
            reference.append(item)
    if not reference:
        raise CodexError("Indexed authorized image reference not found")
    # Reference identity is not tied to a face. Prefer current exact source
    # revision by providing the content-hash-based latest version separately.
    if len(reference)!=1:
        raise CodexError("Ambiguous reference versions; use an unambiguous indexed image")
    matches=[]
    ref=reference[0]
    for item in candidates:
        if item["source_id"]==ref["source_id"] and item["revision"]==ref["revision"]:
            continue
        distance=hamming64(ref["hash"],item["hash"])
        if distance<=max_distance:
            matches.append({"source_id":item["source_id"],"revision":item["revision"],
                            "format":item["format"],"anchor":item["anchor"],
                            "distance":distance,
                            "match_type":"WHOLE_FRAME_VISUAL_APPEARANCE_CANDIDATE",
                            "identity_status":"UNKNOWN"})
    matches.sort(key=lambda x:(x["distance"],x["source_id"],x["revision"]))
    return {"schema":"qualityrag.visual-reference-search/v0.4",
            "reference_source_id":reference_source_id,
            "results":matches[:max_hits],
            "truncated":truncated or len(matches)>max_hits,
            "scanned_authorized_visual_records":len(candidates),
            "method":"64_BIT_DHASH",
            "scope":"BOUNDED_VISUAL_APPEARANCE_NOT_PERSON_IDENTITY",
            "identity_recognition":"NOT_PERFORMED",
            "admission":"INCONCLUSIVE","can_generate":False}
