"""Evaluate an existing v0.7 retrieval receipt under a stated cost scenario.

The output is a scenario estimate, NEVER a measurement of repeated workloads.
Pass a JSON object of explicit measured/assumed extras, e.g. in docs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from economics import evaluate_lifecycle


def _read(path: Path):
    if not path.is_file() or path.stat().st_size > 500_000:
        raise ValueError("Input must be a file under 500 KB")
    return json.loads(path.read_text("utf-8"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--scenario",type=Path,required=True)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    receipt=_read(args.receipt)
    scenario=_read(args.scenario)
    if not isinstance(scenario,dict):
        parser.error("Scenario must be a JSON object")
    result=evaluate_lifecycle(receipt,**scenario)
    payload=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if args.output:
        if args.output.exists():
            parser.error("Refusing to replace existing economics receipt")
        args.output.write_text(payload,encoding="utf-8")
    else:
        print(payload,end="")


if __name__=="__main__":
    main()
