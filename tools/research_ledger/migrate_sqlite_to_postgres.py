"""Transactional lossless SQLite -> PostgreSQL Research Memory migration.

Read-only SQLite input. Reject any target differences; repeat identical imports
are safe. Validates SQLite hash chains before importing. Does not authenticate
GitHub evidence or enable scientific validation.
"""
import argparse
import json
import sqlite3
from pathlib import Path

from ledger import verify_integrity, LedgerError
from postgres import connect, progress


TABLES=(
 ("research_claims","research.claims",
  ["claim_id","project","kind","statement","created_at","content_hash"]),
 ("research_evidence","research.evidence",
  ["evidence_id","kind","uri","description","content_sha256","observed_at","metadata","record_hash"]),
 ("research_events","research.assessment_events",
  ["event_id","claim_id","assessment","reason","observed_at","actor","evidence_ids","previous_event_hash","event_hash"]),
 ("research_links","research.claim_links",
  ["link_id","from_claim","to_claim","relation","created_at","link_hash"]),
)
PK={"research_claims":"claim_id","research_evidence":"evidence_id",
    "research_events":"event_id","research_links":"link_id"}


def import_sqlite(sqlite_path: Path, conn, *, dry_run:bool=False):
    if not sqlite_path.is_file():raise LedgerError("Existing SQLite ledger required")
    src=sqlite3.connect("file:"+str(sqlite_path.resolve())+"?mode=ro",uri=True)
    try:
        integrity=verify_integrity(src)
        if not integrity["consistent"]:raise LedgerError("Source ledger hash integrity failed")
        if src.execute("SELECT 1 FROM research_events WHERE assessment='VALIDATED' LIMIT 1").fetchone():
            raise LedgerError("VALIDATED migration requires destination-bound signed review; automatic transfer is refused")
        source_counts={name:src.execute("SELECT COUNT(*) FROM "+name).fetchone()[0] for name,_,_ in TABLES}
        # No partial import: all rows are compared first in a single DB transaction.
        inserted=0
        with conn.transaction():
            # Lock solely this import path against other simultaneous imports.
            conn.execute("SELECT pg_advisory_xact_lock(469145, 1281)")
            for source,target,columns in TABLES:
                source_rows=src.execute("SELECT * FROM "+source+" ORDER BY "+PK[source]).fetchall()
                names=columns
                for raw in source_rows:
                    value=list(raw)
                    if source=="research_evidence":
                        value[6]=json.loads(value[6])
                    if source=="research_events":
                        value[6]=json.loads(value[6])
                    pk=value[0]
                    dbrow=conn.execute(
                        "SELECT "+",".join(names)+" FROM "+target+" WHERE "+names[0]+"=%s",
                        (pk,)).fetchone()
                    # psycopg decodes jsonb into Python objects. SQLite timestamps
                    # are kept as strings to preserve event hash preimages.
                    if dbrow is not None:
                        if tuple(value)!=tuple(dbrow):
                            raise LedgerError("Conflicting immutable target row: "+source+" "+str(pk))
                        continue
                    if not dry_run:
                        markers=["%s::jsonb" if col in ("metadata","evidence_ids") else "%s" for col in names]
                        conn.execute("INSERT INTO "+target+" ("+",".join(names)+") VALUES ("+
                                     ",".join(markers)+")",
                                     tuple(json.dumps(x,sort_keys=True) if isinstance(x,(dict,list)) else x
                                           for x in value))
                    inserted+=1
            if dry_run:
                # Advisory locks are released at rollback; do not write.
                pass
        return {"schema":"qualityrag.research-migration/v0.2",
                "dry_run":dry_run,"source_counts":source_counts,
                "new_rows":0 if dry_run else inserted,
                "would_import_rows":inserted,
                "integrity":"SQLITE_HASH_CHAIN_VERIFIED",
                "external_source_attestation":"NOT_PERFORMED"}
    finally:
        src.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite",type=Path,required=True)
    p.add_argument("--dsn-env",default="QUALITYRAG_RESEARCH_DATABASE_URL")
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    import os
    dsn=os.environ.get(args.dsn_env)
    if not dsn:p.error("Set the named PostgreSQL DSN environment variable")
    with connect(dsn) as conn:
        result=import_sqlite(args.sqlite,conn,dry_run=args.dry_run)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
