# Semantic Codex v0.5 — optional prompt-to-visual-scene search

Existing Studio now has a **Find scenes** workflow that indexes images and sampled video frames with a shared image/text embedding model. A user can ask **"someone presenting in a conference room"** without captions. The returned items are *candidate rankings* anchored to source image or sampled timestamp. No claimed identification, truth verification, semantic completeness, or PackSpec admission.

## Run locally

The prior local workbench (see `docs/SEMANTIC-STUDIO-LOCAL-WORKBENCH.md`) continues to work with no model. For scene search only, on a trusted machine provision **optional** Python dependencies:

```sh
python -m pip install open_clip_torch torch
export QUALITYRAG_ENABLE_SCENE_MODEL=1
```

The adapter uses OpenCLIP `ViT-B-32` with `laion2b_s34b_b79k` weights on CPU. Model initialization may download weights and has hardware, resource, and supply-chain implications. Use independently reviewed cached weights for private information. The default remains **off**; if the model cannot load, the workbench refuses to start rather than silently returning mock results. Media inputs are processed locally by this adapter, not uploaded to an inference API.

Open the existing QualityRag Studio, connect the **local** workbench, then **Index files** to register source revisions (PNG, JPEG, WebP, optional MP4/MOV/MKV with FFmpeg). Press **Build scene index** to create source/revision/model-bound, immutable vectors; enter a prompt and click **Find scenes**.

The APIs are `POST /semantic/scenes/index` with empty JSON and `POST /semantic/scenes/find` with `{"prompt":"someone presenting"}`. They require the separate local token and never accept a user-supplied directory root or model path.

## Semantic and operational boundaries

- The **original pixels are read** at embedding time, verifying their SHA-256 matches the indexed source revision. The model receives image pixels or selected video frames. A changed file is not indexed against its former version.
- The image/text encoder returns finite normalized vectors; the store maintains immutable embeddings keyed by source, revision, Codex record ID and model ID. Incompatible model versions are never compared. The score is uncalibrated cosine similarity, **not a probability**.
- A 2 MB source cap, 100 visual sources per indexing pass, 12 frames per video, 600 candidate frames per query, and 100 result cap bound work. Video coverage is a sample from the first 60 seconds only. Reindexing is idempotent.
- No face recognition, person naming, object localization, OCR, speaker analysis, video action proof, or source attribution for model predictions. Searching for "Cyrille" is **not** a validated way to find Cyrille in a picture.
- The host's source-authorization callback runs before encoding, reading records, or returning results. The local workbench uses a fixed local-owner policy only, **not production IAM**. Its SQLite source/embedding ledgers are local research prototypes. Do not expose this worker to the internet.
- Media decoders/FFmpeg and model weights need sandboxing, pinned dependencies, resource budgets, and evaluation before production. No universal semantic-preservation or FF-RCT efficiency claim is established.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_visual_semantic.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
npm --prefix apps/studio run build
```

CI tests the integration using an **explicitly identified deterministic test encoder**, not a pretrained model. It verifies authorization, persistence, score ranking mechanics, revisions and model isolation, NOT real-world scene detection accuracy. Real model acceptance needs independent labeled photo/video fixtures and systematic top-k recall / false positives / index cost measurement.
