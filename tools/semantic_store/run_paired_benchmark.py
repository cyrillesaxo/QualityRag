"""Run a user-reviewed paired image retrieval benchmark locally.

Example:
  PYTHONPATH=tools/semantic_store python tools/semantic_store/run_paired_benchmark.py \
    --root /path/to/images --manifest /path/to/labels.json --k 5

Requires opt-in OpenCLIP and CPU weights. Does not transfer media to a service.
"""
import argparse
import json
from pathlib import Path
import sys

from paired_benchmark import compare_directory
from visual_semantic import OpenClipEncoder


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--k",type=int,default=5)
    parser.add_argument("--output",type=Path,default=None)
    args=parser.parse_args(argv)
    if not args.manifest.is_file() or args.manifest.stat().st_size>100_000:
        parser.error("Manifest must be a local JSON file of at most 100 KB")
    manifest=json.loads(args.manifest.read_text("utf-8"))
    print("Loading optional OpenCLIP model (not included in timing measurements)",file=sys.stderr)
    encoder=OpenClipEncoder()
    result=compare_directory(
        args.root,manifest,encoder=encoder,principal="local-owner",
        authorize_source=lambda principal,source,revision: (
            principal=="local-owner" and source.startswith("bench/")),
        k=args.k)
    encoded=json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.output is not None:
        if args.output.exists():
            parser.error("Refusing to overwrite existing benchmark receipt")
        args.output.write_text(encoded,encoding="utf-8")
    else:
        print(encoded,end="")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
