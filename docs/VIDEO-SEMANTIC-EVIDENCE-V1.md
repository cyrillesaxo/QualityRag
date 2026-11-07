# Video Semantic Evidence v1 — bounded adapter

**Status:** executable candidate-IR adapter; not a video understanding model, production ingestion service, PackSpec verdict, or a verified description of media. This module does not download YouTube videos, run ASR, decode frames, perform OCR, recognize actions, or validate physical reality.

The existing `semantic_codex.py` accepts WebVTT text as structural candidates. `video_evidence.py` adds a separate, opt-in adapter to normalize **already extracted** speech and video observations without declaring them true.

## Provider contract

Pass video duration in milliseconds, immutable source identity/revision, actual original-media SHA-256, and an array of source-bound observations ("witnesses"). Each witness must declare:
- unique id, modality (`audio`, `video`, `ocr`, `sensor`), `interval` with integer `start_ms`/`end_ms`, provider name, and observed text
- optional finite confidence score (0–1)
- visual witnesses may carry a frame SHA-256 and normalized bounding box `[x1, y1, x2, y2]`

Events reference existing witnesses whose intervals overlap the event interval. Events carry label, entities, attributes, relations, state changes, and named constraints with `OBSERVED`, `CONTRADICTED`, or `UNKNOWN`. `UNKNOWN` is the default. A physical constraint cannot be marked `OBSERVED` on speech evidence alone. **A visual witness is not itself proof** that a physical predicate holds; its label and the underlying media still need human or independently validated interpretation.

```sh
PYTHONPATH=tools/semantic_store python - <<'PY'
from hashlib import sha256
from video_evidence import compile_video_evidence, inspect_constraints
video = b"example-media-byte-placeholder"  # replace with the actual video bytes
artifact = compile_video_evidence(
    source_id="training-clip", revision="1",
    media_sha256=sha256(video).hexdigest(), duration_ms=10000,
    witnesses=[
      {"id":"w1","modality":"audio","interval":{"start_ms":1000,"end_ms":3500},
       "text":"Engage the brakes","provider":"example-asr"},
      {"id":"w2","modality":"video","interval":{"start_ms":1500,"end_ms":4500},
       "text":"Wheelchair in view","provider":"example-video-model"}
    ],
    events=[
      {"id":"e1","label":"transfer preparation",
       "interval":{"start_ms":1000,"end_ms":5000},"witnesses":["w1","w2"],
       "constraints":[{"name":"brakes_engaged","state":"UNKNOWN","witnesses":["w2"]}]}
    ],
    model_receipts=[{"provider":"example-only","model":"not-run"}])
print(artifact["governance"])
print(inspect_constraints(artifact))
PY
```

## Proposed full pipeline (not implemented in this change)

1. Separate audio with an authorized media decoder; perform ASR with word timing and diarization (capture provider/model/version, language, inference settings and cost).
2. Detect scene cuts, OCR text, UI transitions, object tracks, motion and state-change candidates with video-native models. Preserve frame/time and region hashes.
3. Align audio, frames and temporal events to a common clock. Never infer the absence of an action merely from unsampled frames.
4. Feed candidate observations to this adapter. Add a reviewed PackSpec mapping into WitnessGraph/FF-RCT only after source permission, authentication and evidence checks.
5. Activate higher-resolution inspection where a critical constraint is unresolved. Sample independent high-resolution control windows to measure the missed-trigger rate.
6. Compare speech-only, speech+frame-captions and native-video-model baselines on temporal localization, consequential-detail recall, hallucination/unsupported-claim rate, WER, cost/video-hour and abstention calibration.

## Safety boundaries

- All outputs remain `CANDIDATE_REQUIRES_REVIEW` and `INCONCLUSIVE`. Neither model confidence nor the availability of a frame promotes a candidate to a verified fact.
- Inputs must come from legally and appropriately authorized media. This adapter does not grant media ingestion rights.
- Source bytes/frames are **not embedded**; storage, authorization, retention, deletion, security and provenance are duties of the calling system.
- No patient identity, clinical safety, biometric matching, or policy compliance conclusions are made.
- Use `inspect_constraints` to enumerate unresolved conditions. It validates the fingerprint; the hash is an integrity signal, **not authentication**.

## Test

```sh
PYTHONPATH=tools/semantic_store python -m unittest discover -s tools/semantic_store/tests -p 'test_video_evidence.py' -v
```

This does not connect inference providers or the runtime console yet. It supplies a bounded, testable seam for future adapters and evaluation datasets.
