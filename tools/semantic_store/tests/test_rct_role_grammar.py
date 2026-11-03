"""Typed role-graph falsification of lexically invisible consequential changes."""
from hashlib import sha256
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rct_role_grammar import audit_typed_role_graph
from store import digest


def anchor(text, quote, *, occurrence=0):
    start = -1
    pos = 0
    for _ in range(occurrence+1):
        start = text.find(quote,pos)
        if start < 0:
            raise ValueError("Missing test quote")
        pos = start+len(quote)
    return {"start":start,"end":start+len(quote),"quote":quote}


def fact(text, name, predicate, **roles):
    return {
        "id":name,"predicate":predicate,
        "bindings":[{"role":role,"entity":entity,
                     "span":anchor(text,quote)}
                    for role,(entity,quote) in roles.items()],
    }


def run(source,candidate,source_facts,candidate_facts):
    return audit_typed_role_graph(
        source=source,candidate=candidate,
        source_facts=source_facts,candidate_facts=candidate_facts,
        source_sha256=sha256(source.encode()).hexdigest(),
        candidate_sha256=sha256(candidate.encode()).hexdigest(),
        source_inventory_sha256=digest(source_facts),
        candidate_inventory_sha256=digest(candidate_facts))


class RoleBindingGrammarTests(unittest.TestCase):
    def test_obligor_and_beneficiary_swap_detected_without_lexical_difference(self):
        source="Alice must pay Bob."
        candidate="Bob must pay Alice."
        before=[fact(source,"pay","PAY",OBLIGOR=("alice","Alice"),
                     BENEFICIARY=("bob","Bob"))]
        after=[fact(candidate,"pay","PAY",OBLIGOR=("bob","Bob"),
                    BENEFICIARY=("alice","Alice"))]
        receipt=run(source,candidate,before,after)
        self.assertEqual(receipt["verdict"],"REFUSE")
        self.assertEqual(receipt["findings"][0]["status"],"ROLE_BINDING_CHANGED")
        self.assertFalse(receipt["can_generate"])

    def test_laterality_change_detected(self):
        source="Administer drops to the left eye."
        candidate="Administer drops to the right eye."
        before=[fact(source,"eye","ADMINISTER",SIDE=("left","left"))]
        after=[fact(candidate,"eye","ADMINISTER",SIDE=("right","right"))]
        self.assertEqual(run(source,candidate,before,after)["verdict"],"REFUSE")

    def test_unit_change_detected_even_with_same_number(self):
        source="Set pressure to 5 psi."
        candidate="Set pressure to 5 bar."
        before=[fact(source,"pressure","SET_THRESHOLD",
                     VALUE=("5","5"),UNIT=("psi","psi"))]
        after=[fact(candidate,"pressure","SET_THRESHOLD",
                    VALUE=("5","5"),UNIT=("bar","bar"))]
        receipt=run(source,candidate,before,after)
        self.assertEqual(receipt["verdict"],"REFUSE")

    def test_ordering_change_detected(self):
        source="Inspect before starting the procedure."
        candidate="Inspect after starting the procedure."
        before=[fact(source,"inspection","ORDER",RELATION=("BEFORE","before"),
                     ACTION=("inspect","Inspect"))]
        after=[fact(candidate,"inspection","ORDER",RELATION=("AFTER","after"),
                    ACTION=("inspect","Inspect"))]
        self.assertEqual(run(source,candidate,before,after)["verdict"],"REFUSE")

    def test_passive_voice_semantically_equal_only_inconclusive(self):
        source="Alice must pay Bob."
        candidate="Bob must be paid by Alice."
        before=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"),
                     BENEFICIARY=("bob","Bob"))]
        after=[fact(candidate,"payment","PAY",BENEFICIARY=("bob","Bob"),
                    OBLIGOR=("alice","Alice"))]
        receipt=run(source,candidate,before,after)
        self.assertEqual(receipt["verdict"],"INCONCLUSIVE")
        self.assertEqual(receipt["findings"][0]["status"],
                         "DECLARED_ROLE_BINDINGS_PRESERVED")
        self.assertEqual(receipt["semantic_completeness"],"UNKNOWN")

    def test_missing_fact_refuses(self):
        source="Alice must pay Bob."
        candidate="The agreement was updated."
        before=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"))]
        after=[fact(candidate,"update","UPDATE",OBJECT=("agreement","agreement"))]
        result=run(source,candidate,before,after)
        self.assertEqual(result["verdict"],"REFUSE")
        self.assertEqual({f["status"] for f in result["findings"]},
                         {"REQUIRED_FACT_MISSING","ADDED_FACT_UNREVIEWED"})

    def test_added_fact_is_unknown_not_semantic_admit(self):
        source="Alice must pay Bob."
        candidate="Alice must pay Bob. Alice must sign."
        before=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"))]
        after=[fact(candidate,"payment","PAY",OBLIGOR=("alice","Alice")),
               fact(candidate,"sign","SIGN",ACTOR=("alice","Alice"))]
        result=run(source,candidate,before,after)
        self.assertEqual(result["verdict"],"INCONCLUSIVE")
        self.assertTrue(any(f["status"]=="ADDED_FACT_UNREVIEWED"
                            for f in result["findings"]))

    def test_forged_offset_cannot_pass(self):
        source="Alice must pay Bob."
        before=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"))]
        after=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"))]
        after[0]["bindings"][0]["span"]["start"]+=1
        with self.assertRaisesRegex(ValueError,"Role anchor"):
            run(source,source,before,after)

    def test_stale_annotation_inventory_rejected(self):
        source="Alice must pay Bob."
        before=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"))]
        with self.assertRaisesRegex(ValueError,"version mismatch"):
            audit_typed_role_graph(
                source=source,candidate=source,
                source_facts=before,candidate_facts=before,
                source_sha256=sha256(source.encode()).hexdigest(),
                candidate_sha256=sha256(source.encode()).hexdigest(),
                source_inventory_sha256="0"*64,
                candidate_inventory_sha256=digest(before))

    def test_duplicate_role_and_fact_rejected(self):
        source="Alice must pay Bob."
        before=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"))]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            run(source,source,before*2,before)
        dup=[fact(source,"payment","PAY",OBLIGOR=("alice","Alice"))]
        dup[0]["bindings"].append(dup[0]["bindings"][0])
        with self.assertRaisesRegex(ValueError,"Duplicate role"):
            run(source,source,dup,dup)


if __name__=="__main__":
    unittest.main()
