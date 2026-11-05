import copy
import json
from pathlib import Path
import tempfile
import unittest
from pypdf import PdfReader
from tools.activation_runtime.research.build_report import build

ROOT=Path(__file__).resolve().parents[1]


class ResearchPackageTests(unittest.TestCase):
    def test_prior_art_register_has_comparators_dates_and_negative_boundaries(self):
        text=(ROOT/"research/prior-art.md").read_text()
        self.assertRegex(text,r"Retrieved \d{4}-\d{2}-\d{2}")
        rows=[line.split("|")[1:-1] for line in text.splitlines() if line.startswith("| ")][1:]
        self.assertGreaterEqual(len(rows),6)
        for row in rows:
            with self.subTest(area=row[0]):
                self.assertEqual(len(row),3)
                self.assertIn("https://",row[1])
                self.assertGreater(len(row[2].strip()),50)
        self.assertIn("No claim of being first",text)
        self.assertIn("That question remains open",text)
        self.assertIn("larger payloads than AV1",text)
        self.assertIn("never amortize",text)

    def test_figures_and_pdf_regenerate_from_exact_receipt(self):
        receipt=ROOT/"research/receipts/engineering-v1.json"
        with tempfile.TemporaryDirectory() as root:
            a=Path(root)/"a";b=Path(root)/"b"
            build(receipt,a);build(receipt,b)
            for name in ("report.md","codec-bytes.svg","codec-bytes.png","report.pdf"):
                self.assertEqual((a/name).read_bytes(),(b/name).read_bytes(),name)
            paper=(a/"report.md").read_text()
            pdf=" ".join(" ".join(page.extract_text() for page in PdfReader(a/"report.pdf").pages).split())
            protocol=json.loads((ROOT/"research/protocol.json").read_text())
            for text in (paper,pdf):
                self.assertIn(protocol["id"],text)
                self.assertIn("rct.typed-operator-grammar/v1.4",text)
                self.assertIn("Claim-to-evidence matrix",text)
                self.assertIn("Original source custody evidence is required.",text)
                self.assertIn("NOT ESTABLISHED",text)
            abstract=paper.split("### Abstract",1)[1].split("###",1)[0]
            self.assertIn("do not establish",abstract)
            self.assertIn("negative result is retained",paper)

    def test_changed_receipts_change_figure_and_do_not_keep_false_claims(self):
        data=json.loads((ROOT/"research/receipts/engineering-v1.json").read_text())
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);original=root/"original.json";original.write_text(json.dumps(data))
            build(original,root/"a")
            changed=copy.deepcopy(data)
            for row in changed["ablation"]["measurements"]:
                if row["arm"]=="paired":
                    row.update(payload_bytes=1,model_bytes=0,exact_frame_match=False)
            source=root/"changed.json";source.write_text(json.dumps(changed));build(source,root/"b")
            self.assertNotEqual((root/"a/codec-bytes.svg").read_bytes(),(root/"b/codec-bytes.svg").read_bytes())
            paper=(root/"b/report.md").read_text()
            self.assertIn("paired | 1 |",paper)
            self.assertIn("fewer measured bytes",paper)
            self.assertIn("preservation is incomplete or failed",paper)
            self.assertNotIn("All evaluated reference-arm normalized frames match",paper)
            self.assertIn("not independently validated compression improvement",paper)
