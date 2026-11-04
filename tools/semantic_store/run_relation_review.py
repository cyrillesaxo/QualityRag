"""Run the four-regime experiment with an explicit finite relation-review ledger."""
import argparse
import json
from pathlib import Path
from relation_review_experiment import run_candidate_review


def load(path):
    if not path.is_file() or path.stat().st_size > 200_000:
        raise ValueError("Expected a local JSON file no larger than 200 KB")
    return json.loads(path.read_text("utf-8"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--ledger",type=Path,required=True)
    parser.add_argument("--repetitions",type=int,default=3)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    result=run_candidate_review(load(args.manifest),load(args.ledger),
       principal="local-reviewer",
       authorize_source=lambda p,s,r:p=="local-reviewer" and s.startswith("regime/"),
       repetitions=args.repetitions)
    data=json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n"
    if args.output:
        if args.output.exists():
            parser.error("Refusing to overwrite an existing receipt")
        args.output.write_text(data,encoding="utf-8")
    else:
        print(data,end="")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
