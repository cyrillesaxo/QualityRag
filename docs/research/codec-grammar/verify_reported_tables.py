#!/usr/bin/env python3
"""Verify arithmetic and reported conclusions from primary research tables.

This does NOT execute PH02, rebuild packets or verify source hashes.
"""
import json
from pathlib import Path

def main():
    document = json.loads((Path(__file__).parent / "reported-tables.json").read_text())
    assert document["schema"] == "qualityrag.codec-grammar-reported-tables/v0.1"
    dev = [dict(zip(document["development"]["fields"], row)) for row in document["development"]["rows"]]
    fresh = [dict(zip(document["fresh"]["fields"], row)) for row in document["fresh"]["rows"]]
    assert len(dev) == 9 and len(fresh) == 12
    dev_wins = sum(row["ph02_bytes"] < row["frozen_best_native_bytes"] for row in dev)
    dev_without_zero = sum(row["without_zero_bytes"] < row["frozen_best_native_bytes"] for row in dev)
    dev_dense_only = sum(row["dense_only_bytes"] < row["frozen_best_native_bytes"] for row in dev)
    ph01_wins = sum(row["ph01_bytes"] < row["frozen_best_native_bytes"] for row in dev)
    fresh_wins = sum(row["selected_bytes"] < row["baseline_bytes"] for row in fresh)
    fresh_ties = sum(row["selected_bytes"] == row["baseline_bytes"] for row in fresh)
    assert (ph01_wins, dev_wins, dev_without_zero, dev_dense_only) == (0, 6, 6, 0)
    assert (fresh_wins, fresh_ties) == (6, 6)
    assert all(row["selected_bytes"] <= row["baseline_bytes"] for row in fresh)
    winning = [row for row in fresh if row["selected_bytes"] < row["baseline_bytes"]]
    assert all(row["dense_only_bytes"] is not None for row in winning)
    assert all(row["dense_only_bytes"] < row["baseline_bytes"] for row in winning)
    assert all(439 <= row["dense_only_bytes"] - row["selected_bytes"] <= 452 for row in winning)
    print(json.dumps({
        "status": "PASS: reported table arithmetic only; no codec replay",
        "development": {"cases":len(dev),"ph01_wins":ph01_wins,"ph02_wins":dev_wins,"no_zero_wins":dev_without_zero,"dense_only_wins":dev_dense_only},
        "fresh": {"cases":len(fresh),"wins":fresh_wins,"ties":fresh_ties}
    }, indent=2))

if __name__ == "__main__":
    main()
