# QualityRAG Video MCP — first local prototype

**Status:** repository code only, not a deployed/connected ChatGPT plugin. Based on the video-semantic-evidence research branch. This is **not** Perplexity-level search, cross-platform crawling, verified scene understanding or a published commercial service.

## Capabilities

The local stdio MCP adapter in `tools/semantic_store/video_mcp.py` exposes three tools:

- `analyze_local_video(relative_path, source_id, revision, asr_model, vision_model, interval_ms, max_frames)` — opt-in processing of authorized MP4/MOV/MKV/WebM under an allowlisted root, using existing `compile_local_media`; any selected local ASR/Ollama vision models and weights must be provisioned separately. Returns candidate evidence and a source-hash receipt, not verified facts.
- `search_video_evidence(query, modality, limit)` — bounded **lexical baseline** across indexed witness texts, yielding modality, source ID, revision, timestamp and media/frame hashes. Does not yet perform embedding or semantic retrieval.
- `inspect_video_evidence(source_id)` — returns fingerprint-checked source witnesses/events and explicit `INCONCLUSIVE` governance.

No platform URL ingestion or scraper is present. An LLM caller cannot use this MCP to read arbitrary files or enumerate private directories; source paths are relative to `QUALITYRAG_VIDEO_ROOT`. Do not expose it to untrusted users without container sandboxing, authentication/authorization, rate limits, workload quotas, malware scanning, retention and tenant isolation.

## Local setup

Use Python 3.11+ and the official `mcp` SDK plus FFmpeg and FFprobe. ASR requires optional `faster-whisper`; visual inference uses local Ollama with an explicitly installed vision model.

```sh
python -m pip install "mcp>=1.28,<2"
export QUALITYRAG_VIDEO_ROOT="$HOME/qualityrag-authorized-video"
mkdir -p "$QUALITYRAG_VIDEO_ROOT"
PYTHONPATH=tools/semantic_store python tools/semantic_store/video_mcp.py
```

Connect the stdio server through an MCP host that supports local subprocess MCP connections. This is **not** automatically connected to this ChatGPT session. For remote ChatGPT access, build a separate authenticated Streamable HTTP deployment and follow the host's MCP installation/connection flow. Do not expose this local server publicly as-is.

Place a media file in the allowed directory, choose explicit ASR and/or vision models when invoking `analyze_local_video`, then search with `search_video_evidence`. You can also ingest correctly formed `qualityrag.video-evidence/v1` artifacts through the tested Python `write_evidence` core for fixtures.

## Hard limits and evaluation

- Media size ≤512 MiB; witness artifacts ≤4 MiB; `max_frames` ≤120, default 60. These are not a full CPU/GPU/time budget.
- A matched textual witness is an **unverified observation**. A visual caption is not proof of an action. Missing hits are `UNKNOWN`, not evidence of absence.
- Catalog is local file-backed storage (maximum 1000 enumerated artifacts for search), no tenancy, no vector search, no durable metadata database, no multi-platform URL discovery and no online freshness guarantee.
- Search is lexical; ranking counts matched query terms. Benchmark it against transcript-only search on held-out questions requiring visuals, temporal order, objects, actions, text-in-scene and contradictory evidence before marketing an advantage.
- YouTube, Instagram and TikTok collection must use rights-cleared media or authorized providers. Third-party APIs differ in available metadata, media access, access controls, terms and eligibility.
- For production research add source and URL adapters, rights policy, revision tracking, semantic indexing, robust cross-modal time alignment, cited frame inspection and an authenticated MCP service.

## Test without models or internet

```sh
PYTHONPATH=tools/semantic_store python -m unittest discover \
  -s tools/semantic_store/tests -p 'test_video_catalog.py' -v
```

The tests cover immutable source evidence, time-stamped candidate retrieval, source confinement, invalid catalog entries and no-model operation.
