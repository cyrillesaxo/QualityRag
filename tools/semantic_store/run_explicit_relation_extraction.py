"""Extract explicit relation declarations from a finite source manifest.

This script generates an inspectable candidate file, not KnowledgeGraph edges.
Review/persistence remains a separate explicit operation in Python.
"""
import argparse
import json
from pathlib import Path

from explicit_relation_extraction import extract_declared_relations


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.manifest.is_file() or args.manifest.stat().st_size>200_000:
        parser.error("Manifest must be an existing JSON file smaller than 200 KB")
    manifest=json.loads(args.manifest.read_text("utf-8"))
    if not isinstance(manifest,dict) or not isinstance(manifest.get("sources"),list):
        parser.error("Expected finite sources array")
    result=extract_declared_relations(
        manifest["sources"],principal="local-owner",
        authorize_source=lambda p,s,r:p=="local-owner" and s.startswith("regime/"))
    output=json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n"
    if args.output:
        if args.output.exists():
            parser.error("Refusing to overwrite existing candidate evidence")
        args.output.write_text(output,encoding="utf-8")
    else:
        print(output,end="")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
