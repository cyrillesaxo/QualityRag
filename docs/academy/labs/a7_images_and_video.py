"""A7 · It can't understand diagrams, images and video. (research preview)"""
import sqlite3, tempfile
from pathlib import Path
import _research  # noqa: F401
from PIL import Image, ImageDraw
from directory_codex import index_directory, find_visual_similar
from store import SemanticStore


def diagram(path, reverse=False, boxes=2):
    im = Image.new("RGB", (320, 200), "white"); d = ImageDraw.Draw(im)
    xs = [20, 210] if boxes == 2 else [10, 120, 230]
    for x in xs:
        d.rectangle((x, 70, x + 80, 130), outline="black", width=4)
    d.line((100, 100, 210, 100), fill="black", width=4)
    tip = [(100, 100), (114, 92), (114, 108)] if reverse else [(210, 100), (196, 92), (196, 108)]
    d.polygon(tip, fill="black")  # the arrowhead says who calls whom
    im.save(path)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    diagram(root / "architecture.png")                  # service A calls service B
    diagram(root / "architecture-reversed.png", reverse=True)  # B calls A: the opposite meaning
    diagram(root / "three-tier.png", boxes=3)            # a different diagram
    Image.radial_gradient("L").resize((320, 200)).convert("RGB").save(root / "team-photo.png")
    db = sqlite3.connect(":memory:"); store = SemanticStore(db); store.initialize()
    allow = lambda principal, source, revision: principal == "learner"
    report = index_directory(store, root, namespace="lab", principal="learner", authorize_source=allow)
    print("== Indexed", report["coverage"]["indexed"], "images (64-bit difference hash per image)")
    res = find_visual_similar(store, reference_source_id="lab/architecture.png", namespace="lab",
                              principal="learner", authorize_source=allow, max_distance=64)
    print("== Visually similar to lab/architecture.png")
    for r in res["results"]:
        print(f"  {r['source_id']:<30} distance={r['distance']:<3} identity={r['identity_status']}")
    print(f"  method: {res['method']}   scope: {res['scope']}")
    print(f"  admission: {res['admission']}   can_generate: {res['can_generate']}")
