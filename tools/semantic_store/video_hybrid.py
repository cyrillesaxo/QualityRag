"""Opt-in, local-only hybrid video witness retrieval.

Lexical evidence remains the baseline. Dense vectors are built only from
already-indexed and hash-verified witness text, using a *local* embedding
model directory or a dependency-injected embedder. This is not a verified
fact engine, web crawler, or hosted vector database.
"""
from __future__ import annotations
import json
import math
import os
import tempfile
from pathlib import Path

from video_catalog import CatalogError, _catalog_dir, read_evidence, TOKEN
from video_sources import source_reference

MAX_DOCUMENTS = 5000
MAX_DIMENSION = 1024
MAX_INDEX_BYTES = 16 * 1024 * 1024


def local_encoder(model_directory):
    """Load only a locally installed sentence-transformers model directory."""
    model_path = Path(model_directory).expanduser().resolve(strict=True)
    if not model_path.is_dir():
        raise CatalogError("Embedding model must be an existing local directory")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise CatalogError("Install sentence-transformers for hybrid indexing") from exc
    model = SentenceTransformer(str(model_path), trust_remote_code=False)
    def encode(values):
        return model.encode(values, convert_to_numpy=True, normalize_embeddings=True).tolist()
    return encode


def _normalized(vector):
    if not isinstance(vector, (list, tuple)) or not 1 <= len(vector) <= MAX_DIMENSION:
        raise CatalogError("Invalid embedding dimensions")
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in vector):
        raise CatalogError("Invalid embedding values")
    length = math.sqrt(sum(float(x)**2 for x in vector))
    if length < 1e-10:
        raise CatalogError("Zero-norm embedding")
    return [round(float(x)/length, 8) for x in vector]


def _encode(embedder, texts):
    vectors = embedder(texts)
    if not isinstance(vectors, (list,tuple)) or len(vectors) != len(texts):
        raise CatalogError("Embedding provider did not return a vector per text")
    normalized = [_normalized(v) for v in vectors]
    if len({len(v) for v in normalized}) != 1:
        raise CatalogError("Embedding dimensions inconsistent")
    return normalized


def _index_file(root):
    path = _catalog_dir(root) / "hybrid-index.json"
    if path.is_symlink():
        raise CatalogError("Refusing vector index symlink")
    return path


def build_hybrid_index(root, *, model_id, embedder):
    if not isinstance(model_id, str) or not 1 <= len(model_id) <= 128:
        raise CatalogError("Invalid embedding model ID")
    directory = _catalog_dir(root)
    records = []
    fingerprints = {}
    for file in sorted(directory.glob("*.json")):
        if file.name in {"hybrid-index.json", "sources.json"} or file.name.startswith(".") or file.is_symlink():
            continue
        if len(fingerprints) >= 1000:
            raise CatalogError("Catalog beyond indexed source limit")
        try:
            artifact = read_evidence(root,file.stem)
        except CatalogError:
            raise CatalogError("Cannot silently index a corrupted source")
        source = artifact["source"]
        fingerprints[source["source_id"]] = artifact["fingerprint"]
        for witness in artifact["witnesses"]:
            records.append({
                "source_id":source["source_id"],
                "revision":source["revision"],
                "media_sha256":source["media_sha256"],
                "witness_id":witness["id"],
                "start_ms":witness["interval"]["start_ms"],
                "end_ms":witness["interval"]["end_ms"],
                "modality":witness["modality"],
                "text":witness["text"][:1000],
                "frame_sha256":witness.get("frame_sha256")
            })
            if len(records) > MAX_DOCUMENTS:
                raise CatalogError("Index document budget exceeded")
    if not records:
        raise CatalogError("No video witnesses indexed")
    # Embeddings are deliberately bounded. Model choice and licensing
    # remain caller responsibility.
    vectors = []
    for start in range(0,len(records),32):
        vectors.extend(_encode(embedder,[r["text"] for r in records[start:start+32]]))
    dimensions = len(vectors[0])
    if any(len(v)!=dimensions for v in vectors):
        raise CatalogError("Inconsistent embedding dimensions")
    payload = {
        "schema":"qualityrag.video-hybrid-index/v1",
        "model_id":model_id,
        "dimension":dimensions,
        "fingerprints":fingerprints,
        "records":[{**r,"embedding":v} for r,v in zip(records,vectors)],
        "governance":"UNVERIFIED_WITNESS_TEXT",
    }
    encoded = json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
    if len(encoded)>MAX_INDEX_BYTES:
        raise CatalogError("Hybrid index size budget exceeded")
    dest = _index_file(root)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False,prefix=".hybrid-") as f:
            temp=Path(f.name)
            f.write(encoded)
        os.replace(temp,dest)
    finally:
        if temp is not None: temp.unlink(missing_ok=True)
    return {"status":"BUILT","model_id":model_id,"dimension":dimensions,
            "witness_count":len(records),"source_count":len(fingerprints),
            "retrieval":"LEXICAL_PLUS_LOCAL_DENSE"}


