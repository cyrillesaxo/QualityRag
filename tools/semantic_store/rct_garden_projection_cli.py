"""Export the existing append-only research ledger as a read-only Garden view."""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path

from rct_garden_projection import project_garden


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--project", default="QualityRag")
    parser.add_argument("--max-claims", type=int, default=200)
    parser.add_argument("--max-events", type=int, default=2000)
    args = parser.parse_args()
    db_path = Path(args.db)
    if not db_path.is_file():
        raise ValueError("Research ledger does not exist; refusing to create an empty database")
    # Use SQLite's read-only URI; the command cannot modify the input DB.
    with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        payload = project_garden(db, project=args.project,
                                 maximum_claims=args.max_claims,
                                 maximum_events=args.max_events)
    target = Path(args.output)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps({
        "schema": payload["schema"], "summary": payload["summary"],
        "qualityrag_admission": payload["qualityrag_admission"],
        "promotion_authorized": payload["promotion_authorized"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
