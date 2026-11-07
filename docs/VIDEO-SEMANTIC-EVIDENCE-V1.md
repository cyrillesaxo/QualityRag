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


## Runnable local inference (added in PR #84)

The optional runner is `tools/semantic_store/video_inference.py`. Requires local `ffmpeg` and `ffprobe`. Video frame inference is performed against **loopback Ollama** only, with an explicitly selected local multimodal vision model. Optional local speech transcription uses `faster-whisper` (install separately). Model weights may be downloaded by those runtimes when first selected; verify licensing and hardware requirements. No external YouTube retrieval, remote hosted inference, or background ingestion is built in.

```sh
# Pre-install ffmpeg, ffprobe, Ollama and a locally available vision model.
# Then use an authorized local MP4:
python tools/semantic_store/video_inference.py ./authorized-training.mp4 \
  --source-id training-001 --revision r1 \
  --vision-model YOUR_LOCAL_VISION_MODEL \
  --interval-ms 5000 --max-frames 200 \
  --output ./training-evidence.json

# Optional additional speech observations:
pip install faster-whisper
python tools/semantic_store/video_inference.py ./authorized-training.mp4 \
  --source-id training-001 --revision r1 \
  --asr-model large-v3 --vision-model YOUR_LOCAL_VISION_MODEL \
  --output ./training-evidence.json
```

For targeted higher-frequency sampling, provide `--inspection-windows windows.json`:

```json
[{"start_ms":10000,"end_ms":15000}]
```

The output is a bounded `qualityrag.video-evidence/v1` artifact. Each timestamped frame description and ASR segment becomes a separate candidate event, with hash and model receipt. **This runner does not yet perform temporal event fusion, tracking, OCR-specific grounding, action verification, or FF-RCT admission.** In particular, a single-frame description cannot establish that an action was completed. All inference outputs remain `UNVERIFIED_OBSERVATION` and `INCONCLUSIVE`, suitable for controlled evaluation and later reviewed ingestion.

```sh
PYTHONPATH=tools/semantic_store python -m unittest discover -s tools/semantic_store/tests -p 'test_video_inference.py' -v
```

### Operational boundaries

This is a research-local tool, not a hardened multi-tenant ingestion service. Treat input files as untrusted: use sandboxing, resource limits, protected credentials, and custody/retention controls before exposing it through a server. `--max-frames` provides an inference count bound, not a cap on the size or compute cost of an input video. Increase sampling density only after measuring consequential-event recall on held-out clips.


## Adaptive visual change-point inspection

Use `--scene-scan` to request a **bounded, model-independent candidate transition scan** before visual-language-model inference:

```sh
python tools/semantic_store/video_inference.py ./authorized-training.mp4 \
  --source-id training-001 --revision r2 \
  --vision-model YOUR_LOCAL_VISION_MODEL \
  --scene-scan --scene-cadence-ms 2000 \
  --scene-threshold 0.24 --interval-ms 5000 --max-frames 200 \
  --output ./scene-evidence.json
```

The scanner in `video_scenes.py` decodes tiny 32x18 grayscale frames at deterministic regular intervals. Mean absolute luminance difference proposes a change-point when it crosses the configured threshold. The candidate time is expanded into a local inspection window; dense model sampling combines these windows with regular control samples. The receipt records the detector version, threshold, probe frequency, and candidate count.

**Interpretation boundary:** This detects image changes, not actions, entities, scene semantics, safety conditions, or motion direction. Camera pans, lighting, cuts and compression can produce false positives; gradual or occluded actions can be missed. An empty transition list does not prove nothing happened. The model output is `UNVERIFIED_OBSERVATION`, and downstream constraint admission remains `INCONCLUSIVE`.

The implementation fails closed on excessive probe counts, scene windows or model-frame budgets, rather than silently dropping observations. For production, replace the repeated point-frame decode with bounded streaming and attach actual temporal tracking and a reviewed FF-RCT mapping.

```sh
python -m unittest discover -s tools/semantic_store/tests -p 'test_video_scenes.py' -v
```


## Candidate before/after state transitions

Pass `--compare-transitions` to opt into a paired-frame comparison with the same local Ollama vision model used to caption frames:

```sh
python tools/semantic_store/video_inference.py ./authorized-training.mp4 \
  --source-id training-001 --revision r3 \
  --vision-model YOUR_LOCAL_VISION_MODEL \
  --scene-scan --compare-transitions --max-transition-pairs 40 \
  --max-frames 41 --output ./candidate-transitions.json
```

The `video_transitions.py` adapter requests structured JSON comparing **two distinct timestamped frames**. It records the candidate entity and attribute, before and after descriptions, and a `CHANGED` / `UNCHANGED` / `UNKNOWN` prediction. Every candidate retains the original frame-witness IDs and hashes, plus the explicitly unresolved `causal_attribution` and `physical_constraint_verdict`. A paired-frame difference does not establish what happened between the frames or whether an instructor's narrated action was actually performed.

Transition candidates are attached to the `video-evidence/v1` artifact as event `changes`, together with a mandatory unresolved `transition_verified` constraint. No FF-RCT/PackSpec verdicts or source admission are promoted. The runner fails closed if requested comparisons exceed `--max-transition-pairs`, rather than silently skipping some. Each comparison is a separate local vision-model call, which can be expensive.

Tests:

```sh
python -m unittest discover -s tools/semantic_store/tests -p 'test_video_transitions.py' -v
```

Future work is *multi-frame tracking*, occlusion-aware identity association and independently evaluated state-transition verification; do not market the present paired-still-image output as action recognition.
