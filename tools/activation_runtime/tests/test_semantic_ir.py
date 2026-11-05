"""Finite graph typing, exact source anchors and bijective transformations."""
from copy import deepcopy
import json
import unittest
from tools.activation_runtime.common import canonical,strict_json
from tools.activation_runtime.semantic_ir import build,check,rename,evaluate

RAW="Éva tells Bob: do NOT give 5 mg before checking.".encode()


def draft(name,kind="ENTITY",roles=None,order=None,**changes):
    result={"observation_id":name,"quote_start":0,"quote_end":len(RAW.decode()),"kind":kind,"value":name,
            "roles":roles or {},"polarity":"UNKNOWN","quantity":None,"unit":None,"temporal_order":order or [],"modality":"OBSERVED"}
    result.update(changes);return result


def drafts():
    return [draft("eva"),draft("bob"),draft("check","EVENT",{"actor":"eva"}),
            draft("give","EVENT",{"actor":"eva","recipient":"bob"},["check"],polarity="NEGATIVE",quantity=5,unit="mg",modality="PROHIBITED"),
            draft("knows","RELATION",{"subject":"eva","object":"bob"}),draft("unresolved","UNKNOWN",value=None)]


class SemanticIRTests(unittest.TestCase):
    def test_complete_typed_inventory_anchors_quantities_and_unknowns(self):
        ast=build(RAW,drafts());nodes={node["id"]:node for node in ast["nodes"]}
        self.assertEqual(nodes["give"]["quantity"],5);self.assertEqual(nodes["give"]["unit"],"mg")
        self.assertEqual(nodes["give"]["polarity"],"NEGATIVE")
        self.assertEqual(nodes["eva"]["source"]["byte_end"],len(RAW))
        self.assertEqual(ast["temporal_edges"],[{"before":"check","after":"give"}])
        self.assertTrue(any(row["observation_id"]=="unresolved" for row in ast["unknowns"]))
        self.assertEqual(ast["domain_validity"],"UNKNOWN");self.assertFalse(ast["can_generate"])
        self.assertEqual(ast["canonical_apx_parity"],"NOT_ESTABLISHED")

    def test_canonical_roundtrip_and_input_order_are_deterministic(self):
        ast=build(RAW,drafts())
        self.assertEqual(build(RAW,list(reversed(drafts()))),ast)
        self.assertEqual(check(RAW,strict_json(canonical(ast))),ast)

    def test_reversible_rename_updates_all_roles_orders_and_hashes(self):
        ast=build(RAW,drafts());mapping={node["id"]:"renamed-"+node["id"] for node in ast["nodes"]}
        transformed,trace=rename(RAW,ast,mapping)
        self.assertNotEqual(transformed["ast_sha256"],ast["ast_sha256"])
        self.assertEqual(transformed["source"],ast["source"])
        node=next(n for n in transformed["nodes"] if n["id"]=="renamed-give")
        self.assertEqual(node["roles"]["recipient"],"renamed-bob");self.assertEqual(node["temporal_order"],["renamed-check"])
        recovered,_=rename(RAW,transformed,{v:k for k,v in mapping.items()});self.assertEqual(recovered,ast)
        self.assertEqual(trace["scope"],"FINITE_DECLARED_GRAPH_ONLY")

    def test_missing_nonentity_and_unknown_role_endpoints_refuse(self):
        for target in ("absent","check","unresolved"):
            rows=drafts();rows[3]["roles"]["recipient"]=target
            with self.assertRaises(ValueError):build(RAW,rows)

    def test_entity_and_unknown_nodes_cannot_assert_relation_joins(self):
        for kind in ("ENTITY","UNKNOWN"):
            for changes in ({"roles":{"actor":"eva"}},{"temporal_order":["check"]}):
                rows=drafts();rows.append(draft("bad",kind,**changes))
                with self.assertRaises(ValueError):build(RAW,rows)

    def test_relation_requires_exact_binary_entity_endpoints(self):
        for roles in ({},{"subject":"eva"},{"actor":"eva","object":"bob"},{"subject":"eva","object":"bob","recipient":"bob"}):
            rows=drafts();rows[4]["roles"]=roles
            with self.assertRaises(ValueError):build(RAW,rows)

    def test_temporal_missing_wrong_kind_self_and_duplicate_refs_refuse(self):
        for order in (["absent"],["eva"],["give"],["check","check"]):
            rows=drafts();rows[3]["temporal_order"]=order
            with self.assertRaises(ValueError):build(RAW,rows)

    def test_event_cycles_and_inconsistent_antecedent_orders_refuse(self):
        rows=drafts();rows[2]["temporal_order"]=["give"]
        with self.assertRaises(ValueError):build(RAW,rows)
        rows=drafts()+[draft("third","EVENT",order=["give","check"])]
        with self.assertRaises(ValueError):build(RAW,rows)

    def test_duplicate_ids_incomplete_drafts_and_bounded_inputs_refuse(self):
        for rows in ([],drafts()+[draft("eva")],[draft(str(i)) for i in range(129)],[{"observation_id":"x"}]):
            with self.assertRaises(ValueError):build(RAW,rows)
        for raw in (b"",b"x"*65537,b"\xff"):
            with self.assertRaises(ValueError):build(raw,[draft("x")])

    def test_anchor_graph_fingerprint_and_unknown_inventory_tampering_refuse(self):
        ast=build(RAW,drafts())
        mutations=[lambda d:d["nodes"][0]["source"].update(byte_start=1),
                   lambda d:d["nodes"][0]["source"].update(quote_sha256="0"*64),
                   lambda d:d["nodes"][0]["source"].update(quote="invented"),lambda d:d.update(joins=[]),
                   lambda d:d.update(unknowns=[]),lambda d:d.update(ast_sha256="0"*64),lambda d:d.update(extra=True)]
        for mutate in mutations:
            changed=deepcopy(ast);mutate(changed)
            with self.assertRaises(ValueError):check(RAW,changed)
        with self.assertRaises(ValueError):check(RAW+b" changed",ast)

    def test_mapping_must_be_total_bijective_and_bounded(self):
        ast=build(RAW,drafts());mapping={node["id"]:node["id"] for node in ast["nodes"]}
        bad=[{}, {**mapping,"other":"other"},{**mapping,"eva":"bob"},{**mapping,"eva":"bad/id"}]
        for value in bad:
            with self.assertRaises(ValueError):rename(RAW,ast,value)

    def test_scalar_value_quantity_unit_and_span_limits_refuse(self):
        for changes in ({"value":{}},{"value":"x"*4097},{"value":float("nan")},{"quantity":True,"unit":"mg"},
                        {"quantity":1,"unit":None},{"quantity":1,"unit":"x"*65},{"quantity":None,"unit":"mg"},
                        {"quote_start":True},{"quote_end":9999}):
            with self.assertRaises(ValueError):build(RAW,[draft("x",**changes)])
        ast=build(RAW,[draft("x",quantity=10**400,unit="count")])
        self.assertEqual(ast["nodes"][0]["quantity"],10**400)

    def test_unknown_options_and_nonflat_observation_values_refuse(self):
        for request in ({},{"observations":drafts(),"authority":True},{"observations":drafts(),"rename":None}):
            with self.assertRaises(ValueError):evaluate(RAW,request)

    def test_unicode_quote_offsets_use_utf8_bytes_without_normalizing_source(self):
        ast=build(RAW,[draft("bob",quote_start=10,quote_end=13)])
        anchor=ast["nodes"][0]["source"]
        self.assertEqual(anchor["quote"],"Bob");self.assertEqual(anchor["byte_start"],11)
        self.assertEqual(anchor["byte_end"],14)
