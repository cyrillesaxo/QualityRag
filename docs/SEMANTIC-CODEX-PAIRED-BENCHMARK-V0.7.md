# Semantic Codex v0.7 — paired retrieval baseline experiment

**Purpose:** falsifiable measurement of a familiar lexical baseline versus a Semantic Codex visual retrieval path using the **same complete, explicitly labeled finite image pool**.

The code uses existing `index_directory`, `index_visual_semantics` and `find_visual_scenes`. It does not add an invented search mechanism or claim semantic truth.

## Experiment design

- **Arm A — filename lexical baseline:** deterministic case-insensitive token matching against the *filename only*, because a raw photo generally has no embedded words to search. This is a deliberately limited baseline, **not** a state-of-the-art multimodal search competitor, full-text engine or image-caption retrieval system.
- **Arm B — visual retrieval:** existing opt-in OpenCLIP image/text encoder applied to original image pixels; model-based cosine ranking against the same candidate pool.
- **Common scope:** a single folder with 2–50 **flat PNG/JPEG/WebP image files**, each labeled for each of 1–20 prompts. The evaluator refuses missing files, extra image files, unauthorized files, failed indexing, truncated candidate sets, missing labels and malformed manifests. Videos are *not included* until independently reviewed frame-level labels exist.
- **Labels:** caller-supplied `RELEVANT`, `NOT_RELEVANT`, or `UNCERTAIN`. Their provenance is **not authenticated**. Unknown labels produce no numeric precision/recall.
- **Metrics:** precision@k and finite-pool recall@k, plus directory index time, visual index time, query wall-clock times, source bytes processed by initial indexing, and recorded coverage. No model initialization time, query energy, download cost, complete video processing, or full I/O attribution is measured. **Total cost advantage remains NOT ESTABLISHED.**
- **Interpretation:** a positive result on this fixture would not demonstrate a genuine FF-RCT regime advantage; stronger baselines, multiple independent test datasets, a cost model and independent review are still necessary.

## Label manifest

Put 3 images in a folder, e.g. `a.png`, `b.png`, and `c.png`. Save this `labels.json` **outside** the indexed directory:

```json
{
  "schema": "qualityrag.paired-benchmark-input/v0.7",
  "items": [
    {"path": "a.png", "relevance": {"q1": "NOT_RELEVANT"}},
    {"path": "b.png", "relevance": {"q1": "RELEVANT"}},
    {"path": "c.png", "relevance": {"q1": "NOT_RELEVANT"}}
  ],
  "queries": [
    {"id": "q1", "prompt": "someone presenting in a conference room",
     "lexical_terms": ["presenting", "conference"]}
  ]
}
```

**Do not copy these example relevance judgments blindly**—review the actual pixels and label each image separately. Set `UNCERTAIN` when reviewers cannot establish the requested content.

## Run with actual OpenCLIP

```sh
python -m pip install -r tools/packspec_compiler/requirements.txt
python -m pip install open_clip_torch torch
PYTHONPATH=tools/semantic_store python tools/semantic_store/run_paired_benchmark.py \
    --root /path/to/your/image-folder \
    --manifest /path/to/labels.json --k 2 --output /tmp/paired-benchmark.json
```

This may download model weights on first initialization; use an approved local cache for private data. Neither dataset completeness nor independent review is guaranteed merely because the manifest declares labels.

Run tests without downloading OpenCLIP:

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_paired_benchmark.py -v
```

The CI tests generate simple real PNG pixels and use an explicitly identified deterministic **fixture encoder**, so their high retrieval scores are not evidence of genuine visual understanding or pretrained-model quality.

## What remains

The next research round must compare **equally provisioned** baselines (including OCR, image captions, commercial multimodal retrieval or another open vision-language encoder) with held-out real images, video timestamp labels, recall of hidden semantic relationships, adversarial confounders, inference energy and total lifecycle work.

Because naming a specific person in a photograph is a different task from describing a scene, this experiment does not establish person identity matching. All receipts stay `admission: INCONCLUSIVE`, `can_generate: false`.
