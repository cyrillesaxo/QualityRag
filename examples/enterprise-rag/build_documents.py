"""Generate actual synthetic PDF, DOCX and HTML fixtures. No customer documents."""
from pathlib import Path
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
ROOT=Path(__file__).resolve().parent
OUT=ROOT/"generated"
OUT.mkdir(exist_ok=True)
html="""<!doctype html><html lang="en"><meta charset="utf-8"><title>Incident INC-7421</title><body><h1>Gateway incident report</h1><p>Automated recovery reduced downtime during a prior gateway outage. This incident report does not authorize any future restoration.</p></body></html>"""
(OUT/"incident.html").write_text(html,encoding="utf-8")
doc=Document()
doc.add_heading("Gateway Recovery Runbook (2024, superseded)",0)
doc.add_paragraph("Restart the gateway once upstream connectivity stabilizes. This document predates current regional controls.")
doc.save(OUT/"old-runbook.docx")
c=canvas.Canvas(str(OUT/"operations.pdf"),pagesize=letter)
c.setTitle("Payments Operations Handbook (synthetic)")
for i in range(1,81):
    c.setFont("Helvetica-Bold",12);c.drawString(40,750,f"Payments Operations Handbook - Page {i}")
    c.setFont("Helvetica",10)
    if i==74:c.drawString(40,705,"7.3 On-call staff may initiate automated recovery after dependency timeout.")
    else:c.drawString(40,705,"This page contains general operational guidance and audit context.")
    c.showPage()
c.save()
c=canvas.Canvas(str(OUT/"eu-controls.pdf"),pagesize=letter)
c.setTitle("EU Financial Controls Annex (synthetic)")
for i in range(1,189):
    c.setFont("Helvetica-Bold",12);c.drawString(40,750,f"EU Financial Controls Annex - Page {i}")
    c.setFont("Helvetica",10)
    if i==187:
        c.drawString(40,705,"Appendix D - Sanctions screening dependency:")
        c.drawString(40,685,"Restoration requires compliance sign-off unless an approved")
        c.drawString(40,670,"emergency exception applies.")
    else:c.drawString(40,705,"Regional financial control context and general definitions.")
    c.showPage()
c.save()
print("Generated:",*[p.name for p in sorted(OUT.iterdir())])
