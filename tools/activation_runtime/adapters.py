"""Exact-source custody and deterministic PDF/text/CSV citations, no inferred omissions."""
from hashlib import sha256
from io import BytesIO
from .pipeline import ingest_csv
from .common import fingerprint


def ingest(raw, *, format):
    if not isinstance(raw,bytes) or not 0<len(raw)<=2_000_000:
        raise ValueError("Source byte limit")
    digest=sha256(raw).hexdigest()
    if format=="csv":
        return ingest_csv(raw)
    spans=[]
    unknown=[]
    if format=="text":
        text=raw.decode("utf-8")
        offset=0
        for line_no,line in enumerate(text.splitlines(keepends=True),1):
            spans.append({"page":None,"line":line_no,"char_start":offset,"char_end":offset+len(line),
                          "quote":line,"quote_sha256":sha256(line.encode()).hexdigest()})
            offset+=len(line)
    elif format=="pdf":
        from pypdf import PdfReader
        reader=PdfReader(BytesIO(raw),strict=True)
        if reader.is_encrypted or len(reader.pages)>100:
            raise ValueError("Encrypted/oversize PDF unsupported")
        for page_no,page in enumerate(reader.pages,1):
            text=page.extract_text() or ""
            if not text.strip():
                unknown.append({"page":page_no,"reason":"NO_TEXT_LAYER_OCR_NOT_EXECUTED"})
            # Page text is a parser projection, not a byte offset into compressed PDF.
            spans.append({"page":page_no,"char_start":0,"char_end":len(text),
                          "quote":text,"quote_sha256":sha256(text.encode()).hexdigest(),
                          "anchor_scope":"EXTRACTED_PAGE_TEXT"})
            if page.images:
                unknown.append({"page":page_no,"reason":"IMAGE_CONTENT_NOT_INTERPRETED"})
            if "/Annots" in page:
                unknown.append({"page":page_no,"reason":"ANNOTATIONS_NOT_INTERPRETED"})
    else:
        raise ValueError("Unsupported source adapter")
    return {"schema":"qualityrag.document-source/v1","format":format,"source_sha256":digest,
            "spans":spans,"unsupported":unknown,"coverage":"UNKNOWN" if unknown else "TEXT_PROJECTION_ONLY",
            "original_custody_required":True}


def extract_candidates(documents, *, principal, authorize_source):
    """Reuse canonical extractors; preserve review quarantine and contradictions."""
    from pathlib import Path
    import sys
    parent=str(Path(__file__).resolve().parents[1]/"semantic_store")
    if parent not in sys.path: sys.path.insert(0,parent)
    from explicit_relation_extraction import extract_declared_relations
    from linguistic_relation_extraction import extract_linguistic_relations
    return {"explicit":extract_declared_relations(documents,principal=principal,authorize_source=authorize_source),
            "linguistic":extract_linguistic_relations(documents,principal=principal,authorize_source=authorize_source),
            "review_state":"QUARANTINED_UNTIL_AUTHENTICATED_REVIEW","can_generate":False}
