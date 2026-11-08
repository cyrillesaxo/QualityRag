"""Deterministic benchmark for *synthetic witness descriptions*, not real videos.

This only measures whether indexed descriptions can be retrieved through
the QualityRAG search layer. It does not test ASR, scene understanding,
vision accuracy, real video grounding, or commercial search usefulness.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from video_catalog import search_evidence, write_evidence
from video_evidence import compile_video_evidence

# Each synthetic source deliberately contains both an audio statement and
# a distinct timestamped visual observation. No source media exists.
SCENARIOS = [
    {
        "id": "synthetic-nursing-01",
        "audio": "The instructor explains how to prepare a wheelchair transfer.",
        "visual": "A wheelchair brake lever is visible beside the rear wheel.",
        "question": "wheelchair brake lever",
        "target": "video",
    },
    {
        "id": "synthetic-product-02",
        "audio": "A presenter announces the newest product improvements.",
        "visual": "The package label reads expired batch in small print.",
        "question": "expired batch",
        "target": "video",
    },
    {
        "id": "synthetic-safety-03",
        "audio": "The supervisor outlines construction site procedures.",
        "visual": "A worker walks into the demonstration without a helmet.",
        "question": "worker helmet",
        "target": "video",
    },
    {
        "id": "synthetic-software-04",
        "audio": "An engineer describes system performance and availability.",
        "visual": "The dashboard shows a red warning next to payment retries.",
        "question": "payment retries warning",
        "target": "video",
    },
    {
        "id": "synthetic-nursing-05",
        "audio": "The nurse says the exam wording contains an exception.",
        "visual": "The question screen contains the phrase NOT EXCEPT.",
        "question": "NOT EXCEPT",
        "target": "video",
    },
    {
        "id": "synthetic-research-06",
        "audio": "The speaker says the evaluation used only a small sample.",
        "visual": "A slide chart has a footer reading synthetic evaluation.",
        "question": "synthetic evaluation",
        "target": "video",
    },
]

def make_artifact(item):
    source_id=item["id"]
    checksum=lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
    return compile_video_evidence(
        source_id=source_id,revision="fixture-r1",media_sha256=checksum(source_id),
        duration_ms=10000,
        witnesses=[
            {"id":"speech","modality":"audio",
             "interval":{"start_ms":1000,"end_ms":3200},
             "text":item["audio"],"provider":"synthetic-fixture"},
            {"id":"frame","modality":"video",
             "interval":{"start_ms":1800,"end_ms":1801},
             "text":item["visual"],"provider":"synthetic-fixture",
             "frame_sha256":checksum(source_id+"-frame")},
        ],
        events=[],model_receipts=[{"kind":"synthetic_text_fixture",
                                   "no_video_decoded":True}],
    )


def evaluate(*, root, top_k=5):
    if type(top_k) is not int or not 1 <= top_k <= 30:
        raise ValueError("top_k out of range")
    permitted=frozenset(item["id"] for item in SCENARIOS)
    details=[]
    for item in SCENARIOS:
        query=item["question"]
        audio=search_evidence(root,query,modality="audio",
                              source_ids=permitted,limit=top_k)
        cross=search_evidence(root,query,modality="all",
                              source_ids=permitted,limit=top_k)
        target=lambda results:any(r["source_id"]==item["id"] and
                                  r["modality"]==item["target"]
                                  for r in results["results"])
        details.append({
            "source_id":item["id"],"query":query,
            "required_modality":item["target"],
            "speech_only_hit":target(audio),
            "multimodal_hit":target(cross),
            "speech_only_retrieved":len(audio["results"]),
            "multimodal_retrieved":len(cross["results"]),
        })
    n=len(details)
    baseline=sum(r["speech_only_hit"] for r in details)
    multimodal=sum(r["multimodal_hit"] for r in details)
    return {
        "schema":"qualityrag.synthetic-video-retrieval-benchmark/v1",
        "dataset":"SYNTHETIC_TEXT_FIXTURES_NO_VIDEO_MEDIA",
        "claims_not_established":[
            "real_video_scene_accuracy","speech_recognition_accuracy",
            "real_video_multimodal_advantage","user_relevance",
            "semantic_understanding","commercial_conversion"],
        "retrieval_method":"BOUNDED_LEXICAL_ONLY",
        "questions":n,"top_k":top_k,
        "speech_only_hit_count":baseline,
        "multimodal_hit_count":multimodal,
        "speech_only_hit_at_k":round(baseline/n,4),
        "multimodal_hit_at_k":round(multimodal/n,4),
        "cases":details,
        "quality_admission":"INTEGRATION_FIXTURE_NOT_REAL_WORLD_VALIDATION",
    }


def run():
    with tempfile.TemporaryDirectory(prefix="qualityrag-synthetic-video-benchmark-") as root:
        for item in SCENARIOS:
            write_evidence(root,make_artifact(item))
        return evaluate(root=root)


if __name__=="__main__":
    print(json.dumps(run(),indent=2,sort_keys=True))
