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


## Cross-modal research queries (new)

The MCP now provides `research_video_question(query, intent, limit, window_ms)`. Choose `intent="spoken"` for transcript matches, `"visual"` for frame-caption matches, or `"cross_modal"` (default) to find either and include nearby witnesses from the same approved video. Results are grouped into timestamp-cited, source-hashed candidate bundles. Each bundle reports its anchor, nearby witnesses, source ID/revision, media SHA-256, witness IDs, modalities and unresolved governance.

For a speech witness discussing wheelchair brakes, a nearby visual frame about the brake lever can be returned **alongside** the audio claim. That is *co-observation*, **not** agreement, action verification, or evidence that the brake was actually engaged. If the visual term is not indexed, visual-only queries return no matches without concluding the action was absent. Evidence location references are local catalog coordinates, not publicly playable YouTube links.

This is still **bounded lexical retrieval**, limited to the first 30 candidate matches before regrouping; it does not yet perform cross-language semantic search, compare semantic entailment, inspect full-frame media on demand or validate FF-RCT constraints. It is an intermediate MCP protocol for testing whether multimodal evidence improves consequential-detail retrieval compared with speech-only search.

```sh
PYTHONPATH=tools/semantic_store python -m unittest discover \
  -s tools/semantic_store/tests -p test_video_research.py -v
```

### Near-term path to a paid product

1. **Customer-authorized corpus:** accept lawful local/owned media and explicit source metadata/permissions; do not rely on unrestricted downloading from social networks.
2. **Source-native visual citations:** resolve each witness to a playable and permissioned video segment plus frame timestamp; preserve source link/version and availability status.
3. **Cross-modal hybrid retrieval:** compare lexical baseline against embeddings and temporal relevance on a fixed set of visually answerable questions.
4. **Governed answers:** distinguish spoken assertions, visible observations, inferred transitions and missing evidence; never treat model captions as independently verified.
5. **Commercial pilot:** sell evidence-backed competitor-demo audits, product-review intelligence and training-compliance analysis. Track processing cost, report acceptance, customer conversion and whether results outperform transcript-only research.
6. **Deployment:** only after tenant boundaries, authentication, consent, rate limits and model-worker isolation are implemented, expose a remote Streamable HTTP MCP endpoint and connect it in ChatGPT.

Do not claim a connected ChatGPT tool or public Perplexity-like service before those steps have been executed and verified.


## Rights-gated source registry (added)

`video_sources.py` maintains a local metadata registry for each fingerprint-checked video source. Operators may register a title, immutable source ID/revision/media SHA-256, declared rights category (`owned`, `licensed`, `explicit_permission`, `unknown`, `restricted`) and optional public source page. Rights are **declarations**, not independently authenticated legal permissions. This registry does **not** download, crawl or fetch the registered URL.

Timestamped research results now contain `source_reference`. A public link is returned only for sources explicitly registered with an allowed rights category and `allow_public_citation=true`. Otherwise it returns `NO_APPROVED_PUBLIC_REFERENCE` or `PRIVATE_OR_UNLICENSED` without disclosing a private URL. Approved public links use specific allowlisted HTTPS video hosts; YouTube timestamp links are candidates whose playback/deep-link support must be reviewed.

A trusted local operator can register source metadata through Python:

```python
from video_sources import register_source
register_source(
    "/path/to/authorized/media", source_id="lesson-001", revision="r1",
    media_sha256="PASTE_EXACT_64_CHARACTER_MEDIA_HASH",
    title="Consented training demonstration", rights="owned",
    public_url="https://www.youtube.com/watch?v=REPLACE_WITH_REAL_VIDEO_ID",
    allow_public_citation=True)
```

Registration requires matching existing indexed evidence. It rejects attempts to change the source revision, media hash or rights silently. Do not expose source registration to untrusted chat users.

## Optional hybrid dense/lexical search (added)

`video_hybrid.py` provides a bounded, real embedding-vector retrieval path with lexical relevance blending; it is **optional**, not a claim that the entire video is semantically understood. Vectors cover source-bound *witness descriptions*, not raw video pixels. The search rejects stale indexes when catalog membership or source fingerprint changes, missing model IDs, dimension mismatches and malformed vectors. It returns the same rights-scoped timestamp citations and explicit `UNVERIFIED_OBSERVATION` admission.

To build the index, provision a locally downloaded, reviewed and appropriately licensed sentence-transformers model in a local directory, then run the operator-only CLI:

```sh
python -m pip install sentence-transformers
export QUALITYRAG_VIDEO_ROOT="$HOME/qualityrag-authorized-video"
export QUALITYRAG_VIDEO_EMBED_MODEL_DIR="/absolute/path/to/locally-installed-model"
export QUALITYRAG_VIDEO_EMBED_MODEL_ID="local-embedding-v1"
PYTHONPATH=tools/semantic_store python tools/semantic_store/video_hybrid_cli.py
```

