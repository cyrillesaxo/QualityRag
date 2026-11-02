"""Transparent lexical retrieval baseline over the synthetic corpus.

This script intentionally does NOT implement embeddings, OCR or production RAG.
It compares ranked lexical hits with and without a targeted query and checks
the QualityRag metadata gate on the returned witnesses.
"""
from collections import Counter
from pathlib import Path
import json
import re
from qualityrag import evaluate

DATA = json.loads(Path(__file__).with_name("corpus.json").read_text())
TOKENS = re.compile(r"[a-z0-9]+")
STOP = {"the","a","an","is","are","and","or","to","of","in","for","do","does","can","our","after","we","need","with"}
def tokenize(text):
    return [w for w in TOKENS.findall(text.lower()) if w not in STOP]
def rank(query, limit=4):
    q = Counter(tokenize(query))
    chunks = []
    for document in DATA["documents"]:
        for chunk in document["chunks"]:
            words = Counter(tokenize(chunk["text"]))
            score = sum(min(words[w], n) for w,n in q.items())
            chunks.append((score, chunk["id"]))
    return [cid for score,cid in sorted(chunks,key=lambda x:(-x[0],x[1])) if score>0][:limit]
def evaluate_hits(ids):
    lookup = {c["id"]:(d,c) for d in DATA["documents"] for c in d["chunks"]}
    evidence=[]
    for cid in ids:
        d,c=lookup[cid]
        if not c.get("requirement_id"): continue
        evidence.append(dict(id=cid,requirement_id=c["requirement_id"],origin=d["origin"],
            source_ref=d["id"]+"#"+cid,status=c["status"],observed_at="2026-11-02T10:00:00Z"))
    return evaluate(DATA["pack"],evidence,as_of="2026-11-02T10:05:00Z")
def run():
    generic=rank("on call automated recovery after dependency timeout",4)
    targeted=rank("EU sanctions screening compliance sign off emergency exception",6)
    initial=evaluate_hits(generic)
    recovered=evaluate_hits(list(dict.fromkeys(generic+targeted)))
    print("GENERIC QUERY RANKED CHUNKS:",generic)
    print("GENERIC QUERY VERDICT:",initial["verdict"])
    print("TARGETED QUERY RANKED CHUNKS:",targeted)
    print("AFTER BOTH QUERIES:",recovered["verdict"])
    for f in initial["findings"]: print("  ",f["requirement_id"],f["verdict"],f["reasons"])
    assert initial["verdict"]=="INCONCLUSIVE"
    assert "annex-d-187" in targeted
    return generic,targeted,initial,recovered
if __name__=="__main__":run()
