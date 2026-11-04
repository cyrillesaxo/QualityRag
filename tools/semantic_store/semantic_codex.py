"""Semantic Codex v0.1: deterministic, source-bound cross-format annotations.

Normalize explicitly structured CSV rows, JSON objects and WebVTT cues to the
same candidate IR. This is a format-neutral *structural* IR, not an LLM,
OCR/transcription, named-person recognition, publisher authentication, or
semantic equivalence engine. It retains source bytes (with caller custody),
anchors, uncertainty and typed values without inventing implied relationships.
"""
from __future__ import annotations
import csv
import io
import json
import re
from hashlib import sha256
from typing import Any

from store import digest

SCHEMA = "qualityrag.semantic-codex/v0.1"
_TYPES = {"csv", "json", "vtt"}
_MAX_BYTES = 2_000_000
_MAX_RECORDS = 1000
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_ -]{0,127}$")
_TIMESTAMP = re.compile(r"^(?:(\d{2}):)?([0-5]\d):([0-5]\d)\.(\d{3})$")
_CUE = re.compile(r"(?:(?:\d{2}:)?[0-5]\d:[0-5]\d\.\d{3})\s+-->\s+(?:(?:\d{2}:)?[0-5]\d:[0-5]\d\.\d{3})")


class CodexError(ValueError):
    pass


def _timestamp(value: str) -> int:
    m = _TIMESTAMP.fullmatch(value)
    if not m:
        raise CodexError("Invalid VTT timestamp")
    return ((int(m[1] or 0)*3600 + int(m[2])*60 + int(m[3]))*1000 + int(m[4]))


def _value(x: Any) -> dict:
    """Preserve lexical strings rather than falsely interpreting dates/units."""
    if x is None:
        return {"type":"NULL","value":None}
    if type(x) is bool:
        return {"type":"BOOLEAN","value":x}
    if type(x) in (int,float):
        if type(x) is float and (x != x or abs(x) == float("inf")):
            raise CodexError("Nonfinite numeric literal")
        return {"type":"NUMBER","value":x}
    if isinstance(x,str):
        return {"type":"TEXT","value":x}
    raise CodexError("Nested JSON is not supported by this finite v0.1 adapter")


def _records_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    names = reader.fieldnames
    if not names or len(names)>100 or len(set(names))!=len(names):
        raise CodexError("CSV requires unique, bounded column names")
    if any(not isinstance(n,str) or not _FIELD.fullmatch(n) for n in names):
        raise CodexError("Invalid CSV header")
    rows=[]
    for index,row in enumerate(reader, start=2):
        if len(rows)>=_MAX_RECORDS:
            raise CodexError("Too many CSV rows")
        if None in row or any(v is None for v in row.values()):
            raise CodexError("Inconsistent CSV column count")
        rows.append({"anchor":{"kind":"csv_row","row_number":index},
                     "fields":{k:_value(row[k]) for k in names}})
    return rows


def _records_json(text: str) -> list[dict]:
    def unique_pairs(pairs):
        out={}
        for k,v in pairs:
            if k in out:
                raise CodexError("Duplicate JSON property")
            out[k]=v
        return out
    try:
        payload=json.loads(text,object_pairs_hook=unique_pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(CodexError("Nonfinite JSON number")))
    except (ValueError,TypeError,RecursionError) as e:
        raise CodexError("Invalid JSON input") from e
    if isinstance(payload,dict):
        items=[payload]
    elif isinstance(payload,list):
        items=payload
    else:
        raise CodexError("Expected JSON object or array of objects")
    if len(items)>_MAX_RECORDS:
        raise CodexError("Too many JSON objects")
    rows=[]
    for i,obj in enumerate(items):
        if not isinstance(obj,dict) or len(obj)>100:
            raise CodexError("Each JSON item must be an object of <=100 scalar properties")
        if any(not _FIELD.fullmatch(k) for k in obj):
            raise CodexError("Invalid JSON field name")
        rows.append({"anchor":{"kind":"json_pointer","pointer":("" if isinstance(payload,dict) else "/"+str(i))},
                     "fields":{k:_value(v) for k,v in obj.items()}})
    return rows


