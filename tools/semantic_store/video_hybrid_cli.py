"""Operator-only CLI to build an offline hybrid index from authorized evidence.

Example:
 QUALITYRAG_VIDEO_ROOT=/approved/media \
 QUALITYRAG_VIDEO_EMBED_MODEL_DIR=/models/my-embedding-model \
 QUALITYRAG_VIDEO_EMBED_MODEL_ID=my-model-v1 \
 PYTHONPATH=tools/semantic_store python tools/semantic_store/video_hybrid_cli.py

This command will not download a model or fetch third-party URLs.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from video_catalog import _root
from video_hybrid import build_hybrid_index, local_encoder

def main():
    root=os.environ.get("QUALITYRAG_VIDEO_ROOT")
    model=os.environ.get("QUALITYRAG_VIDEO_EMBED_MODEL_DIR")
    model_id=os.environ.get("QUALITYRAG_VIDEO_EMBED_MODEL_ID")
    if not root or not model or not model_id:
        raise SystemExit("Configure VIDEO_ROOT, EMBED_MODEL_DIR and EMBED_MODEL_ID")
    receipt=build_hybrid_index(str(_root(root)),model_id=model_id,
                               embedder=local_encoder(model))
    print(json.dumps(receipt,indent=2))

if __name__=="__main__":
    main()
