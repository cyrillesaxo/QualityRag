import unittest
from chat_to_tree import convert
class SkillTests(unittest.TestCase):
    def test_provenance_and_fail_closed(self):
        v=convert({"messages":[{"role":"user","content":"Explain transformer attention"},{"role":"assistant","content":"Attention is a mechanism."}]},"Transformer")
        self.assertEqual(v["source"]["message_count"],2)
        self.assertEqual(v["root_pack_spec"]["verification"],"INCONCLUSIVE")
        self.assertTrue(any(n["label"]=="Self-attention" and n["source_message_ids"]==[0,1] for n in v["nodes"]))
        self.assertEqual(v["shorts"],[])
    def test_deterministic(self):
        payload=[{"role":"user","content":"Kafka and attention"}]
        self.assertEqual(convert(payload),convert(payload))
    def test_max_nodes(self):
        self.assertLessEqual(len(convert("Kafka attention transformer neuron PackSpec",max_children=2)["nodes"]),3)
    def test_size_bound(self):
        with self.assertRaises(ValueError):convert("x"*100001)
if __name__=="__main__":unittest.main()
