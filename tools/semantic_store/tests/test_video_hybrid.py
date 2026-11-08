"""Hybrid video retrieval is evaluated with injected vectors, no model downloads."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_evidence import compile_video_evidence
from video_catalog import write_evidence, CatalogError
from video_hybrid import build_hybrid_index, search_hybrid

EMBEDDINGS={
    "Wheelchair brake lever is beside the wheel":[1.,0.,0.],
    "Nurse prepares a transfer":[0.,1.,0.],
    "wheelchair safety lock":[1.,0.,0.],
    "patient transfer":[0.,1.,0.],
}
def embedding(texts):
    return [EMBEDDINGS[x] for x in texts]

def media(id):
    return compile_video_evidence(source_id=id,revision="r1",
        media_sha256=hashlib.sha256(id.encode()).hexdigest(),
        duration_ms=10000,witnesses=[
          {"id":"v1","modality":"video","interval":{"start_ms":2000,"end_ms":2001},
           "provider":"model","text":"Wheelchair brake lever is beside the wheel"},
          {"id":"a1","modality":"audio","interval":{"start_ms":3000,"end_ms":4000},
           "provider":"asr","text":"Nurse prepares a transfer"}
        ],events=[])


class HybridTests(unittest.TestCase):
    def test_dense_search_recovers_concept_without_shared_keywords(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,media("lesson-01"))
            info=build_hybrid_index(root,model_id="fixture-v1",embedder=embedding)
            self.assertEqual(info["witness_count"],2)
            result=search_hybrid(root,"wheelchair safety lock",
                embedder=embedding,model_id="fixture-v1",lexical_weight=0)
            self.assertEqual(result["results"][0]["witness_id"],"v1")
            self.assertEqual(result["results"][0]["modality"],"video")
            self.assertEqual(result["results"][0]["source_reference"]["citation_status"],
                             "NO_APPROVED_PUBLIC_REFERENCE")
            self.assertEqual(result["governance"].split(";")[0],"INCONCLUSIVE")

    def test_stale_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,media("lesson-01"))
            build_hybrid_index(root,model_id="fixture-v1",embedder=embedding)
            write_evidence(root,media("lesson-02"))
            with self.assertRaisesRegex(CatalogError,"membership changed"):
                search_hybrid(root,"patient transfer",embedder=embedding,
                    model_id="fixture-v1")

    def test_wrong_model_and_invalid_weights_fail(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,media("lesson-01"))
            build_hybrid_index(root,model_id="fixture-v1",embedder=embedding)
            with self.assertRaisesRegex(CatalogError,"Wrong embedding"):
                search_hybrid(root,"patient transfer",embedder=embedding,model_id="other")
            with self.assertRaises(CatalogError):
                search_hybrid(root,"patient transfer",embedder=embedding,
                              model_id="fixture-v1",lexical_weight=float("nan"))

    def test_original_source_fingerprint_cannot_change_silently(self):
        with tempfile.TemporaryDirectory() as root:
            write_evidence(root,media("lesson-01"))
            build_hybrid_index(root,model_id="fixture-v1",embedder=embedding)
            f=Path(root)/".video-evidence"/"lesson-01.json"
            f.write_text(f.read_text().replace("beside the wheel","behind the wheel"))
            with self.assertRaises(CatalogError):
                search_hybrid(root,"patient transfer",embedder=embedding,
                    model_id="fixture-v1")


if __name__ == "__main__":
    unittest.main()
