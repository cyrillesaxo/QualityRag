"""Record and inspect QualityRag research progress in a persistent local ledger.

No cloud credentials are required. The same schema contract is also provided
for a future Postgres service. This CLI never infers VALIDATED from CI.
"""
import argparse
import json
from pathlib import Path
import sqlite3
from ledger import initialize,claim,evidence,assess,link,progress,verify_integrity

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",type=Path,required=True)
    subs=p.add_subparsers(dest="command",required=True)
    subs.add_parser("init")
    a=subs.add_parser("claim")
    for k in ("id","project","kind","statement"):a.add_argument("--"+k,required=True)
    a=subs.add_parser("evidence")
    for k in ("id","kind","uri","description"):a.add_argument("--"+k,required=True)
    a.add_argument("--sha256")
    a=subs.add_parser("assess")
    for k in ("id","claim","status","reason","actor"):a.add_argument("--"+k,required=True)
    a.add_argument("--evidence",nargs="*",default=[])
    a=subs.add_parser("link")
    for k in ("id","from-claim","to-claim","relation"):a.add_argument("--"+k,required=True)
    a=subs.add_parser("report");a.add_argument("--project")
    subs.add_parser("verify")
    args=p.parse_args()
    args.db.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(args.db)
    initialize(db)
    try:
        if args.command=="init":out={"initialized":True,"db":str(args.db)}
        elif args.command=="claim":
            out=claim(db,claim_id=args.id,project=args.project,kind=args.kind,statement=args.statement)
        elif args.command=="evidence":
            out=evidence(db,evidence_id=args.id,kind=args.kind,uri=args.uri,
                         description=args.description,content_sha256=args.sha256)
        elif args.command=="assess":
            out=assess(db,event_id=args.id,claim_id=args.claim,assessment=args.status,
                       reason=args.reason,actor=args.actor,evidence_ids=args.evidence)
        elif args.command=="link":
            out=link(db,link_id=args.id,from_claim=args.from_claim,
                     to_claim=args.to_claim,relation=args.relation)
        elif args.command=="report":out=progress(db,project=args.project)
        else:out=verify_integrity(db)
        print(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2))
        return 0 if args.command!="verify" or out["consistent"] else 2
    finally:db.close()

if __name__=="__main__":
    raise SystemExit(main())
