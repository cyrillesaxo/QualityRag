"""Generate publication artifacts solely from committed observed engineering receipts."""
import argparse
from collections import defaultdict
import html
import json
from pathlib import Path
from statistics import mean


def build(receipt,output):
    data=json.loads(Path(receipt).read_text())
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(list)
    for row in data["ablation"]["measurements"]:
        groups[row["arm"]].append(row.get("payload_bytes",row.get("encoded_bytes"))+row.get("model_bytes",0))
    means={arm:mean(values) for arm,values in groups.items()}
    negative=means["paired"]>=means["av1"]
    comparison=("The paired palette arm is no smaller than the lossless AV1 baseline. This negative result is retained."
                if negative else "The paired palette arm has fewer measured bytes in these authored clips. This is not independently validated compression improvement.")
    reference_rows=[r for r in data["ablation"]["measurements"] if r["arm"] in {"fixed","decoder-only","paired"}]
    frame_claim=("All evaluated reference-arm normalized frames match the source in these clips."
                 if reference_rows and all(r.get("exact_frame_match") is True for r in reference_rows)
                 else "Exact frame preservation is incomplete or failed; these results do not qualify as quality equivalence.")
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["svg.hashsalt"]="qualityrag-activation-research-v1"
    import matplotlib.pyplot as plt
    fig,axis=plt.subplots(figsize=(7,3.5))
    names=["av1","fixed","decoder-only","paired"]
    bars=axis.bar(names,[means[n] for n in names],color=["#155e46","#72867d","#72867d","#72867d"])
    axis.set_ylabel("Bytes per clip including one model copy")
    axis.set_title("Authored test clips: measured bytes, including model",fontsize=11,loc="left",pad=18)
    axis.spines[["top","right"]].set_visible(False)
    for bar in bars:axis.text(bar.get_x()+bar.get_width()/2,bar.get_height()+100,str(round(bar.get_height())),ha="center",fontsize=9)
    axis.set_ylim(0,max(means.values())*1.2)
    fig.tight_layout()
    fig.savefig(root/"codec-bytes.svg",metadata={"Date":None})
    fig.savefig(root/"codec-bytes.png",dpi=180)
    plt.close(fig)
    rows="\n".join("| "+arm+" | "+str(round(means[arm]))+" |" for arm in names)
    text="""# QualityRag Activation Research
## Executable reference system and open validation
Cyrille Eloundou - APX / QualityRag - 2026-11-04 - https://apx.guide/

### Abstract
We implement a constraint-directed research reference connecting reviewed
ConstraintIR, bounded typed RCT search, signed artifact compatibility, exact
source custody, local reconstruction, research-memory operations and isolated
deterministic proposal agents. A playable lossless palette scene-state codec
provides a concrete video baseline with explicit timeline and exact residuals.
It is a predictive reference, not a learned semantic codec or FF-RCT parity
implementation. The authored synthetic experiments do not establish a semantic
compression advantage or independently validated clinical/legal preservation.

### Existing grammar and governance
The existing finite relation grammar is:
Relation<A,B> = EDGE<P:A->B> | PATH(Relation<A,M>, Relation<M,B>)
              | AND(Relation<A,B>, Relation<A,B>).
Typed composition, bounded candidate counts and work limits are reused from the
existing Semantic Store. A minimum fitting authored labels remains a candidate,
not universal semantic truth. The activation DSL executes PRESERVE, TRANSITION,
ACTIVATE, VERIFY and FALLBACK with a deterministic trace and no eval.

The PackSpec source in the finite demonstration explicitly states:
"Original source custody evidence is required." The real compiler extracts that
authored clause into ConstraintIR. The demonstration maps it to
EVIDENCE_PRESENCE with min_independent_sources=1.
The existing repository policy examples/apx-packspecs/policies/ffi.json
(id=apx-training-ffi, version=1.0) declares
verbatim-source-custody, discriminating-probe and independent-corroboration,
each with min_independent_sources=1. These genuine evidence-presence clauses
are not executable video-fidelity guarantees. The review label is deliberately
identified as unauthenticated; missing independent evidence keeps admission
INCONCLUSIVE. Distinct policy-source and transformed-data hashes are retained.

### Versioned experimental proposals
The protocol template is `activation-research-v1` (research/protocol.json).
Its H1-H6 variables and null hypotheses are explicit; it is not a registered
experiment until a real corpus is bound and the holdout is independently opened.
The typed search proposal uses `rct.typed-operator-grammar/v1.4`; finite agent
proposals use `qualityrag.agent-proposal/v1` and explicit patch lists. The video
reference uses `qualityrag.scene-palette/v1` and `qualityrag.scene-video/v1`.
These versioned proposals do not assert canonical FF-RCT parity or novelty.

### Methods
The source-to-output path stores exact original bytes, checks a signed release
against runtime, source, policy and transitive modules, reconstructs actual
values and checks all declared distinctions. Source adapters retain PDF page or
CSV row/line anchors; unsupported image/annotation content remains unknown.
Every omission requires a matching policy disposition; unspecified fields are
retained rather than silently discarded.

The shared video grammar is a finite RGB backdrop palette. Each frame records
its palette code, source frame identity and exact XOR/zlib residual or a raw
fallback. Full decoding writes a playable FFV1 file and verifies normalized RGB
frames, presentation timestamps and PCM32 audio samples. The streaming index
pins each frame segment and model; range seeking does not fetch the full title.

Six deterministic research roles run in separate resource-limited processes
with default-deny seccomp. File opening, sockets and process creation are
denied by integration tests. These agents search a predefined typed space;
they are not autonomous mathematical inventors. Guardian/counterexample
disagreement blocks promotion. Original pinned APX WBC and RCoC are executed
through Node 24 rather than reimplemented in Python.

### Observed engineering results
Four authored finite cases reconstruct deterministically. Independent runs
produce identical structural receipts. The adversarial suite covers actor/
recipient reversal, negation, temporal order, units, quantities, captions and
incompatible models. These finite test outcomes do not authenticate domain truth.

The codec experiment uses two training and two held-out authored clips sharing
a synthetic test-pattern generator. This is an engineering fixture, not a
representative corpus or four independent natural-video families. The table
includes one complete model copy for each clip, a declared cold-install view.

| Arm | Mean measured bytes |
|---|---|
"""+rows+"""

"""+frame_claim+"\n"+comparison+"""
Decoder-only retains the fixed encoder/model and selects between scalar and strided-XOR
decoders on training data only. No held-out data is sent to the proposing agents. Paired palette selection
uses training clips only; the receipt counts its actual search time.
No confidence interval or generalization claim is computed from these correlated
authored fixtures. Energy, full lifecycle USD and physical-device effects remain
unknown, so no economic advantage is established.

### Falsifiable research protocol
The preregistration template defines H1 bytes, H2 full lifecycle cost, H3 local
activation time, H4 preserved distinctions, H5 research continuity and H6 agent
evolution. An immutable registry must bind a real corpus and sample plan before
an independent evaluator can open its holdout. Family-disjoint splitting, paired
bootstrap methods, blinded field scoring and rejection conditions are explicit.
The template is not represented as a registered final experiment.

### Claim-to-evidence matrix
| Claim | Reproducible source or receipt | Scope |
|---|---|---|
| Exact finite transformations | tests/test_preservation.py; tests/test_runtime.py | Authored finite scalar records |
| Actual playable lossless reference | tests/test_scene_codec.py | Bounded CFR RGB/PCM32 profile |
| Signed streaming and fallback | tests/test_streaming.py | Pinned local segment store |
| Isolated role proposals | tests/test_agents.py | Linux seccomp deterministic backend |
| Original native APX behavior | tests/test_native_apx.py | Pinned WBC/RCoC source only |
| SDK parity and access isolation | tests/test_service_sdk.py | Same canonical authenticated API |
| Review workflow | tests/test_browser.py | Actual Chromium, opt-in |
| Negative codec comparison | research/receipts/engineering-v1.json | Authored synthetic engineering run |
| Independent semantic or compression advantage | No evidence supplied | NOT ESTABLISHED |

### Limitations and release decision
A representative authorized 100-clip corpus, licensed neural-model weights,
independent domain reviewers, two physical mobile/TV device classes, thermal/
power instrumentation and canonical FF-RCT reconstruction parity are not supplied
by this experiment. The neural adapter refuses absent or unpinned weights; it
never downloads models or substitutes a pretend result. Lossy neural output
cannot qualify for an exact preservation profile.

The release gate is BLOCK with the current evidence. No software test, source
hash, agent consensus or ephemeral demonstration signature is treated as
independent scientific acceptance. Negative/no-crossover results remain publishable
research outcomes; production promotion is not automatic.

### Reproduction
From the repository root:
python -m tools.activation_runtime.run_research --out /tmp/research-run
python -m tools.activation_runtime.research.build_report --receipt /tmp/research-run/receipt.json --out /tmp/research-paper

For all tests, install the repository requirements, use Node 24, FFmpeg/ffprobe,
and configure QUALITYRAG_APX_ROOT for the pinned native APX source. Browser checks
require QUALITYRAG_BROWSER_TESTS=1 plus Playwright Chromium. Test/receipt links
must be attached to the actual commit and reviewed before claiming completion.

### Primary references
1. Alliance for Open Media, AV1 specification: https://aomediacodec.github.io/av1-spec/
2. InterDigital, CompressAI model zoo: https://interdigitalinc.github.io/CompressAI/zoo.html
3. Darwiche and Marquis, A Knowledge Compilation Map, JAIR 17 (2002), https://arxiv.org/abs/1106.1819
4. Doyle, A Truth Maintenance System, MIT AI Memo 521 (1979), https://dspace.mit.edu/entities/publication/5377b306-4ecc-4687-b1f5-78cbb4a0543a
5. Microsoft, GraphRAG indexing/query documentation: https://microsoft.github.io/graphrag/
6. Generation Is Compression: Zero-Shot Video Coding via Stochastic Rectified Flow (2026), https://arxiv.org/abs/2603.26571
All references were retrieved 2026-11-04. Prior-art and failure boundaries are
recorded in research/prior-art.md.
"""
    (root/"report.md").write_text(text)
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont("DocSans","/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DocBold","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    styles=getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName="DocBold" if "Heading" in style.name or style.name=="Title" else "DocSans"
    styles["Heading2"].keepWithNext=True
    styles.add(ParagraphStyle(name="ResearchBody",fontName="DocSans",fontSize=9.5,leading=14,spaceAfter=8))
    styles.add(ParagraphStyle(name="ResearchTable",fontName="DocSans",fontSize=8,leading=11))
    flow=[];table=[]
    def flush():
        nonlocal table
        if not table:return
        widths=[1.65*inch,3.0*inch,1.65*inch] if len(table[0])==3 else [3.2*inch,3.1*inch]
        tab=Table([[Paragraph(html.escape(cell),styles["ResearchTable"]) for cell in row] for row in table],colWidths=widths,repeatRows=1,hAlign="LEFT")
        tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e7efe9")),
                                ("VALIGN",(0,0),(-1,-1),"TOP"),("BOTTOMPADDING",(0,0),(-1,-1),8),
                                ("TOPPADDING",(0,0),(-1,-1),8),("LINEBELOW",(0,0),(-1,0),.5,colors.HexColor("#71877c"))]))
        flow.extend([tab,Spacer(1,12)]);table=[]
    paragraph=[]
    def flush_paragraph():
        if paragraph:
            flow.append(Paragraph(html.escape(" ".join(paragraph)),styles["ResearchBody"]));paragraph.clear()
    for line in text.splitlines():
        if line.startswith("|"):
            flush_paragraph()
            cells=[x.strip() for x in line.strip("|").split("|")]
            if not all(set(cell)<=set("-: ") for cell in cells):table.append(cells)
        elif line.startswith("#"):
            flush();flush_paragraph()
            level=len(line)-len(line.lstrip("#"))
            flow.append(Paragraph(html.escape(line.lstrip("# ")),styles["Title" if level==1 else "Heading2"]))
            if line.startswith("### Observed"):flow.append(Image(str(root/"codec-bytes.png"),width=6.3*inch,height=3.15*inch))
        elif not line.strip():flush();flush_paragraph()
        else:flush();paragraph.append(line)
    flush();flush_paragraph()
    def footer(canvas,doc):
        canvas.setFont("DocSans",8);canvas.setFillColor(colors.HexColor("#536360"))
        canvas.drawString(42,28,"QualityRag research reference | Independent validation pending")
        canvas.drawRightString(570,28,str(doc.page))
    from reportlab.pdfgen.canvas import Canvas
    def stable_canvas(*args,**kwargs):
        kwargs["invariant"]=1
        return Canvas(*args,**kwargs)
    SimpleDocTemplate(str(root/"report.pdf"),pagesize=(612,792),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=45,
                      title="QualityRag Activation Research",author="Cyrille Eloundou - APX / QualityRag").build(flow,onFirstPage=footer,onLaterPages=footer,canvasmaker=stable_canvas)
    return root/"report.pdf"


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--receipt",required=True);parser.add_argument("--out",required=True)
    args=parser.parse_args();print(build(args.receipt,args.out))
