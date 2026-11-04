"""Optional, local contrastive vision-language retrieval over original media bytes.

A trusted host configures an image/text encoder with a pinned model identity.
Real OpenCLIP is opt-in. Deterministic fixtures can implement the same encoder
contract for unit tests, but NEVER represent model evidence or visual accuracy.
No identity/face recognition, no verified scene truth, no PackSpec admission.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
from typing import Protocol

from PIL import Image, ImageOps
from visual_codex import IMAGE_FORMATS, VIDEO_FORMATS, _video_frames
from semantic_codex import CodexError
from store import SemanticStore, canonical_bytes

MAX_INPUT_BYTES = 2_000_000
MAX_FILES = 100
MAX_VECTORS = 600
MAX_DIMENSIONS = 2048
MODEL_ID = "openclip:ViT-B-32:laion2b_s34b_b79k"


class Encoder(Protocol):
    model_id: str
    def image(self, image_bytes: bytes) -> list[float]: ...
    def text(self, prompt: str) -> list[float]: ...


class OpenClipEncoder:
    """Optional CPU inference, loaded once by the trusted local process.

    Install manually: pip install open_clip_torch torch. First use may download
    model weights from the network; use an approved cached model for private data.
    No raw media is sent to an inference API by this class.
    """
    model_id = MODEL_ID

    def __init__(self):
        try:
            import open_clip
            import torch
        except ImportError as e:
            raise CodexError("Install optional open_clip_torch and torch for scene search") from e
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k", device="cpu")
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-B-32")

    def image(self, image_bytes: bytes) -> list[float]:
        with Image.open(BytesIO(image_bytes)) as image:
            converted = ImageOps.exif_transpose(image).convert("RGB")
            inputs = self.preprocess(converted).unsqueeze(0)
        with self.torch.no_grad():
            return self.model.encode_image(inputs).float().cpu().flatten().tolist()

    def text(self, prompt: str) -> list[float]:
        with self.torch.no_grad():
            return self.model.encode_text(self.tokenizer([prompt])).float().cpu().flatten().tolist()


def normalize(vector: list[float]) -> list[float]:
    if (not isinstance(vector, list) or not 2 <= len(vector) <= MAX_DIMENSIONS
            or any(type(x) not in (int,float) or not math.isfinite(x) for x in vector)):
        raise CodexError("Encoder returned invalid finite vector")
    scale=math.sqrt(sum(x*x for x in vector))
    if scale < 1e-12:
        raise CodexError("Encoder returned zero vector")
    return [x/scale for x in vector]


def initialize(store: SemanticStore):
    store.db.execute("""CREATE TABLE IF NOT EXISTS codex_visual_embeddings(
       source_id TEXT NOT NULL, revision TEXT NOT NULL, record_id TEXT NOT NULL,
       model_id TEXT NOT NULL, anchor_json TEXT NOT NULL, vector_json TEXT NOT NULL,
       PRIMARY KEY(source_id, revision, record_id, model_id),
       FOREIGN KEY(source_id,revision) REFERENCES source_versions(source_id,revision)
    )""")
    for action in ("UPDATE","DELETE"):
        store.db.execute(
            f"CREATE TRIGGER IF NOT EXISTS immutable_codex_visual_embeddings_{action.lower()} "
            f"BEFORE {action} ON codex_visual_embeddings BEGIN "
            "SELECT RAISE(ABORT,'immutable visual index'); END;")


def _source_bytes(root: Path, sid: str, namespace: str) -> bytes:
    prefix=namespace+"/"
    if not sid.startswith(prefix):
        raise CodexError("Source outside indexed namespace")
    rel=sid[len(prefix):]
    parts=Path(rel).parts
    if not parts or any(p in ("..",".","") for p in parts):
        raise CodexError("Invalid source relative path")
    location=root.joinpath(*parts)
    if not location.resolve().is_relative_to(root.resolve()):
        raise CodexError("Source outside configured directory")
    fd=os.open(location, os.O_RDONLY | getattr(os,"O_NOFOLLOW",0))
    with os.fdopen(fd,"rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise CodexError("Source must be a regular file")
        source=handle.read(MAX_INPUT_BYTES+1)
    if not 0<len(source)<=MAX_INPUT_BYTES:
        raise CodexError("Source exceeds local visual budget")
    return source


def index_visual_semantics(
    store: SemanticStore, root: Path, *, namespace: str, principal: str,
    authorize_source, encoder: Encoder, max_sources: int = MAX_FILES,
) -> dict:
    if (not callable(authorize_source) or not principal
            or not isinstance(namespace,str) or not namespace.isascii()
            or not namespace.replace("-","").replace("_","").isalnum()
            or type(max_sources) is not int or not 1<=max_sources<=MAX_FILES
            or not isinstance(encoder.model_id,str) or not 1<=len(encoder.model_id)<=128):
        raise CodexError("Invalid visual indexing configuration")
    initialize(store)
    rows=store.db.execute(
        "SELECT source_id,revision,source_sha256,metadata_json FROM source_versions "
        "WHERE substr(source_id,1,?)=? ORDER BY source_id,revision LIMIT ?",
        (len(namespace)+1,namespace+"/",max_sources+1)).fetchall()
    truncated=len(rows)>max_sources
    indexed=failed=skipped=0
    for sid,rev,original_hash,metadata in rows[:max_sources]:
        if not authorize_source(principal,sid,rev):
            skipped+=1
            continue
        fmt=json.loads(metadata).get("format")
        if fmt not in IMAGE_FORMATS | VIDEO_FORMATS:
            skipped+=1
            continue
        try:
            already=store.db.execute(
                "SELECT COUNT(*) FROM codex_visual_embeddings WHERE source_id=? AND revision=? AND model_id=?",
                (sid,rev,encoder.model_id)).fetchone()[0]
            expected=1 if fmt in IMAGE_FORMATS else None
            if expected is not None and already>=expected:
                skipped+=1
                continue
            data=_source_bytes(root,sid,namespace)
            if sha256(data).hexdigest()!=original_hash:
                # Historical source bytes must not be silently reinterpreted as
                # their previous revision. The host must reindex latest first.
                skipped+=1
                continue
            frames=([(0,data)] if fmt in IMAGE_FORMATS else _video_frames(data,format=fmt))
            if already==len(frames):
                skipped+=1
                continue
            if already:
                raise CodexError("Partial or conflicting existing model index")
            if len(frames)>12:
                raise CodexError("Video frame budget exceeded")
            prepared=[]
            for i,(ms,frame) in enumerate(frames):
                vec=normalize(encoder.image(frame))
                prepared.append((sid,rev,f"{sid}#{i}",encoder.model_id,
                    canonical_bytes({"kind":"image_frame"} if fmt in IMAGE_FORMATS
                                    else {"kind":"video_frame","timestamp_ms":ms}).decode(),
                    canonical_bytes(vec).decode()))
            with store.db:
                store.db.executemany(
                    "INSERT INTO codex_visual_embeddings VALUES(?,?,?,?,?,?)",prepared)
            indexed+=1
        except (CodexError,OSError,sqlite3.DatabaseError,ValueError):
            failed+=1
    return {"schema":"qualityrag.visual-semantic-index/v0.5",
            "model_id":encoder.model_id,"indexed_sources":indexed,
            "failed_sources":failed,"skipped_sources":skipped,
            "truncated":truncated,"coverage":"AUTHORIZED_SAMPLED_MEDIA_ONLY",
            "identity_recognition":"NOT_PERFORMED",
            "admission":"INCONCLUSIVE"}


def find_visual_scenes(
    store: SemanticStore, prompt: str, *, namespace: str, principal: str,
    authorize_source, encoder: Encoder, max_hits: int = 30,
    max_records: int = MAX_VECTORS,
) -> dict:
    if (not isinstance(prompt,str) or not 1<=len(prompt.strip())<=256
            or not principal or not callable(authorize_source)
            or not isinstance(namespace,str) or not namespace.isascii()
            or not namespace.replace("-","").replace("_","").isalnum()
            or type(max_hits) is not int or not 1<=max_hits<=100
            or type(max_records) is not int or not 1<=max_records<=MAX_VECTORS):
        raise CodexError("Invalid natural-language scene query")
    initialize(store)
    query=normalize(encoder.text(prompt))
    rows=store.db.execute(
        "SELECT source_id,revision,record_id,anchor_json,vector_json "
        "FROM codex_visual_embeddings "
        "WHERE model_id=? AND substr(source_id,1,?)=? "
        "ORDER BY source_id,revision,record_id LIMIT ?",
        (encoder.model_id,len(namespace)+1,namespace+"/",max_records+1)).fetchall()
    truncated=len(rows)>max_records
    ranked=[]
    for sid,rev,rid,anchor,packed in rows[:max_records]:
        if not authorize_source(principal,sid,rev):
            continue
        vec=json.loads(packed)
        if len(vec)!=len(query):
            raise CodexError("Visual model dimensionality mismatch")
        similarity=sum(a*b for a,b in zip(query,vec))
        ranked.append({"source_id":sid,"revision":rev,"record_id":rid,
                       "anchor":json.loads(anchor),
                       "similarity":round(similarity,6),
                       "match_type":"MODEL_RANKED_VISUAL_SCENE_CANDIDATE",
                       "verification":"NOT_PERFORMED"})
    ranked.sort(key=lambda x:(-x["similarity"],x["source_id"],x["record_id"]))
    return {"schema":"qualityrag.visual-semantic-search/v0.5",
            "prompt":prompt,"model_id":encoder.model_id,
            "results":ranked[:max_hits],
            "truncated":truncated or len(ranked)>max_hits,
            "evaluated_authorized_frames":len(ranked),
            "coverage":"ONLY_SAMPLED_AND_ENCODED_MEDIA_NOT_COMPLETE",
            "score_meaning":"UNCALIBRATED_COSINE_SIMILARITY_NOT_PROBABILITY",
            "identity_recognition":"NOT_PERFORMED",
            "admission":"INCONCLUSIVE","can_generate":False}
