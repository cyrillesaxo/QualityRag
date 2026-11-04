# Semantic Codex v0.4 — image appearance and video-frame reference search

This release adds a **real pixel-based but non-semantic** visual indexing mechanism to the same local QualityRag Studio directory workflow.

## What works

- PNG, JPEG and WebP files are decoded with Pillow and reduced to an orientation-aware 64-bit difference hash (dHash). This is a compact visual-appearance signature, not an embedding or object representation.
- MP4, MOV and MKV video can be **optionally** sampled with an installed FFmpeg executable. A bounded maximum of 12 frames from the first 60 seconds, nominally one frame every 5 seconds, is stored with source-relative time anchors. FFmpeg failure is reported as failed indexing; no fallback is fabricated.
- The existing immutable Semantic Store stores one candidate record per image or sampled video frame, preserving source revision hash, anchor, and method.
- Studio offers **Find visually similar images and video frames**, taking the exact ID of an **already indexed source image**, for example `local/reference.png`. It never accepts an arbitrary file path to open.
- The workbench uses source-level authorization before image indexing, lookup and result disclosure. An exact namespace is required and query results are bounded.

## How to try

Install shared requirements:

```sh
python -m pip install -r tools/packspec_compiler/requirements.txt
```

For video sampling, install FFmpeg separately on the local trusted host, ensuring `ffmpeg` is on `PATH`. Video is optional; images do not require FFmpeg.

Start the existing Registry, local Semantic Store workbench and Studio as documented in `docs/SEMANTIC-STUDIO-LOCAL-WORKBENCH.md`. Set `QUALITYRAG_SEMANTIC_ROOT` to your media folder, **Index files**, enter a source image ID such as `local/reference.png`, and choose **Find similar media**.

A programmatic local host can use:

```python
from directory_codex import find_visual_similar
result = find_visual_similar(store,
    reference_source_id="local/reference.png",
    namespace="local",principal="local-owner",
    authorize_source=trusted_authorization_callback,
    max_distance=10)
```

The `distance` is a 0–64 Hamming distance between image hashes. It is **not** a confidence score or calibrated probability, and no threshold has been validated for a specific dataset.

## Boundaries

**This does not recognize Cyrille from a photograph.** Whole-image visual similarity may find nearly identical photos, altered versions or similar-looking scenes, but cannot establish that they contain the same person. The implementation neither detects faces nor identifies people; `identity_status` stays `UNKNOWN` and admission stays `INCONCLUSIVE`.

A general query `FIND 'Cyrille'` still searches indexed **text only**. Visual matching is separately invoked by referencing an indexed image. There is no automated visual-to-name association, text-image model, semantic object detection, arbitrary video processing, or production-grade multimodal search yet.

For production, media decoders and FFmpeg must be isolated in a restricted worker with resource and protocol limitations, and source ACLs must be provided by a trusted host. The prototype's loopback local-only auth is not multi-tenant authorization. This work does not change QualityRag PackSpec evaluation.

## Verification

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_visual_codex.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
npm --prefix apps/studio run build
```

Tests use actual generated image pixels, source-authorized indexed search and deterministic synthetic video frame inputs. They **do not** claim FFmpeg execution on every machine, visual semantic classification, biometric verification or semantic equivalence.

## Next milestone

Add a separately evaluated image-text embedding/caption provider so the user's prompt can retrieve objects/actions/scenes in visual media without filename or caption text. Make it explicit whether a result comes from a lexical description, model-generated observation, visual similarity or verified source evidence, and do not conflate visual resemblance with identity.
