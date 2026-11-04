"""Constrained natural-language relation candidates, contradictions and review gate.

This is a transparent, deterministic English-pattern recognizer, not a general
language model. It supports literal known source IDs in simple affirmative and
explicitly negated sentences. It does NOT infer a relation from incidental
co-occurrence, resolve pronouns, model temporal changes or verify source truth.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from time import perf_counter_ns

from explicit_relation_extraction import extract_declared_relations
from semantic_codex import CodexError
from store import SemanticStore, canonical_bytes, digest

SCHEMA="qualityrag.linguistic-relation-candidates/v1.3"
MAX_SOURCES=40
MAX_CANDIDATES=100
# The deliberately small grammar is documented and independently testable.
# Leading subject + known action + optional explicit negator + object.
ACTION={
    "supports":("SUPPORTS","supports"),
    "references":("REFERENCES","references"),
    "relates to":("RELATES_TO","relates to"),
    "depends on":("DEPENDS_ON","depends on"),
}
_PATTERN=re.compile(
    r"(?<![\w])(?P<subject>[A-Za-z0-9]{1,50})\s+"
    r"(?P<negative>does\s+not\s+)?"
    r"(?P<verb>supports|references|relates\s+to|depends\s+on|"
    r"support|reference|relate\s+to|depend\s+on)\s+"
    r"(?P<object>[A-Za-z0-9]{1,50})\s*"
    r"(?P<terminal>[.;!?]|$)",re.IGNORECASE)
_LEMMA={
    "supports":"SUPPORTS","support":"SUPPORTS",
    "references":"REFERENCES","reference":"REFERENCES",
    "relates to":"RELATES_TO","relate to":"RELATES_TO",
    "depends on":"DEPENDS_ON","depend on":"DEPENDS_ON",
}


def _validate_sources(sources, principal, authorize_source):
    if not isinstance(sources,list) or not 1<=len(sources)<=MAX_SOURCES or not principal or not callable(authorize_source):
        raise CodexError("Bounded source inventory and authorization callback required")
    known={}
    for s in sources:
        if (not isinstance(s,dict) or set(s)!={"id","text"} or
            not isinstance(s["id"],str) or not 1<=len(s["id"])<=50 or
            not s["id"].isalnum() or s["id"] in known or
            not isinstance(s["text"],str) or not 1<=len(s["text"])<=1000):
            raise CodexError("Invalid or duplicate source")
        known[s["id"]]=s["text"]
    for key,body in known.items():
        revision=sha256(json.dumps({"text":body},sort_keys=True).encode()).hexdigest()
        if not authorize_source(principal,"regime/"+key+".json",revision):
            raise PermissionError("Inaccessible source makes extraction incomplete")
    return known


def extract_linguistic_relations(sources, *, principal, authorize_source):
    known=_validate_sources(sources,principal,authorize_source)
    start=perf_counter_ns()
    candidates=[]
    unresolved=[]
    for s in sources:
        body=s["text"]
        # Prevent interpreting code-like source declarations as prose.
        offset=0
        for line_number,line in enumerate(body.splitlines(keepends=True),1):
            raw=line.rstrip("\r\n")
            if raw.startswith("RELATE "):
                offset+=len(line)
                continue
            for match in _PATTERN.finditer(raw):
                a,b=match.group("subject"),match.group("object")
                if a not in known or b not in known:
                    unresolved.append({"source_id":s["id"],"line":line_number,
                                       "status":"UNKNOWN_NAMED_ENTITY"})
                    continue
                negative=match.group("negative") is not None
                verb=" ".join(match.group("verb").lower().split())
                # Simple grammatical validity: does-not uses base verb;
                # affirmative uses third-person singular.
                if (negative and verb in ACTION) or (not negative and verb not in ACTION):
                    unresolved.append({"source_id":s["id"],"line":line_number,
                                       "status":"GRAMMATICAL_FORM_NOT_SUPPORTED"})
                    continue
                span_start=offset+match.start()
                span_end=offset+match.end()
                snippet=body[span_start:span_end]
                record={
                    "from":a,"to":b,"relation":_LEMMA[verb],
                    "polarity":"NEGATIVE" if negative else "POSITIVE",
                    "evidence_source":s["id"],
                    "source_sha256":sha256(body.encode()).hexdigest(),
                    "quoted_evidence":snippet,
                    "anchor":{"kind":"text_span","line":line_number,
                              "start":span_start,"end":span_end},
                    "extractor":"BOUNDED_ENGLISH_PATTERN_V1",
                }
                record["candidate_id"]=digest(record)
                candidates.append(record)
                if len(candidates)>MAX_CANDIDATES:
                    raise CodexError("Exceeded finite candidate budget")
            offset+=len(line)
    if len({x["candidate_id"] for x in candidates})!=len(candidates):
        raise CodexError("Duplicate candidate identities")
    groups={}
    for candidate in candidates:
        key=(candidate["from"],candidate["relation"],candidate["to"])
        groups.setdefault(key,[]).append(candidate)
    conflicts=[]
    for key,items in sorted(groups.items()):
        if {x["polarity"] for x in items}=={"POSITIVE","NEGATIVE"}:
            conflicts.append({"from":key[0],"relation":key[1],"to":key[2],
                              "candidate_ids":[x["candidate_id"] for x in items],
                              "status":"POTENTIAL_CONTRADICTION_NOT_SEMANTIC_PROOF"})
    duration=(perf_counter_ns()-start)/1_000_000
    return {
        "schema":SCHEMA,"candidates":candidates,
        "potential_contradictions":conflicts,"unresolved_mentions":unresolved,
        "measured_extraction_ms":round(duration,6),
        "source_inventory_fingerprint":digest(sources),
        "coverage":"FINITE_SUPPORTED_ENGLISH_PATTERNS_ONLY",
        "semantic_entailment":"NOT_VERIFIED",
        "source_authenticity":"UNVERIFIED",
        "admission":"INCONCLUSIVE","can_generate":False,
    }


def compare_extractors(sources, *, principal, authorize_source):
    """Apply both v1.2 explicit grammar and v1.3 prose patterns to same sources."""
    explicit=extract_declared_relations(sources,principal=principal,authorize_source=authorize_source)
    linguistic=extract_linguistic_relations(sources,principal=principal,authorize_source=authorize_source)
    def keys(rows):
        return sorted({(x["from"],x["relation"],x["to"]) for x in rows})
    return {"schema":"qualityrag.relation-extractor-comparison/v1.3",
            "source_inventory_fingerprint":digest(sources),
            "explicit_declarations":len(explicit["candidates"]),
            "linguistic_candidates":len(linguistic["candidates"]),
            "explicit_relation_keys":keys(explicit["candidates"]),
            "linguistic_positive_keys":keys(
                [x for x in linguistic["candidates"] if x["polarity"]=="POSITIVE"]),
            "potential_contradictions":linguistic["potential_contradictions"],
            "explicit_extraction_ms":explicit["extraction_ms_measured"],
            "linguistic_extraction_ms":linguistic["measured_extraction_ms"],
            "quality_ground_truth":"NOT_SUPPLIED",
            "false_positive_rate":"UNMEASURED",
            "review_cost":"UNMEASURED",
            "semantic_parity":"NOT_ESTABLISHED_DIFFERENT_GRAMMARS",
            "admission":"INCONCLUSIVE","can_generate":False}


def project_linguistic_reviews(store: SemanticStore, extraction: dict, *,
                               sources: list[dict], verdicts: list[dict],
                               principal: str, authorize_source):
    """Only caller-SUPPORTED, noncontradictory candidates enter an unverified graph."""
    reference=extract_linguistic_relations(sources,principal=principal,
                                           authorize_source=authorize_source)
    if (not isinstance(extraction,dict) or extraction.get("schema")!=SCHEMA or
            extraction.get("source_inventory_fingerprint")!=reference["source_inventory_fingerprint"] or
            digest(extraction.get("candidates"))!=digest(reference["candidates"]) or
            digest(extraction.get("potential_contradictions"))!=digest(reference["potential_contradictions"]) or
            extraction.get("unresolved_mentions")!=reference["unresolved_mentions"]):
        raise CodexError("Source-derived linguistic candidate inventory mismatch")
    candidates=reference["candidates"]
    if not isinstance(verdicts,list) or len(verdicts)!=len(candidates):
        raise CodexError("Complete reviewer inventory required")
    reviewed={}
    for item in verdicts:
        if (not isinstance(item,dict) or set(item)!={"candidate_id","verdict","review_ms"} or
                item["verdict"] not in ("SUPPORTED","REJECTED","UNCERTAIN") or
                not isinstance(item["candidate_id"],str) or item["candidate_id"] in reviewed or
                type(item["review_ms"]) not in (int,float) or
                not __import__("math").isfinite(item["review_ms"]) or
                item["review_ms"]<0 or item["review_ms"]>3_600_000):
            raise CodexError("Invalid reviewer receipt")
        reviewed[item["candidate_id"]]=item
    if set(reviewed)!={c["candidate_id"] for c in candidates}:
        raise CodexError("Unmatched reviewer inventory")
    conflicts={candidate_id for x in reference["potential_contradictions"]
               for candidate_id in x["candidate_ids"]}
    revisions={s["id"]:sha256(json.dumps({"text":s["text"]},sort_keys=True).encode()).hexdigest()
               for s in sources}
    persisted=0
    with store.db:
        for c in candidates:
            if reviewed[c["candidate_id"]]["verdict"]!="SUPPORTED" or c["candidate_id"] in conflicts or c["polarity"]!="POSITIVE":
                continue
            for entity in (c["from"],c["to"]):
                stored=store.db.execute(
                    "SELECT kind FROM semantic_versions WHERE object_id=? AND revision=?",
                    ("node:"+entity,revisions[entity])).fetchone()
                if not stored or stored[0]!="BENCHMARK_CANDIDATE":
                    raise CodexError("Missing source-versioned candidate node")
            properties={
                "candidate_id":c["candidate_id"],
                "source_id":c["evidence_source"],
                "source_sha256":c["source_sha256"],
                "anchor":c["anchor"],
                "polarity":c["polarity"],
                "review":"CALLER_SUPPORTED_UNAUTHENTICATED",
                "semantic_verification":"NOT_PERFORMED",
            }
            edge_id="linguistic:"+c["candidate_id"]
            packed=canonical_bytes(properties).decode()
            existing=store.db.execute(
                "SELECT properties_json FROM semantic_edges WHERE edge_id=?",
                (edge_id,)).fetchone()
            if existing:
                if existing[0]!=packed:
                    raise CodexError("Immutable linguistic projection collision")
                continue
            store.db.execute("INSERT INTO semantic_edges VALUES(?,?,?,?,?,?,?,?)",
                             (edge_id,"KNOWLEDGE","node:"+c["from"],revisions[c["from"]],
                              "node:"+c["to"],revisions[c["to"]],c["relation"],packed))
            persisted+=1
    return {
        "schema":"qualityrag.linguistic-review-projection/v1.3",
        "candidate_count":len(candidates),
        "persisted_unverified_positive_edges":persisted,
        "contradictory_candidate_count":len(conflicts),
        "rejected_review_count":sum(v["verdict"]=="REJECTED" for v in reviewed.values()),
        "uncertain_review_count":sum(v["verdict"]=="UNCERTAIN" for v in reviewed.values()),
        "review_ms_caller_supplied":sum(v["review_ms"] for v in reviewed.values()),
        "extraction_ms_measured":reference["measured_extraction_ms"],
        "review_authentication":"UNVERIFIED",
        "contradiction_status":"SYNTACTIC_POLARITY_ONLY",
        "admission":"INCONCLUSIVE","can_generate":False,
    }
