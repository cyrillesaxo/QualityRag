# Semantic Codex v0.2 — connect a local directory to Semantic Store

**Scope:** local trusted-host prototype. Supports CSV, flat JSON and WebVTT captions. It does **not** index PDF, DOCX, image pixels, video frames, untranscribed audio, or infer an individual's identity. Unsupported formats are explicitly counted.

## Actual end-to-end workflow

Use Python 3.12 from the repository root:

```sh
PYTHONPATH=tools/semantic_store python - <<'PY'
from pathlib import Path
import sqlite3
from store import SemanticStore
from directory_codex import index_directory, search_store

db = sqlite3.connect("codex-demo.sqlite3")
store = SemanticStore(db)
store.initialize()

# Local single-user example only. Never use this permissive policy in a
# network service or multi-user environment.
def local_only(principal, source_id, revision):
    return principal == "local-owner" and source_id.startswith("demo/")

report = index_directory(
    store, Path("./example-files"), namespace="demo",
    principal="local-owner", authorize_source=local_only)
print(report)

results = search_store(
    store, "Cyrille", namespace="demo", principal="local-owner",
    authorize_source=local_only)
for hit in results["hits"]:
    print(hit["source_id"], hit["anchor"], hit["matched_text"])
print("Truncated:", results["truncated"])
PY
```

Create `example-files` containing a `team.csv` such as `name,role\nCyrille,architect\n`, a `meeting.json` such as `{"note":"Cyrille attended"}`, and a `clip.vtt` WebVTT caption with the word Cyrille. The result is retrieved from an **immutable, persistent SQLite Semantic Store**, not from in-memory artifacts. `FIND` is a strictly bounded indexed lexical search; it is not a general SQL parser, visual entity recognition, or semantic similarity engine.

## Implementation details

- `persist_codex` appends source revision fingerprint and typed records in one transaction. Reindexing exact same content is idempotent; changed bytes create another immutable revision.
- `index_directory` enumerates locally, skips symlinks, caps at 200 files / 20MB / 2MB per file, and requires a caller-supplied source authorization callback **before** reading files and again against the derived revision.
- `search_store` reads only the requested namespace's stored `CODEX_RECORD` objects, requires per-source/revision authorization, applies strict 5,000-record and 100-hit limits, and returns file/row/JSON pointer/time-span anchors.
- The SQLite store retains **no original source bytes**. Custody, reconstructions, access controls and file retention must be supplied by the host.
- Source access callbacks must implement a secure authenticated identity. A `'*'` revision preflight is used before file access; the precise SHA-256-derived revision is checked immediately after reading.
- `truncated`, `unsupported`, `failed`, `denied`, and coverage counts must be surfaced to the user. Absence of results never proves absence from unindexed files.
- This prototype is not a public REST endpoint. Do **not** reuse the Studio Registry operator token as a file authorizer.

## Limits of what was accomplished

The actual ingestion, persistence and query functions are implemented and CI-tested; a hosted interactive Studio console, PDF/DOCX adapters, image/video analysis, full source reconstruction, signed PackSpec admission, and production IAM are **not implemented in this change**.

Future UI flow: **Connect directory → Index → Query → Display source anchors → Open original**. A production host must broker filesystem access, source custody and ACL verification before connecting the existing Studio interface.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```