def search_hybrid(root, query, *, embedder, model_id, limit=10, lexical_weight=0.5):
    if not isinstance(query,str) or not 2 <= len(query.strip()) <= 200:
        raise CatalogError("Invalid query")
    if type(limit) is not int or not 1 <= limit <= 30:
        raise CatalogError("Invalid result limit")
    if type(lexical_weight) not in (float,int) or not math.isfinite(lexical_weight) or not 0 <= lexical_weight <= 1:
        raise CatalogError("Invalid lexical weight")
    idx = _index_file(root)
    if not idx.is_file() or idx.stat().st_size>MAX_INDEX_BYTES:
        raise CatalogError("Missing or oversized hybrid index")
    try:
        payload=json.loads(idx.read_text(encoding="utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise CatalogError("Invalid hybrid index") from exc
    if payload.get("schema")!="qualityrag.video-hybrid-index/v1" or payload.get("model_id")!=model_id:
        raise CatalogError("Wrong embedding index or model")
    records=payload.get("records")
    if not isinstance(records,list) or not 1<=len(records)<=MAX_DOCUMENTS:
        raise CatalogError("Invalid indexed witnesses")
    # New sources make an index incomplete just as changed sources make it stale.
    current_ids={p.stem for p in _catalog_dir(root).glob("*.json")
                 if p.name not in {"hybrid-index.json","sources.json"} and not p.name.startswith(".")}
    if current_ids != set(payload.get("fingerprints",{})):
        raise CatalogError("Catalog membership changed; rebuild hybrid index")
    # Fail closed if indexed content is stale or underlying source removed.
    for source_id, fingerprint in payload.get("fingerprints",{}).items():
        if read_evidence(root,source_id)["fingerprint"]!=fingerprint:
            raise CatalogError("Index is stale; rebuild before searching")
    qvec = _encode(embedder,[query])[0]
    if len(qvec)!=payload["dimension"]:
        raise CatalogError("Query model dimension does not match index")
    terms = set(TOKEN.findall(query.lower()))
    results=[]
    for item in records:
        vec=_normalized(item.get("embedding"))
        if len(vec)!=len(qvec):
            raise CatalogError("Indexed vector dimension mismatch")
        similarity=sum(a*b for a,b in zip(vec,qvec))
        lexical = len(terms & set(TOKEN.findall(item["text"].lower())))/max(len(terms),1)
        score=lexical_weight*lexical+(1-lexical_weight)*max(0,similarity)
        if score<=0: continue
        results.append({
            "source_id":item["source_id"],"revision":item["revision"],
            "media_sha256":item["media_sha256"],"witness_id":item["witness_id"],
            "modality":item["modality"],"start_ms":item["start_ms"],
            "end_ms":item["end_ms"],"frame_sha256":item.get("frame_sha256"),
            "observation":item["text"],"score":round(score,6),
            "lexical_score":round(lexical,6),"dense_similarity":round(similarity,6),
            "source_reference":source_reference(root,item["source_id"],item["start_ms"]),
            "admission":"UNVERIFIED_OBSERVATION"
        })
    results.sort(key=lambda r:(-r["score"],r["source_id"],r["start_ms"],r["witness_id"]))
    return {"schema":"qualityrag.video-hybrid-search/v1",
            "query":query,"retrieval":"LEXICAL_PLUS_LOCAL_DENSE",
            "model_id":model_id,"results":results[:limit],
            "governance":"INCONCLUSIVE; embeddings measure similarity, not truth or action completion"}