def _records_vtt(text: str) -> list[dict]:
    normalized=text.replace("\r\n","\n").replace("\r","\n")
    if not normalized.startswith("WEBVTT"):
        raise CodexError("WebVTT header required")
    blocks=re.split(r"\n\s*\n",normalized)
    rows=[]
    for block in blocks[1:]:
        lines=block.strip().split("\n")
        if not lines:
            continue
        if lines[0].startswith(("NOTE","STYLE","REGION")):
            raise CodexError("Unsupported VTT block; refusing to drop structure")
        cue_line=0 if "-->" in lines[0] else 1
        if len(lines)<=cue_line or not _CUE.fullmatch(lines[cue_line].strip()):
            raise CodexError("Invalid or unsupported VTT cue")
        start,end=(s.strip() for s in lines[cue_line].split("-->",1))
        a,b=_timestamp(start),_timestamp(end)
        if b<=a:
            raise CodexError("Non-positive video interval")
        speech="\n".join(lines[cue_line+1:])
        if not speech.strip():
            raise CodexError("Empty cue")
        rows.append({"anchor":{"kind":"time_range","start_ms":a,"end_ms":b},
                     "fields":{"text":_value(speech)}})
        if len(rows)>_MAX_RECORDS:
            raise CodexError("Too many media cues")
    return rows


def compile_source(source: bytes, *, source_id: str, revision: str, format: str) -> dict:
    if (not isinstance(source,bytes) or not 0<len(source)<=_MAX_BYTES
            or not isinstance(source_id,str) or not 0<len(source_id)<=256
            or not isinstance(revision,str) or not 0<len(revision)<=256
            or format not in _TYPES):
        raise CodexError("Invalid source bytes, identifier, revision or supported format")
    try:
        text=source.decode("utf-8-sig")
    except UnicodeError as e:
        raise CodexError("UTF-8 source required") from e
    try:
        records={"csv":_records_csv,"json":_records_json,"vtt":_records_vtt}[format](text)
    except (csv.Error,UnicodeError) as e:
        raise CodexError("Unsupported malformed structured source") from e
    body={"schema":SCHEMA,"source":{"source_id":source_id,"revision":revision,
             "format":format,"sha256":sha256(source).hexdigest(),"bytes":len(source)},
          "records":[{"id":f"{source_id}#{i}","anchor":row["anchor"],
                      "fields":row["fields"],"status":"STRUCTURAL_CANDIDATE"}
                     for i,row in enumerate(records)],
          "governance":{"packspec":"NOT_BOUND","admission":"INCONCLUSIVE"},
          "source_authenticity":"UNVERIFIED","semantic_interpretation":"NOT_PERFORMED",
          "identity_recognition":"NOT_PERFORMED",
          "reconstruction":{"source_bytes_required":True,
                            "source_bytes_embedded":False,
                            "exact_source_bytes_recoverable_from_ir":False}}
    body["fingerprint"]=digest(body)
    return body


def compare_structural_values(left: dict,right: dict) -> dict:
    """Compare values and types only. Different source anchors do not prove sameness."""
    def valid(v):
        b=dict(v)
        fp=b.pop("fingerprint",None)
        if b.get("schema")!=SCHEMA or digest(b)!=fp:
            raise CodexError("Invalid or modified semantic Codex artifact")
        return b
    l,r=valid(left),valid(right)
    a=[x["fields"] for x in l["records"]]
    b=[x["fields"] for x in r["records"]]
    return {"schema":"qualityrag.semantic-codex-comparison/v0.1",
            "left_fingerprint":left["fingerprint"],"right_fingerprint":right["fingerprint"],
            "same_typed_fields_in_order":a==b,
            "left_records":len(a),"right_records":len(b),
            "scope":"BOUNDED_STRUCTURAL_VALUE_COMPARISON_ONLY",
            "semantic_equivalence":"UNKNOWN","admission":"INCONCLUSIVE"}
