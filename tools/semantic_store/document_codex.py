"""Bounded textual document adapters to Semantic Codex.

PDF extraction: pypdf; DOCX: bounded OOXML main document; HTML: stdlib parser;
TXT: UTF-8 lines. None performs OCR, image/video recognition or complete
document interpretation. Unsupported structures are explicitly marked partial.
"""
from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile
from typing import Any

from semantic_codex import SCHEMA, CodexError, compile_source
from store import digest

FORMATS = ("pdf", "docx", "html", "htm", "txt")
MAX_TEXT = 500_000
MAX_PARTS = 500
_MAX_DOCX_XML = 8_000_000


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.fragments: list[str] = []

    def handle_starttag(self, name, attrs):
        if name in ("script", "style", "noscript", "template"):
            self.skip += 1
        if not self.skip and name in ("p", "div", "section", "article", "br", "h1", "h2", "h3", "li", "tr"):
            self.fragments.append("\n")

    def handle_endtag(self, name):
        if name in ("script", "style", "noscript", "template") and self.skip:
            self.skip -= 1
        if not self.skip and name in ("p", "div", "section", "article", "li", "tr"):
            self.fragments.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.fragments.append(data)


def _parts(source: bytes, format: str) -> list[dict]:
    if format == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(source), strict=True)
            if reader.is_encrypted:
                raise CodexError("Encrypted PDF requires separate authorized handling")
            if len(reader.pages) > MAX_PARTS:
                raise CodexError("PDF page limit exceeded")
            result=[]
            for index,page in enumerate(reader.pages, 1):
                text=page.extract_text() or ""
                if text.strip():
                    result.append({"anchor":{"kind":"pdf_page","page_number":index}, "text":text})
            return result
        except CodexError:
            raise
        except Exception as e:
            raise CodexError("PDF text extraction failed") from e

    if format == "docx":
        try:
            with ZipFile(BytesIO(source)) as doc:
                names=doc.namelist()
                if len(names)>1500 or len(set(names))!=len(names):
                    raise CodexError("Unbounded or duplicate OOXML entries")
                if "word/document.xml" not in names:
                    raise CodexError("DOCX main document missing")
                if doc.getinfo("word/document.xml").file_size > _MAX_DOCX_XML:
                    raise CodexError("DOCX XML exceeds decompression cap")
                xml=doc.read("word/document.xml")
            if len(xml)>_MAX_DOCX_XML or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise CodexError("Unsupported DOCX XML entity declarations")
            root=ET.fromstring(xml)
            namespace="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs=root.iter(namespace+"p")
            result=[]
            for index,para in enumerate(paragraphs,1):
                if index>MAX_PARTS:
                    raise CodexError("DOCX paragraph limit exceeded")
                text="".join(n.text or "" for n in para.iter(namespace+"t"))
                if text.strip():
                    result.append({"anchor":{"kind":"docx_paragraph","paragraph_number":index}, "text":text})
            return result
        except CodexError:
            raise
        except (BadZipFile,KeyError,ET.ParseError,RuntimeError,OSError,ValueError) as e:
            raise CodexError("DOCX text extraction failed") from e

    try:
        text=source.decode("utf-8-sig")
    except UnicodeError as e:
        raise CodexError("Document requires UTF-8 text") from e
    if format in ("html", "htm"):
        parser=TextHTML()
        try:
            parser.feed(text)
            parser.close()
        except (ValueError,AssertionError) as e:
            raise CodexError("HTML parsing failed") from e
        text="".join(parser.fragments)
    lines=text.splitlines()
    if len(lines)>MAX_PARTS:
        raise CodexError("Text block limit exceeded")
    return [{"anchor":{"kind":"html_line" if format in ("html","htm") else "text_line",
                        "line_number":index},
             "text":line}
            for index,line in enumerate(lines,1) if line.strip()]


def compile_document(source: bytes, *, source_id: str, revision: str, format: str) -> dict:
    if format not in FORMATS:
        return compile_source(source,source_id=source_id,revision=revision,format=format)
    if (not isinstance(source, bytes) or not 0<len(source)<=2_000_000
            or not isinstance(source_id,str) or not 0<len(source_id)<=256
            or not isinstance(revision,str) or not 0<len(revision)<=256):
        raise CodexError("Invalid document source or identity")
    parts=_parts(source,format)
    if len(parts)>MAX_PARTS or sum(len(p["text"]) for p in parts)>MAX_TEXT:
        raise CodexError("Document text extraction exceeds bounds")
    result={
        "schema":SCHEMA,
        "source":{"source_id":source_id,"revision":revision,"format":format,
                  "sha256":sha256(source).hexdigest(),"bytes":len(source)},
        "records":[{"id":f"{source_id}#{i}","anchor":part["anchor"],
                    "fields":{"text":{"type":"TEXT","value":part["text"]}},
                    "status":"STRUCTURAL_CANDIDATE"} for i,part in enumerate(parts)],
        "governance":{"packspec":"NOT_BOUND","admission":"INCONCLUSIVE"},
        "source_authenticity":"UNVERIFIED",
        "semantic_interpretation":"NOT_PERFORMED",
        "identity_recognition":"NOT_PERFORMED",
        "extraction_coverage":"PARTIAL_TEXT_ONLY",
        "extraction_limitations":[
            "No OCR, alt text, image contents, video frames, embedded media or attachments",
            "PDF page text, DOCX main-body paragraphs, HTML visible text or UTF-8 lines only",
            "Unsupported or invisible document content may remain unindexed",
        ],
        "reconstruction":{"source_bytes_required":True,"source_bytes_embedded":False,
                          "exact_source_bytes_recoverable_from_ir":False},
    }
    result["fingerprint"]=digest(result)
    return result
