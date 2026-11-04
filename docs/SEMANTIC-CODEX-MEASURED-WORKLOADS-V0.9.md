# Semantic Codex v0.9 — actually measured repeat workloads

This milestone runs **real repeated query executions** over two indexed arms on **temporary local copies** of the same reviewed image corpus. It measures indexing, first-query latency, subsequent warm-query samples, source-update work, and physical SQLite database size. It does **not** claim that one representation is better; the compared filename-only baseline has much less capability than visual retrieval.

## Run with your own reviewed image collection

Provide the same exact flat-folder image inventory and v0.7 label manifest specified in `docs/SEMANTIC-CODEX-PAIRED-BENCHMARK-V0.7.md` (2–50 PNG/JPEG/WebP files, every file labeled for every query). Install the existing Python governance requirements and optional local OpenCLIP model:

```sh
python -m pip install -r tools/packspec_compiler/requirements.txt
python -m pip install open_clip_torch torch
PYTHONPATH=tools/semantic_store python tools/semantic_store/run_measured_workloads.py \
  --root /path/to/photos --manifest /path/to/labels.json \
  --repetitions 10 --k 5 --update-png selected.png \
  --output /tmp/workload-v09.json
```

The `--update-png` file is mutated at one pixel **only on a disposable temporary copy**. The original input bytes are not modified. Leaving out `--update-png` measures initial indexing and repeated retrieval only.

The runner refuses extra or missing files, unapproved source access, partial index coverage, truncation, invalid relevance labels, unsupported source updates and over-budget workloads. It uses the existing `index_directory`, `index_visual_semantics`, and `find_visual_scenes` mechanisms rather than simulating visual retrieval.

## Interpreting the receipt

- `initial_index_ms.filename_metadata`: actual filename/size/mtime indexing into a SQLite table.
- `initial_index_ms.codex_and_visual`: actual versioned Semantic Codex source record ingestion **plus** encoding into the visual index.
- `query_samples`: each actual execution's latency and finite-scope precision@k/recall@k, alternating arm order to partially reduce cache-order effects.
- `cold_first_in_process`: the first query in an already initialized Python process. **It is not a cold process or unloaded-model test.**
- `warm_query_latency`: min, median, nearest-rank p95 and maximum from the subsequent query samples. Do not interpret tiny fixture runs as statistically reliable.
- `source_update`: actual baseline metadata update and Semantic Codex reindexing + visual re-embedding of the changed source, preserving immutable historic source revisions. A common file mutation time is listed separately and excluded from arm comparisons.
- `storage_after_initial_index` and `storage_after_update`: observed SQLite file byte sizes for the respective indexes. Physical sizes include SQLite overhead and ledger history; source media files are copied and shared input cost is excluded.
- `full_lifecycle_cost: NOT_ESTABLISHED`, `verification_time: NOT_MEASURED`, `model_initialization: EXCLUDED`: no fabricated zero costs, savings or total-cost equivalence. Machine, caching, CPU load, storage device, query mix and model weights can materially change measured times.

### Restrictions

The two arms do **not** have equivalent semantics. The filename baseline cannot see pixels, so it should not be used to argue that Semantic Codex is better than modern multimodal retrieval. Model inference results and independent label provenance are not verified. OpenCLIP model initialization may need approved weights/network; the benchmark does not transmit user media to an inference API. No named-person identification or PackSpec admission is performed.

The measured update is deliberately a small pixel mutation. It does not validate large changed documents, multi-tenant permissions, distributed storage, frame-by-frame video, rebuilding an index after model upgrades, or complex semantic relations. The current temporary SQLite index is not a production scale test.

## CI verification

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_measured_workloads.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

CI uses a labeled synthetic image set and an explicit deterministic **test encoder**. The test measures the actual software paths and storage but does not establish accuracy, latency or cost for the real pretrained model.

## Next real experiment

Run this benchmark on independently reviewed, realistic photographs, then compare against a **capability-matched retrieval system** (another image-text encoder or image captions plus lexical/vector search), measure process-cold model loading, verification obligations, updates, network/energy consumption, and image/video source coverage. FF-RCT should choose the least-cost representation **subject to the same required distinctions and correctness constraints**, not merely optimize an incomplete filename baseline.
