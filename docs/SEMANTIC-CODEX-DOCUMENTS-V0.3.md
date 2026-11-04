# Semantic Codex v0.3 — documents in the directory search workbench

The existing local QualityRag Studio workbench can now index textual content from:

| Format | Extraction | Match anchor |
| --- | --- | --- |
| CSV | rows and scalar values | row number |
| flat JSON | scalar fields | JSON pointer |
| WebVTT | subtitle text | time interval |
| PDF | embedded selectable text via `pypdf` | page number |
| DOCX | main document paragraphs in bounded OOXML | paragraph number |
| HTML / HTM | ordinary visible HTML text via stdlib `HTMLParser` | extracted text line |
| TXT | UTF-8 text | line number |

**Not full coverage:** this release has no OCR, images, alt text, drawings, speaker identification, embedded media, headers/footers, attachments or video-frame interpretation. DOCX extraction covers only the primary `word/document.xml` paragraphs, including paragraphs inside tables. The resulting records explicitly say `extraction_coverage: PARTIAL_TEXT_ONLY`, and source reconstruction still requires separate custody of original bytes.

PDFs with no selectable text cannot be found based on their page images. Every query remains scoped to indexed candidate text with source anchors and `admission: INCONCLUSIVE`.

## Run

Install the existing shared Python requirements for pypdf (if not already installed):

```sh
python -m pip install -r tools/packspec_compiler/requirements.txt
```

Follow the three-terminal local Studio instructions in `docs/SEMANTIC-STUDIO-LOCAL-WORKBENCH.md`. Choose a folder containing `.pdf`, `.docx`, `.html`, `.htm`, `.txt`, `.csv`, `.json`, or `.vtt` files. Index and type `Cyrille` in the existing Studio field, or use:

```sql
FIND 'Cyrille' IN 'local' LIMIT 50;
```

Queries return source names and anchors. Original bytes are **not served over HTTP**. PDFs are not automatically opened or highlighted yet. The existing worker's local token and loopback-only constraints still apply.

## Verification

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_document_codex.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
cd apps/studio && npm run build
```

The tests create a real reportlab PDF and minimal valid OOXML DOCX, then confirm the same persistent index can search both along with HTML and TXT, with page/paragraph/line anchors, partial-extraction boundaries, and idempotent reindexing.

## Next

The subsequent image and video adapters require a separately evaluated visual indexing pipeline and source-frame anchors; we must not infer identity from textual captions or visual resemblance. Image OCR is a distinct capability from scene/object retrieval, which is distinct from permissioned person identification. All must retain explicit source custody and non-authoritative confidence.

**Practical constraint:** document extraction handles untrusted files in the local process, with strict size and count limits. For production, place parsers in a separately isolated/sandboxed worker and audit parser denial-of-service and archive decompression risks.
