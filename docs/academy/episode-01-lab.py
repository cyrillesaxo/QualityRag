"""QualityRag Academy 01 — deterministic evidence-gate exercise.

Run: PYTHONPATH=sdk/python python docs/academy/episode-01-lab.py
Synthetic evidence metadata; source truth is not checked.
"""
from qualityrag import evaluate

pack = {
    "id": "training.independence",
    "version": "1.0",
    "requirements": [{
        "id": "confirmed",
        "min_independent_sources": 2,
        "max_age_seconds": 86400,
    }],
}

a = {
    "id": "excerpt-A",
    "requirement_id": "confirmed",
    "origin": "bulletin-2026",
    "source_ref": "doc:A#1",
    "status": "SUPPORTS",
    "observed_at": "2026-11-02T10:00:00Z",
}
b_copy = {
    **a,
    "id": "excerpt-B",
    "source_ref": "doc:B#4",
}
b_independent = {**b_copy, "origin": "reviewed-source-B"}
b_contradict = {**b_independent, "status": "CONTRADICTS"}

for label, witnesses, expected in [
    ("one witness", [a], "INCONCLUSIVE"),
    ("two copies, same origin", [a, b_copy], "INCONCLUSIVE"),
    ("independent origins", [a, b_independent], "ADMIT"),
    ("contradicting evidence", [a, b_contradict], "REFUSE"),
]:
    result = evaluate(pack, witnesses, as_of="2026-11-02T11:00:00Z")
    print(label, result["verdict"], result["findings"][0]["reasons"])
    assert result["verdict"] == expected, (label, result)

print("PASS: 4 deterministic cases; ADMIT does not prove source truth.")
