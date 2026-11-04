"""Compare explicit RELATE declarations with bounded ordinary-English patterns.

The comparison reports candidate inventories and elapsed extraction time.
It does NOT rank truth, infer identities or write edges into KnowledgeGraph.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from linguistic_relation_extraction import compare_extractors

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.manifest.is_file() or args.manifest.stat().st_size>200_000:
        parser.error("Expected a local JSON manifest no larger than 200 KB")
    manifest=json.loads(args.manifest.read_text("utf-8"))
    if not isinstance(manifest,dict) or not isinstance(manifest.get("sources"),list):
        parser.error("Expected a source manifest")
    result=compare_extractors(
        manifest["sources"],principal="local-owner",
        authorize_source=lambda p,s,r:p=="local-owner" and s.startswith("regime/"))
    text=json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n"
    if args.output:
        if args.output.exists():
            parser.error("Refusing to overwrite an earlier comparison receipt")
        args.output.write_text(text,encoding="utf-8")
    else:
        print(text,end="")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
