# Semantic Codex v0.1 — cross-format structural records

**Status: executable prototype, not semantic/biometric recognition or production admission.**

This is the first small intermediate representation underneath the SQL-like and future natural-language surfaces. It converts exact supplied bytes from CSV, flat JSON and WebVTT captions to versioned, source-anchored typed records. It retains original SHA-256 and explicit source custody requirements. It does not flatten images, extract video frames, identify people, interpret units, prove semantic equivalence or evaluate PackSpec.

## Try "Find Cyrille" across three different formats

Run from repository root:

```sh
PYTHONPATH=tools/semantic_store python - <<'PY'
from semantic_codex import compile_source
from codex_find import find_text
sources = [
  compile_source(b"name,role\nCyrille,architect\n",
                 source_id="staff.csv", revision="1", format="csv"),
  compile_source(b'{"note":"Cyrille signed the meeting minutes"}',
                 source_id="meeting.json", revision="1", format="json"),
  compile_source(b"WEBVTT\n\n00:01:02.500 --> 00:01:04.000\nCyrille speaking\n",
                 source_id="clip.vtt", revision="1", format="vtt"),
]
result=find_text(sources,"Cyrille",principal="local-reviewer",
                 authorize_source=lambda principal,source,revision: principal=="local-reviewer")
for hit in result["hits"]:
  print(hit["source_id"], hit["anchor"], hit["matched_text"])
PY
```

The result contains exact CSV row, JSON pointer or WebVTT timestamp anchors. This is lexical searching over extracted text only: a video with no transcript and a photograph with no caption are **not yet searchable by visual content**. The user is not asked to learn this internal Python API; it is an initial adapter for a future familiar console.

## Codex invariants

1. Original source hash and immutable source revision are recorded. **Original bytes are NOT stored inside the Codex output**, so complete byte reconstruction requires separate source custody.
2. Source anchors preserve CSV row number, JSON pointer or media subtitle time interval.
3. Values retain distinct TEXT, NUMBER, BOOLEAN and NULL types. CSV numbers remain text until an explicitly governed typed conversion is requested.
4. Unrecognized/nested JSON, inconsistent CSV records, unsupported WebVTT blocks and nonfinite numbers fail closed instead of silently dropping meaning.
5. Every artifact is an **unverified structural candidate**; no named person's identity is inferred from text.
6. The comparison helper checks typed fields, in order, across different formats. Equality is **not proof of semantic or source equivalence**.
7. Search needs per-source authorization and reports the limitation that it covers only supplied/compiled artifacts. No filesystem crawling or privacy authorization is provided by the package itself.

## Reuse and roadmap

The canonical QualityRag `store.py` remains the immutable/versioned persistence system; `knowledge_ir.py` remains the reviewed ConstraintIR adapter; `semantic_sql.py` and `semantic_investigation.py` remain bounded graph query surfaces. This new IR does **not** replace them. The next integration should persist Codex records as explicitly unverified source versions, then link their anchors into KnowledgeGraph/WitnessGraph using reviewed mappings.

Next format adapters: PDF.js/Tika-backed document structure, DOCX/HTML, Excel/SQL, image regions and image-derived candidates, audio segmentation/transcripts, and video events/frame regions. Identity matching requires an appropriately consented and independently evaluated process; visually similar entities must not be promoted to verified identity without sufficient evidence.

The future common query plan can route SQL, natural-language, UI and spreadsheet formulas to the same candidate IR without making users learn a new grammar.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

This prototype is not a native FF-RCT codec, and no source publisher, PackSpec obligation or global search completeness has been authenticated.
