"""Extract real local PDF/DOCX/HTML fixture text and compare naive search vs governed evidence."""
from pathlib import Path
from html.parser import HTMLParser
import re
from pypdf import PdfReader
from docx import Document
from qualityrag import evaluate

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"generated"
class ExtractText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)
def parse(path):
    if path.suffix==".pdf":
        return [(f"{path.name}#page={i+1}",page.extract_text() or "") for i,page in enumerate(PdfReader(str(path)).pages)]
    if path.suffix==".docx":
        d=Document(path)
        return [(path.name," ".join(p.text for p in d.paragraphs))]
    h=ExtractText();h.feed(path.read_text(encoding="utf-8"))
    return [(path.name," ".join(h.parts))]
def tokens(t):return set(re.findall(r"[a-z0-9]+",t.lower()))
def search(chunks,query,k=3):
    q=tokens(query)
    scored=[(len(q&tokens(text)),identifier,text) for identifier,text in chunks]
    return [(identifier,text,score) for score,identifier,text in sorted(scored,key=lambda x:(-x[0],x[1])) if score>0][:k]
def main():
    expected=["operations.pdf","eu-controls.pdf","old-runbook.docx","incident.html"]
    for name in expected:
        if not (OUT/name).is_file():raise SystemExit("Generate fixtures first: python build_documents.py")
    chunks=[c for name in expected for c in parse(OUT/name)]
    assert any("requires compliance sign-off" in t for _,t in chunks)
    generic=search(chunks,"automated recovery dependency timeout on call",3)
    print("GENERIC SEARCH:",[(cid,score) for cid,_,score in generic])
    pack={"id":"eu-payments-screening-recovery","version":"1","requirements":[
        {"id":"recovery-procedure"},{"id":"eu-screening-control"}]}
    evidence=[]
    for identifier,text,score in generic:
        if "automated recovery after dependency timeout" in text.lower():
            evidence.append({"id":identifier,"origin":"ops-handbook","source_ref":identifier,
            "requirement_id":"recovery-procedure","status":"SUPPORTS","observed_at":"2026-11-02T10:00:00Z"})
    decision=evaluate(pack,evidence,as_of="2026-11-02T10:05:00Z")
    print("GOVERNED VERDICT:",decision["verdict"])
    assert decision["verdict"]=="INCONCLUSIVE"
    targeted=search(chunks,"sanctions screening restoration requires compliance sign off",3)
    print("TARGETED SEARCH:",[(cid,score) for cid,_,score in targeted])
    assert any("eu-controls.pdf#page=187"==cid for cid,_,_ in targeted)
    return decision
if __name__=="__main__":main()
