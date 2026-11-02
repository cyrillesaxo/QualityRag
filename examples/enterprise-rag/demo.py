"""Deterministic simulation of a retrieval miss. Not a vector-search/LLM benchmark."""
from pathlib import Path
import json
from qualityrag import evaluate

DATA = json.loads(Path(__file__).with_name("corpus.json").read_text())
CLOCK = "2026-11-02T10:05:00Z"
OBSERVED = "2026-11-02T10:00:00Z"
chunks = {chunk["id"]: (doc, chunk) for doc in DATA["documents"] for chunk in doc["chunks"]}

def witnesses(ids):
    result = []
    for cid in ids:
        doc, chunk = chunks[cid]
        if not chunk.get("requirement_id"):
            continue
        result.append({
            "id": cid, "requirement_id": chunk["requirement_id"],
            "origin": doc["origin"], "source_ref": doc["id"] + "#" + cid,
            "status": chunk["status"], "observed_at": OBSERVED
        })
    return result

def run():
    first = DATA["retrieval"]["initial"]
    second = DATA["retrieval"]["targeted"]
    print("QUESTION:", DATA["question"])
    print("\nINITIAL RETRIEVAL:", ", ".join(first))
    initial = evaluate(DATA["pack"], witnesses(first), as_of=CLOCK)
    print("INITIAL VERDICT:", initial["verdict"])
    for f in initial["findings"]:
        print(" ", f["requirement_id"], f["verdict"], f["reasons"])
    assert initial["verdict"] == "INCONCLUSIVE"
    assert sum(x["verdict"] == "INCONCLUSIVE" for x in initial["findings"]) == 2
    print("\nTARGETED RETRIEVAL:", ", ".join(second))
    expanded = evaluate(DATA["pack"], witnesses(first + second), as_of=CLOCK)
    print("AFTER TARGETED RETRIEVAL:", expanded["verdict"])
    assert expanded["verdict"] == "ADMIT"
    print("ADMIT is metadata gate satisfaction, not authorization to restart the gateway.")
    print("Compliance approval applicability and source authenticity are not established.")
    return initial, expanded

if __name__ == "__main__":
    run()
