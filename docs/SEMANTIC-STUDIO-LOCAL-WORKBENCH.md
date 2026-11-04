# QualityRag Studio — local Semantic Store directory workbench

This is a **local single-user research preview**, not a remotely deployed file browser. It reuses the **existing Studio** and persisted Semantic Codex directory search backend. Browser users never send an arbitrary server filesystem path. A trusted local operator supplies one directory at service startup.

## Start three components

From repository root (Python 3.12 and Node.js 20+):

Terminal 1 — existing Registry:

```sh
export QUALITYRAG_REGISTRY_TOKEN='choose-a-long-local-registry-token'
npm --prefix apps/registry start
```

Terminal 2 — separate local semantic workbench:

```sh
export QUALITYRAG_SEMANTIC_ROOT="$HOME/Documents"
export QUALITYRAG_SEMANTIC_TOKEN='choose-a-different-very-long-random-local-secret'
export QUALITYRAG_SEMANTIC_DB='.qualityrag/semantic-local.sqlite3'
PYTHONPATH=tools/semantic_store python tools/semantic_store/local_workbench.py
```

Terminal 3 — existing React Studio:

```sh
cd apps/studio
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. In **5. Semantic Store · Local directory**, enter the **separate semantic token**, click **Connect directory**, then **Index files**, and type **Cyrille** in the search field. Press **Find**.

Studio sends `FIND 'Cyrille' IN 'local' LIMIT 50;` to a separate local worker through Vite's loopback proxy. Results include source-relative path, source revision, CSV row / JSON pointer / VTT time interval, field, and matching text.

## Supported v0.1 query

```sql
FIND 'Cyrille' IN 'local' LIMIT 50;
```

Only indexed **CSV, flat JSON and WebVTT** files are supported. This is lexical search on extracted text. **Photos, videos without subtitles, PDFs, DOCX and visual identity recognition are not included.** Results are research candidates, not PackSpec admission, and an absence of hits proves nothing about unindexed content.

## Security / reliability boundary

- Worker binds strictly to `127.0.0.1` (5056 by default) and requires its own >=24-character bearer token. Registry credentials do not work with the semantic worker.
- Paths are configured at startup, never passed from the browser. Indexing is subject to file count/size limits, skips symlinks, and stores immutable source versions. Worker is intended for a trusted local OS account, not a hostile multi-tenant machine.
- It checks browser `Origin` for known localhost Studio URLs, but this is a defense-in-depth local limitation, **not** a replacement for production CSRF protection, CORS policy, authenticated user isolation, or filesystem ACLs.
- The demo worker uses a fixed local-owner source policy. It is **not** a production per-user authorizer. Do not expose via public Vite/registry ingress, tunnel or reverse proxy.
- The Studio stores tokens only in component state, not local storage; close the tab to discard.
- Original source bytes remain on disk; the database stores fingerprints, typed candidate records and source anchors. The UI displays path and anchor, but does not yet open the original file in the browser.
- A full source-revision history is retained. Search across all indexed versions may produce multiple historical hits; latest-version selection is future work.
- Indexing reports denied/unsupported/failed/unchanged counts. Search reports truncated results to prevent claims of completeness.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_local_workbench.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
npm --prefix apps/studio run build
```

Next: production-capable file authorization, document adapters, latest-version selection, source preview, graph visualizer and proper PackSpec gate. None is provided by this local preview.
