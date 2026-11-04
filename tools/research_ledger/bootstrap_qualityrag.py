"""Bootstrap cautiously sourced QualityRag milestone records.

This is a RECORDED HISTORY of merged pull requests, not independent
verification that the feature works on production or that a scientific theory
has been proven. Re-running will not overwrite claims, evidence or events.
"""
import sqlite3
from ledger import initialize, claim, evidence, assess, progress

MILESTONES=[
  (56,"document-ingestion","PDF/DOCX/HTML/TXT text ingestion was implemented"),
  (57,"visual-fingerprints","Bounded image/video-frame visual reference indexing was implemented"),
  (58,"scene-retrieval","An optional OpenCLIP image/text retrieval adapter was implemented"),
  (59,"visual-evaluation","Finite labeled retrieval quality evaluation and candidate provenance were implemented"),
  (60,"paired-benchmark","A finite filename-vs-visual paired benchmark harness was implemented"),
  (61,"economics-model","A bounded lifecycle-cost scenario calculator was implemented"),
  (62,"measured-workloads","A repeated retrieval workload measurement harness was implemented"),
  (63,"four-regimes","A finite R1–R4 candidate-regime comparison harness was implemented"),
  (64,"review-ledger","An unauthenticated relation review-cost input ledger was implemented"),
  (65,"explicit-relations","A bounded explicit RELATE syntax extractor was implemented"),
  (66,"linguistic-patterns","A bounded English-pattern relation extractor with polarity quarantine was implemented"),
]


def seed(db:sqlite3.Connection):
    initialize(db)
    created=0
    for pr,slug,statement in MILESTONES:
        claim_id="qualityrag.capability."+slug
        eid="qualityrag.pr."+str(pr)
        event_id="qualityrag.implemented."+str(pr)
        if db.execute("SELECT 1 FROM research_claims WHERE claim_id=?",(claim_id,)).fetchone():
            continue
        # A merged PR establishes implementation history, not user acceptance,
        # independently measured effectiveness, or correct semantic reasoning.
        claim(db,claim_id=claim_id,project="QualityRag",kind="CAPABILITY",statement=statement)
        evidence(db,evidence_id=eid,kind="CODE_COMMIT",
                 uri=f"https://github.com/cyrillesaxo/QualityRag/pull/{pr}",
                 description=f"Merged QualityRag pull request #{pr}; code-level provenance only",
                 metadata={"source":"GitHub PR","truth_status":"NOT_INDEPENDENTLY_VERIFIED"})
        assess(db,event_id=event_id,claim_id=claim_id,assessment="IMPLEMENTED",
               reason="Merged PR recorded in project history; independent functional and deployment verification missing",
               actor="bootstrap-unverified",evidence_ids=[eid])
        created+=1
    hypotheses=[
      ("qualityrag.hypothesis.semantic-superiority",
       "Semantic Codex provides better accuracy at equivalent capability and total cost."),
      ("qualityrag.hypothesis.12g-correctness",
       "The complete 12G semantic grammar preserves consequential distinctions across domains."),
      ("qualityrag.hypothesis.production-readiness",
       "QualityRag is deployable as a production-grade multi-tenant evidence-governance service."),
    ]
    for claim_id,statement in hypotheses:
        if not db.execute("SELECT 1 FROM research_claims WHERE claim_id=?",(claim_id,)).fetchone():
            claim(db,claim_id=claim_id,project="QualityRag",kind="HYPOTHESIS",statement=statement)
            created+=1
    return {"new_claims":created,"report":progress(db,project="QualityRag")}


if __name__=="__main__":
    import argparse,json
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    args=p.parse_args()
    db=sqlite3.connect(args.db)
    try:
        result=seed(db)
        print(json.dumps(result["report"]["counts"],indent=2))
    finally:db.close()
