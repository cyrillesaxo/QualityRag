"""Generate the main README's animated, accurate QualityRag walkthrough.

The fictional example explains the v0.1 deterministic PackSpec/evidence
admission contract. The separate Semantic Garden research stage is experimental.
Requires Pillow, DejaVu Sans; all content is drawn locally and reproducibly.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 960, 540
BG, PANEL, BORDER = "#07121E", "#102234", "#294359"
WHITE, MUTED = "#F1F6FC", "#9BB1C3"
TEAL, GREEN, AMBER, BLUE = "#3CD4BE", "#5DE0A5", "#FFBE55", "#85BFFF"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
if not FONT_DIR.exists():
    FONT_DIR = Path("/usr/share/fonts/truetype/liberation2")
BOLD = FONT_DIR / ("DejaVuSans-Bold.ttf" if "dejavu" in str(FONT_DIR)
                   else "LiberationSans-Bold.ttf")
REGULAR = FONT_DIR / ("DejaVuSans.ttf" if "dejavu" in str(FONT_DIR)
                      else "LiberationSans-Regular.ttf")


def f(size, bold=False):
    return ImageFont.truetype(str(BOLD if bold else REGULAR), size)


FONT = {size: f(size, size in (34, 25, 21)) for size in (34, 25, 21, 17, 15, 13)}


def text(d, at, message, size=17, color=WHITE, anchor=None):
    d.text(at, message, fill=color, font=FONT[size], anchor=anchor)


def rounded(d, area, fill=PANEL, outline=BORDER):
    d.rounded_rectangle(area, radius=16, fill=fill, outline=outline, width=2)


def badge(d, area, label, accent=TEAL):
    d.rounded_rectangle(area, radius=11, fill="#172A39",
                        outline=accent, width=1)
    x, y, x2, y2 = area
    text(d, ((x+x2)//2, (y+y2)//2), label, 13, accent, anchor="mm")


def card(d, area, heading, first="", second="", accent=BLUE):
    rounded(d, area)
    x, y, _, _ = area
    d.rectangle((x+16, y+17, x+20, y+42), fill=accent)
    text(d, (x+31, y+18), heading, 21)
    if first:
        text(d, (x+19, y+58), first, 17, MUTED)
    if second:
        text(d, (x+19, y+89), second, 17, MUTED)


def arrow(d, start, end):
    d.line((start, end), fill=BLUE, width=3)
    x,y=end
    d.polygon([(x-7,y-5),(x,y),(x-7,y+5)],fill=BLUE)


def frame(index):
    image=Image.new("RGB", (WIDTH, HEIGHT), BG)
    d=ImageDraw.Draw(image)
    text(d,(33,25),"QUALITY",25)
    text(d,(163,25),"RAG",25,TEAL)
    text(d,(34,62),"Evidence completeness before generated answers",15,MUTED)
    badge(d,(777,25,928,57),f"FRAME {index+1} / 9",BLUE)
    d.line([(34,89),(926,89)],fill=BORDER,width=2)

    headings=[
        ("1. A question enters the RAG application",
         "Fictional example: a company policy question"),
        ("2. Retrieve the available documents",
         "Retrieval supplies candidates, not automatic proof"),
        ("3. Apply a versioned PackSpec",
         "The application defines the evidence admission contract"),
        ("4. Run the deterministic evidence gate",
         "Two documents are not always two independent witnesses"),
        ("5. Incomplete evidence -> INCONCLUSIVE",
         "The application abstains or retrieves more evidence"),
        ("6. Retrieve an additional independent source",
         "The missing obligation can be repaired and rechecked"),
        ("7. PackSpec satisfied -> ADMIT",
         "ADMIT means the supplied metadata passes declared checks"),
        ("8. Only then produce a source-linked answer",
         "The answer generator operates after the evidence gate"),
        ("9. Research improves the mechanisms",
         "Semantic Garden is a separate, experimental learning loop"),
    ]
    heading, subtitle = headings[index]
    text(d,(35,112),heading,25)
    text(d,(35,151),subtitle,15,MUTED)

    if index==0:
        card(d,(72,204,888,396),
             "Does procedure X require supervisor approval?",
             "A language model could answer from retrieved text.",
             "QualityRAG first asks: is the evidence complete?",TEAL)
    elif index==1:
        card(d,(45,211,453,403),"Document A",
             "States: supervisor approval required",
             "Origin: company handbook")
        card(d,(508,211,916,403),"Document B",
             "Repeats the same policy statement",
             "Origin: a copy of that handbook")
        arrow(d,(450,309),(506,309))
    elif index==2:
        card(d,(60,202,901,427),"PackSpec v1  |  procedure-X",
             "Requirement: 2 INDEPENDENT source origins",
             "Requirement: current, in-scope evidence",TEAL)
        badge(d,(340,384,610,414),"Rules checked deterministically")
    elif index==3:
        card(d,(48,196,444,405),"Document A",
             "Original handbook","Origin key: HANDBOOK")
        card(d,(515,196,912,405),"Document B",
             "Copied handbook","Origin key: HANDBOOK")
        badge(d,(344,424,614,458),"Independent origins = 1 / 2",AMBER)
    elif index==4:
        rounded(d,(70,205,892,418),"#2D211E",AMBER)
        text(d,(103,236),"INCONCLUSIVE",34,AMBER)
        text(d,(103,297),
             "Missing a second independent supporting origin",21)
        text(d,(103,348),
             "Do not generate an unsupported definitive answer.",17,MUTED)
    elif index==5:
        card(d,(43,197,448,406),"Document A",
             "Current company handbook","Origin: HANDBOOK")
        card(d,(511,197,916,406),"Document C",
             "Current approval workflow","Origin: PROCESS-OWNER",GREEN)
        badge(d,(344,424,614,458),"Independent origins = 2 / 2",GREEN)
    elif index==6:
        rounded(d,(65,203,895,422),"#12332F",GREEN)
        text(d,(105,229),"ADMIT",34,GREEN)
        text(d,(105,294),"2 origins  |  Current  |  In scope",21)
        text(d,(105,353),
             "This does NOT prove the underlying documents are truthful.",
             17,MUTED)
    elif index==7:
        rounded(d,(64,201,895,427),PANEL,TEAL)
        text(d,(88,225),"Answer permitted by PackSpec",25,GREEN)
        text(d,(88,289),
             '"Procedure X requires supervisor approval."',21)
        text(d,(88,345),
             "Evidence: Handbook + Process-owner workflow",17,MUTED)
        badge(d,(667,383,861,413),"CITE SOURCES")
    else:
        card(d,(44,194,436,409),"Investigate failures",
             "Propose grammar + activation",
             "Run controlled comparisons",TEAL)
        card(d,(507,194,915,409),"Govern promotion",
             "Preserve failed experiments",
             "No automatic policy admission",AMBER)
        arrow(d,(435,306),(505,306))

    stages=["QUESTION","RETRIEVE","PACKSPEC","CHECK","ABSTAIN",
            "REPAIR","ADMIT","ANSWER","GARDEN"]
    for number, label in enumerate(stages):
        x,y=56+number*105,498
        d.ellipse((x-6,y-6,x+6,y+6),
                  fill=TEAL if number==index else "#2C4860")
        if number<8:
            d.line((x+10,y,x+95,y),fill="#264051",width=2)
        text(d,(x,515),label,13,TEAL if number==index else MUTED,
             anchor="mt")
    return image


def generate(output):
    frames=[frame(i) for i in range(9)]
    optimized=[image.quantize(colors=96,method=Image.Quantize.MEDIANCUT)
               for image in frames]
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    optimized[0].save(
        output,save_all=True,append_images=optimized[1:],
        duration=[1150,1450,1400,1650,1900,1550,1750,1800,1950],
        loop=0,optimize=True,disposal=2)
    inspection=Image.open(output)
    if inspection.n_frames!=9 or inspection.size!=(WIDTH,HEIGHT):
        raise AssertionError("Invalid README GIF shape or frame count")
    if output.stat().st_size>2_000_000:
        raise AssertionError("README GIF exceeds 2 MB budget")
    print(f"Created {output}: {inspection.n_frames} frames; "
          f"{output.stat().st_size} bytes")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",
                        default="docs/assets/qualityrag-how-it-works.gif")
    options=parser.parse_args()
    generate(options.output)