No remote model identifier or remote download is accepted by this path; `video_hybrid_cli.py` loads the model from the existing local directory. The new MCP tool `hybrid_search_video(query, limit, lexical_weight)` then searches the built index. `lexical_weight=0.5` blends both signals equally; 0 uses only dense similarity, 1 uses only token overlap. The index is a bounded local file, **not** a durable multi-tenant vector database or a verified semantic benchmark. Rebuild it after any changes to indexed sources.

### Operational and evaluation limits

- The registry permits URL references, not playback rights or downloading rights.
- The local index is capped at 5,000 witness documents, 1,024 vector dimensions, and 16 MiB on-disk.
- Only a source with declared rights and explicit permission can produce a public timestamp citation; a video description alone does not certify any action.
- The MCP still runs via local stdio. It is not yet available to ChatGPT without connection, and it should not be exposed on a public network without authentication and tenant isolation.
- Benchmark speech-only lexical, cross-modal lexical and cross-modal hybrid on held-out real footage, tracking consequential visual detail recall, false supports, cost, latency and source-access correctness before claiming an advantage.

```sh
PYTHONPATH=tools/semantic_store python -m unittest discover -s tools/semantic_store/tests -p test_video_sources.py -v
PYTHONPATH=tools/semantic_store python -m unittest discover -s tools/semantic_store/tests -p test_video_hybrid.py -v
```


## Read-only authenticated Streamable HTTP staging (new)

`tools/semantic_store/video_mcp_remote.py` adds a **separate** MCP transport intended for a single operator's protected staging environment. It exposes only `search_video_evidence`, `research_video_question` and `inspect_video_evidence`. Remote clients **cannot** run local-video inference, modify the source registry, build the index or ingest new media through this endpoint.

It uses an operator-supplied 32+ character bearer token checked before any MCP request, exact Origin filtering, explicit SDK Host allowlisting, and loopback-only process binding. It does **not** provide OAuth 2.1, multi-tenant auth, token rotation/revocation, quota management, inference sandboxing, or a public ChatGPT connector. Bearer tokens are a single-operator staging measure, not a replacement for proper OAuth in a customer service.

```sh
python -m pip install 'mcp>=2.3,<3' 'uvicorn>=0.30,<1'
export QUALITYRAG_VIDEO_ROOT="$HOME/qualityrag-authorized-video"
export QUALITYRAG_VIDEO_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
# Optional exact origin/host allowlists for a protected HTTPS reverse proxy:
# export QUALITYRAG_VIDEO_MCP_ALLOWED_HOSTS="mcp.example.com"
# export QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGINS="https://app.example.com"
PYTHONPATH=tools/semantic_store python tools/semantic_store/video_mcp_remote.py
```

The internal ASGI service binds only to `127.0.0.1:8039` by default. Its MCP endpoint is `/mcp`, requiring the header `Authorization: Bearer <configured token>` for all calls. To use off-host, put it **behind an independently secured HTTPS reverse proxy** that preserves authentication and enforces host/origin restrictions. Never expose port 8039 directly or commit secrets.

The dedicated workflow tests security denials and authentic MCP initialization/tool discovery through the current Python v2 SDK. The original v1 integration failed because its FastMCP app factory does not accept transport_security; the protected HTTP adapter now uses the supported v2 MCPServer API. The standalone stdio prototype is currently based on the older v1 SDK; install its dependencies in a separate virtual environment until it is migrated. No actual server has been deployed or connected to ChatGPT yet; check the latest workflow before treating protocol compatibility as verified. To use this as a ChatGPT-connected remote service, the next milestone is OAuth with scoped access, deployment isolation and supported plugin connection—not just a reverse-proxied static token.

## Mandatory source allowlist for remote MCP staging

The read-only HTTP server now refuses to start unless `QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS` is explicitly populated with a comma-separated list of indexed source IDs. Every remote search restricts source membership **before ranking and before selecting nearby cross-modal witnesses**. Direct `inspect_video_evidence` on a disallowed source fails without revealing whether the ID exists.

```sh
export QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS="lesson-001,lesson-002"
# Only these indexed, authorized videos may be read over the HTTP MCP.
PYTHONPATH=tools/semantic_store python tools/semantic_store/video_mcp_remote.py
```

This is a static source scope for a **single operator**, not per-user OAuth authorization or robust multi-tenancy. Do not share its token between tenants or expose it to public internet clients. Production needs a trusted identity provider, audience/scopes, per-tenant source ACL enforcement, token expiry/revocation, audit logs and load-shedding; those pieces are not completed here. Source permission declarations are not independently verified legal grants. Existing MCP connections remain unavailable from this conversation until the user installs/connects an approved, actually deployed connector.
