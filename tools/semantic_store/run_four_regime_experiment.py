"""Run the finite R1–R4 regime contrast against a local JSON manifest."""
import argparse
import json
from pathlib import Path
from four_regime_experiment import run_regime_contrast


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--repetitions",type=int,default=5)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.manifest.is_file() or args.manifest.stat().st_size>200_000:
        parser.error("Expected a JSON manifest under 200 KB")
    manifest=json.loads(args.manifest.read_text("utf8"))
    result=run_regime_contrast(manifest,repetitions=args.repetitions,
        principal="local-reviewer",
        authorize_source=lambda principal,source,revision: (
            principal=="local-reviewer" and source.startswith("regime/")))
    encoded=json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n"
    if args.output:
        if args.output.exists():
            parser.error("Output already exists; refusing to overwrite a measurement")
        args.output.write_text(encoded,encoding="utf8")
    else:
        print(encoded,end="")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
