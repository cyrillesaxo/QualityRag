"""Offline real-corpus retrieval evaluation with externally curated gold witnesses.

Media bytes are verified locally against catalog hashes. No video downloaded,
no ground truth synthesized from system output, no identity or action truth
inferred. Human reviewer attestations are self-reported, not authenticated.
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

from video_catalog import CatalogError, permitted_media, read_evidence, search_evidence

MAX_CASES=500
MAX_MANIFEST_BYTES=1024*1024


def evaluate_manifest(root: str, manifest: dict, *, top_k=5) -> dict:
    if type(top_k) is not int or not 1<=top_k<=30:
        raise CatalogError("Top-k must be 1-30")
    if not isinstance(manifest,dict) or manifest.get("schema")!="qualityrag.video-benchmark-manifest/v1":
        raise CatalogError("Invalid evaluation manifest schema")
    if manifest.get("synthetic_only") is not False:
        raise CatalogError("Real evaluation requires an explicit nonsynthetic declaration")
    cases=manifest.get("cases")
    if not isinstance(cases,list) or not 1<=len(cases)<=MAX_CASES:
        raise CatalogError("Evaluation cases missing or exceed budget")
    reviewer=manifest.get("reviewer")
    if not isinstance(reviewer,str) or not reviewer.strip() or len(reviewer)>200:
        raise CatalogError("Named reviewer required")
    if manifest.get("rights_confirmed") is not True or manifest.get("reviewed_original_video") is not True:
        raise CatalogError("Rights and independent full-video review attestations required")
    source_paths=manifest.get("sources")
    if not isinstance(source_paths,dict) or not source_paths:
        raise CatalogError("Source-to-local-media map required")

    # Preflight all source hashes prior to any retrieval/scoring.
    allow=set()
    verified_sources={}
    for source_id,relative_path in source_paths.items():
        artifact=read_evidence(root,source_id)
        media=permitted_media(root,relative_path)
        digest=hashlib.file_digest(media.open("rb"),"sha256").hexdigest()
        if digest!=artifact["source"]["media_sha256"]:
            raise CatalogError("Original media digest does not match source catalog")
        allow.add(source_id)
        verified_sources[source_id]=artifact

    allowed=frozenset(allow)
    seen=set()
    results=[]
    for case in cases:
        if not isinstance(case,dict):
            raise CatalogError("Invalid evaluation case")
        case_id=case.get("id")
        source_id=case.get("source_id")
        witness_id=case.get("target_witness_id")
        query=case.get("query")
        if not isinstance(case_id,str) or not case_id or case_id in seen:
            raise CatalogError("Duplicate or invalid evaluation case ID")
        seen.add(case_id)
        if source_id not in verified_sources:
            raise CatalogError("Gold target source absent from verified corpus")
        artifact=verified_sources[source_id]
        target=next((w for w in artifact["witnesses"] if w["id"]==witness_id),None)
        if target is None or target["modality"] not in {"video","ocr"}:
            raise CatalogError("Gold witness must be a visual or OCR observation")
        if not isinstance(query,str) or not 2<=len(query.strip())<=200:
            raise CatalogError("Invalid evaluation query")
        speech=search_evidence(root,query,modality="audio",limit=top_k,source_ids=allowed)
        cross=search_evidence(root,query,modality="all",limit=top_k,source_ids=allowed)
        def hit(candidate):
            return any(r["source_id"]==source_id and r["witness_id"]==witness_id
                       for r in candidate["results"])
        results.append({
            "id":case_id,"source_id":source_id,"target_witness_id":witness_id,
            "target_modality":target["modality"],
            "speech_only_target_hit":hit(speech),
            "cross_modal_target_hit":hit(cross),
        })
    n=len(results)
    return {
        "schema":"qualityrag.video-retrieval-evaluation/v1",
        "dataset":"OPERATOR_DECLARED_NONSYNTHETIC_REVIEWED_CORPUS",
        "human_review_authenticity":"SELF_ATTESTED_NOT_VERIFIED",
        "media_hashes_checked":len(verified_sources),
        "cases":n,"top_k":top_k,
        "speech_only_target_hit_at_k":sum(x["speech_only_target_hit"] for x in results)/n,
        "cross_modal_target_hit_at_k":sum(x["cross_modal_target_hit"] for x in results)/n,
        "results":results,
        "limitations":[
            "Measures retrieval over already-indexed text witnesses, not vision model accuracy",
            "Expected witnesses and review attestations are operator supplied",
            "Speech-only cannot return visual witness IDs by construction; compare user-answer accuracy separately",
            "Missing search hits do not prove visual absence",
        ],
        "evidence_admission":"RETRIEVAL_EVALUATION_ONLY",
    }


def run_manifest(root, filename, *, top_k=5):
    file=Path(filename).expanduser().resolve(strict=True)
    if not file.is_file() or file.stat().st_size>MAX_MANIFEST_BYTES:
        raise CatalogError("Manifest missing or exceeds budget")
    return evaluate_manifest(root,json.loads(file.read_text(encoding="utf-8")),
                             top_k=top_k)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",required=True)
    parser.add_argument("--manifest",required=True)
    parser.add_argument("--top-k",type=int,default=5)
    args=parser.parse_args()
    try:
        print(json.dumps(run_manifest(args.root,args.manifest,top_k=args.top_k),
                         indent=2,sort_keys=True))
    except (ValueError,OSError) as exc:
        print("VIDEO_EVALUATION_REJECTED: "+str(exc),file=sys.stderr)
        sys.exit(1)
