"""Run the v0.9 measured repeated workload with locally approved OpenCLIP.

  PYTHONPATH=tools/semantic_store python tools/semantic_store/run_measured_workloads.py \
    --root ./media --manifest ./reviewed-labels.json --repetitions 5 \
    --update-png selected.png --output ./measured-v09.json

The runner modifies a TEMPORARY copy, never the original. It requires the
same v0.7 reviewed-label format; independent review is not authenticated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from measured_workloads import run_measured_workload
from visual_semantic import OpenClipEncoder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--repetitions",type=int,default=5)
    parser.add_argument("--k",type=int,default=1)
    parser.add_argument("--update-png",default=None)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.manifest.is_file() or args.manifest.stat().st_size>100_000:
        parser.error("Manifest must be a JSON file under 100 KB")
    manifest=json.loads(args.manifest.read_text("utf-8"))
    print("Loading optional local OpenCLIP model; model load excluded from measurements",
          file=sys.stderr)
    encoder=OpenClipEncoder()
    result=run_measured_workload(
        args.root,manifest,encoder=encoder,principal="local-owner",
        authorize_source=lambda principal,sid,revision: (
            principal=="local-owner" and sid.startswith("bench/")),
        repetitions=args.repetitions,k=args.k,update_path=args.update_png)
    content=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if args.output:
        if args.output.exists():
            parser.error("Refusing to overwrite a previous measurement")
        args.output.write_text(content,encoding="utf-8")
    else:
        print(content,end="")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
