"""Document adapters -> source-anchored immutable index -> FIND integration."""
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from document_codex import compile_document
from semantic_codex import CodexError
from directory_codex import index_directory,search_store
from store import SemanticStore

def word_bytes(text):
    doc=(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>'
    )
    out=io.BytesIO()
    with ZipFile(out,"w",ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml",doc)
    return out.getvalue()

def pdf_bytes():
    from reportlab.pdfgen import canvas
    out=io.BytesIO()
    paper=canvas.Canvas(out)
    paper.drawString(80,700,"Cyrille attended the meeting")
    paper.showPage()
    paper.save()
    return out.getvalue()

class DocumentCodexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/"meeting.docx").write_bytes(word_bytes("Cyrille authored the plan"))
        (self.root/"report.pdf").write_bytes(pdf_bytes())
        (self.root/"notes.html").write_text(
            "<html><body><h1>Cyrille at work</h1>"
            "<script>secret code</script><p>Meeting notes</p></body></html>",encoding="utf8")
        (self.root/"details.txt").write_text("First line\nCyrille handles this\n",encoding="utf8")
        self.db=sqlite3.connect(":memory:")
        self.store=SemanticStore(self.db)
        self.store.initialize()
        self.policy=lambda principal,sid,rev:principal=="local" and sid.startswith("docs/")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_document_formats_index_and_find_cyrille(self):
        report=index_directory(self.store,self.root,namespace="docs",
                               principal="local",authorize_source=self.policy)
        self.assertEqual(report["coverage"]["indexed"],4)
        results=search_store(self.store,"Cyrille",namespace="docs",
                             principal="local",authorize_source=self.policy)
        self.assertEqual({h["format"] for h in results["hits"]},{"docx","pdf","html","txt"})
        anchors={h["format"]:h["anchor"]["kind"] for h in results["hits"]}
        self.assertEqual(anchors,{"docx":"docx_paragraph","pdf":"pdf_page",
                                  "html":"html_line","txt":"text_line"})
        pdf=next(h for h in results["hits"] if h["format"]=="pdf")
        self.assertEqual(pdf["anchor"]["page_number"],1)
        self.assertEqual(results["admission"],"INCONCLUSIVE")
        self.assertEqual(results["visual_identity_recognition"],"NOT_PERFORMED")

    def test_html_ignores_scripts(self):
        artifact=compile_document(b"<p>Hello Cyrille</p><script>secret-token</script>",
                                  source_id="docs/a.html",revision="v1",format="html")
        self.assertNotIn("secret-token",str(artifact["records"]))
        self.assertEqual(artifact["extraction_coverage"],"PARTIAL_TEXT_ONLY")

    def test_docx_invalid_zip_refused(self):
        with self.assertRaises(CodexError):
            compile_document(b"not a word doc",source_id="a",revision="b",format="docx")

    def test_docx_entities_refused(self):
        payload=word_bytes("Cyrille")
        with ZipFile(io.BytesIO(payload)) as z:
            xml=z.read("word/document.xml")
        xml=xml.replace(b"<w:document",b"<!DOCTYPE foo [<!ENTITY x 'y'>]><w:document")
        out=io.BytesIO()
        with ZipFile(out,"w") as archive:
            archive.writestr("word/document.xml",xml)
        with self.assertRaises(CodexError):
            compile_document(out.getvalue(),source_id="a",revision="b",format="docx")

    def test_no_ocr_coverage_claim(self):
        artifact=compile_document(pdf_bytes(),source_id="a",revision="b",format="pdf")
        self.assertIn("No OCR",artifact["extraction_limitations"][0])
        self.assertFalse(artifact["reconstruction"]["exact_source_bytes_recoverable_from_ir"])

    def test_second_index_is_idempotent(self):
        index_directory(self.store,self.root,namespace="docs",principal="local",
                        authorize_source=self.policy)
        report=index_directory(self.store,self.root,namespace="docs",principal="local",
                               authorize_source=self.policy)
        self.assertEqual(report["coverage"]["unchanged"],4)

    def test_utf8_invalid_text_refused(self):
        with self.assertRaises(CodexError):
            compile_document(b"\xff",source_id="a",revision="b",format="txt")

if __name__=="__main__":
    unittest.main()
