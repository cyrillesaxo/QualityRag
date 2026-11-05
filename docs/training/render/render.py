"""Render a QualityRag training episode from its script.json.

    python docs/training/render/render.py docs/training/episode-01-getting-started --voice-dir DIR [--out DIR]
    python docs/training/render/render.py EPISODE --voice-dir DIR --stills title:3.0 gate:9.5

Narration is synthesized locally with Piper (LibriTTS high, CC BY 4.0 data). Animated scenes
are drawn frame by frame from scenes.html; console scenes film the real QualityRag console,
started with the documented bootstrap + serve commands. Every scene is encoded with the same
settings, joined with the concat demuxer, then captions are burned once.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FPS = 30
W, H = 1920, 1080
SR = 22050
X264 = ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), "-video_track_timescale", "15360"]


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


# ---------- narration ----------
def tts(text, voice, cache, model):
    key = hashlib.sha256(json.dumps([text, voice], sort_keys=True).encode()).hexdigest()[:20]
    out = cache / f"{key}.wav"
    if not out.exists():
        tmp = out.with_suffix(".part.wav")
        run([sys.executable, "-m", "piper", "-m", str(model), "-s", str(voice["speaker"]),
             "--length-scale", str(voice["length_scale"]), "-f", str(tmp)], input=text.encode(), capture_output=True)
        tmp.rename(out)
    with wave.open(str(out)) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def timeline(script, voice_dir, cache):
    """Per scene: sentence audio, marks (sentence starts), exact frame-aligned duration."""
    voice = script["voice"]
    model = Path(voice_dir) / "libritts-high" / "en-us-libritts-high.onnx"
    gap = voice["sentence_gap"]
    out = []
    for scene in script["scenes"]:
        lines = scene["say"] if scene["kind"] == "animation" else [s["say"] for s in scene["steps"]]
        clips = [tts(line, voice, cache, model) for line in lines]
        t, marks, cues = scene["pad"][0], [], []
        for line, clip in zip(lines, clips):
            marks.append(t)
            cues.append((t, t + len(clip) / SR, line))
            t += len(clip) / SR + gap
        dur = round((t - gap + scene["pad"][1]) * FPS) / FPS
        audio = np.zeros(int(round(dur * SR)), dtype=np.float32)
        for (start, _end, _l), clip in zip(cues, clips):
            i = int(round(start * SR))
            audio[i:i + len(clip)] += clip[:len(audio) - i]
        out.append({"scene": scene, "marks": marks, "cues": cues, "dur": dur, "audio": audio})
    return out


def write_wav(path, audio):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


# ---------- animated scenes ----------
def encode_frames(frames, dur, dest):
    """frames: iterable of JPEG bytes at FPS. Writes dest atomically."""
    tmp = dest.with_name(dest.stem + ".part.mp4")
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                             *X264, "-t", f"{dur:.4f}", str(tmp)], stdin=subprocess.PIPE)
    for f in frames:
        proc.stdin.write(f)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed for " + dest.name)
    tmp.rename(dest)


def animation_scene(page, item, dest, episode):
    n = int(round(item["dur"] * FPS))
    name = item["scene"]["id"]

    def frames():
        for i in range(n):
            page.evaluate("([n,t,m,e])=>render(n,t,m,e)", [name, i / FPS, item["marks"], episode])
            yield page.screenshot(type="jpeg", quality=92)
    encode_frames(frames(), item["dur"], dest)


# ---------- console scenes ----------
OVERLAY = r"""
(()=>{
  const css=`#__cur{position:fixed;z-index:2147483647;left:0;top:0;width:26px;height:26px;pointer-events:none;transform:translate(-3px,-2px);filter:drop-shadow(0 2px 4px rgba(0,0,0,.45))}
  .__rip{position:fixed;z-index:2147483646;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:999px;border:3px solid #57E0CC;pointer-events:none;animation:__r .55s ease-out forwards}
  @keyframes __r{from{transform:scale(.3);opacity:1}to{transform:scale(1.4);opacity:0}}
  .__ring{position:fixed;z-index:2147483645;border:3px solid #57E0CC;border-radius:12px;box-shadow:0 0 0 6px rgba(87,224,204,.22),0 0 40px rgba(87,224,204,.35);pointer-events:none;transition:opacity .3s}
  .__label{position:fixed;z-index:2147483645;padding:6px 12px;border-radius:8px;background:#57E0CC;color:#04110E;font:600 15px Inter,sans-serif;pointer-events:none;white-space:nowrap}`;
  const add=()=>{const s=document.createElement('style');s.textContent=css;document.head.append(s);
    const c=document.createElement('div');c.id='__cur';c.innerHTML='<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';document.body.append(c);
    addEventListener('mousemove',e=>{c.style.left=e.clientX+'px';c.style.top=e.clientY+'px';},true);
    addEventListener('mousedown',e=>{const r=document.createElement('div');r.className='__rip';r.style.left=e.clientX+'px';r.style.top=e.clientY+'px';document.body.append(r);setTimeout(()=>r.remove(),700);},true);};
  if(document.body)add();else addEventListener('DOMContentLoaded',add);
  window.__callout=(sel,label,ms,below)=>{const el=document.querySelector(sel);if(!el)return false;
    const ring=document.createElement('div');ring.className='__ring';const tag=label?document.createElement('div'):null;
    if(tag){tag.className='__label';tag.textContent=label;document.body.append(tag);}document.body.append(ring);
    const end=performance.now()+(ms||3000);
    const step=()=>{const r=el.getBoundingClientRect();Object.assign(ring.style,{left:(r.left-8)+'px',top:(r.top-8)+'px',width:(r.width+16)+'px',height:(r.height+16)+'px'});
      if(tag){const above=r.top-46,hdr=64;tag.style.left=(r.left-8)+'px';tag.style.top=(below||above<hdr?r.bottom+14:above)+'px';}
      if(performance.now()<end)requestAnimationFrame(step);else{ring.remove();if(tag)tag.remove();}};step();return true;};
})();
"""


class Console:
    """The real console: documented bootstrap, real server, real browser."""

    def __init__(self, browser, workdir):
        self.root = Path(workdir) / "qualityrag-local"
        shutil.rmtree(self.root, ignore_errors=True)  # every film starts from a fresh install
        info = json.loads(subprocess.check_output([sys.executable, "-m", "tools.activation_runtime.bootstrap", "--root", str(self.root)], cwd=REPO))
        self.token = Path(info["browser_token_file"]).read_text().strip()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]
        self.server = subprocess.Popen([sys.executable, "-m", "tools.activation_runtime.cli", "serve", "--root", str(self.root / "state"),
                                        "--keys", info["keys"], "--port", str(self.port)], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close(); break
            except OSError:
                time.sleep(0.1)
        # bypass_csp only lets the film's cursor and callout overlay run; the console itself is unchanged.
        self.context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5, color_scheme="dark", bypass_csp=True)
        self.context.add_init_script(OVERLAY)
        self.page = self.context.new_page()
        self.page.goto(f"http://127.0.0.1:{self.port}/")
        self.mouse = [640, 360]
        self.page.mouse.move(*self.mouse)
        self.cdp = self.context.new_cdp_session(self.page)
        self.frames = []
        self.cdp.on("Page.screencastFrame", self._frame)

    def _frame(self, e):
        self.frames.append((e["metadata"]["timestamp"], e["data"]))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": e["sessionId"]})
        except Exception:
            pass

    def close(self):
        self.context.close(); self.server.terminate(); self.server.wait(timeout=10)

    # --- actions ---
    def wait(self, ms): self.page.wait_for_timeout(ms)

    def move_to(self, locator, steps=28):
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        x, y = box["x"] + min(box["width"] / 2, 60), box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=steps); self.mouse = [x, y]

    def click(self, locator):
        self.move_to(locator); self.wait(180); self.page.mouse.down(); self.wait(70); self.page.mouse.up()

    def smooth(self, selector, block="center"):
        # scroll-margin keeps the target clear of the console's sticky top bar
        self.page.evaluate("([s,b])=>{const e=document.querySelector(s);e.style.scrollMarginTop='76px';e.scrollIntoView({behavior:'smooth',block:b})}", [selector, block]); self.wait(700)

    def callout(self, selector, label, ms=3200, below=False):
        self.page.evaluate("([s,l,m,b])=>window.__callout(s,l,m,b)", [selector, label, ms, below])

    def do(self, name):
        p = self.page
        if name == "signin":
            field = p.get_by_label("Access token")
            self.click(field); self.wait(300); field.fill(self.token); self.wait(500)
            self.click(p.get_by_role("button", name="Open workspace"))
            p.locator(".engine-row").first.wait_for()
        elif name == "home_engine":
            p.locator(".engine-row").filter(has_text="Evolution").filter(has_text="Not started").wait_for()
            self.wait(1400); self.smooth("#engine", "center"); self.callout("#engine", "Engine · live from the server", 4200)
        elif name == "open_ask":
            self.click(p.locator('[data-nav="ask"]')); p.locator("#gov-sample").wait_for(); self.wait(400)
            self.callout("#gov-sample", "Sample data", 2600)
        elif name == "tour_form":
            self.smooth("#gov-passages"); self.callout("#gov-passages", "Passages your search returned", 3000); self.wait(3300)
            self.smooth("#gov-pack-editor"); self.callout("#gov-pack-editor", "What the answer needs", 3000)
        elif name == "run_check":
            self.click(p.get_by_role("button", name="Check answer")); p.locator(".gov-verdict-word").wait_for(); self.wait(300)
            self.smooth("#gov-test-result", "start")
        elif name == "point_headline":
            self.callout(".gov-headline", None, 5200); self.wait(2600); self.callout(".gov-verdict .gov-stats", None, 2600)
        elif name == "select_screening":
            self.click(p.locator('.gov-req[data-requirement="eu-screening-control"]')); self.wait(400); self.smooth(".gov-spans")
        elif name == "point_unless":
            self.move_to(p.locator(".gov-span-text mark").first); self.callout(".gov-span-text mark", "unless", 4200)
        elif name == "select_recovery":
            self.click(p.locator('.gov-req[data-requirement="recovery-procedure"]')); self.wait(500)
            note = ".gov-span:nth-of-type(2) .gov-note"
            self.smooth(".gov-spans"); self.callout(".gov-spans", "Same origin: counted once", 3800)
        elif name == "untick_memo":
            self.smooth("#gov-passages"); memo = p.locator("#gov-passages label").filter(has_text="memo-exception")
            self.click(memo); self.wait(500)
            self.click(p.get_by_role("button", name="Check answer"))
            p.locator(".gov-verdict-word").filter(has_text="Not enough evidence").wait_for(); self.smooth("#gov-test-result", "start")
        elif name == "point_inconclusive":
            self.callout(".gov-verdict-main", "Not enough evidence", 4200)
        elif name == "hold":
            pass
        elif name == "open_health":
            self.click(p.locator('[data-nav="health"]')); p.locator(".gov-finding").first.wait_for()
        elif name == "point_findings":
            self.callout(".gov-findings", "Each finding has a fix", 4800, below=True)
        else:
            raise KeyError(name)

    def film(self, item, dest):
        steps = item["scene"]["steps"]
        self.frames = []
        first = self.page.screenshot(type="jpeg", quality=92)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})
        start = time.time()
        self.frames.append((start, None))
        for step, mark in zip(steps, item["marks"]):
            delay = start + mark - time.time()
            if delay > 0:
                self.wait(int(delay * 1000))
            self.do(step["do"])
        rest = start + item["dur"] - time.time()
        if rest > 0:
            self.wait(int(rest * 1000))
        self.cdp.send("Page.stopScreencast")
        overrun = time.time() - start - item["dur"]
        if overrun > 0.4:
            print(f"  warning: {item['scene']['id']} actions overran narration by {overrun:.1f}s; the end is trimmed")
        tmpdir = Path(tempfile.mkdtemp(dir=dest.parent))
        import base64
        listing, entries = tmpdir / "frames.txt", []
        frames = [(start, first)] + [(ts, base64.b64decode(d)) for ts, d in self.frames if d is not None]
        for i, (ts, data) in enumerate(frames):
            (tmpdir / f"{i:05d}.jpg").write_bytes(data)
            entries.append((max(0.0, ts - start), f"{i:05d}.jpg"))
        entries.sort()
        with listing.open("w") as f:
            f.write("ffconcat version 1.0\n")
            for i, (t, name) in enumerate(entries):
                nxt = entries[i + 1][0] if i + 1 < len(entries) else item["dur"] + 1
                f.write(f"file '{name}'\nduration {max(1 / FPS, nxt - t):.4f}\n")
            f.write(f"file '{entries[-1][1]}'\n")
        tmp = dest.with_name(dest.stem + ".part.mp4")
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS},tpad=stop_mode=clone:stop_duration=5", *X264, "-t", f"{item['dur']:.4f}", str(tmp)])
        tmp.rename(dest)
        shutil.rmtree(tmpdir)


# ---------- captions ----------
def fmt(t, sep):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", sep)


def captions(items, out_dir, stem):
    cues, offset = [], 0.0
    for it in items:
        for s, e, text in it["cues"]:
            cues.append((offset + s, offset + e + 0.15, text))
        offset += it["dur"]
    vtt = ["WEBVTT", ""] + [f"{fmt(s, '.')} --> {fmt(e, '.')}\n{t}\n" for s, e, t in cues]
    (out_dir / f"{stem}.vtt").write_text("\n".join(vtt))
    srt = [f"{i}\n{fmt(s, ',')} --> {fmt(e, ',')}\n{t}\n" for i, (s, e, t) in enumerate(cues, 1)]
    (out_dir / f"{stem}.srt").write_text("\n".join(srt))
    ass = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
           "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Default,Inter,40,&H00F3EFED,&H00F3EFED,&H1A120D0A,&H1A120D0A,0,0,0,0,100,100,0,0,3,14,0,2,260,260,54,1", "",
           "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for s, e, t in cues:
        a = lambda x: f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"
        ass.append(f"Dialogue: 0,{a(s)},{a(e)},Default,,0,0,0,,{t}")
    (out_dir / f"{stem}.ass").write_text("\n".join(ass) + "\n")
    return cues


# ---------- main ----------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("episode", type=Path)
    ap.add_argument("--voice-dir", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stills", nargs="*", help="scene:time pairs to draw as PNG instead of rendering")
    ap.add_argument("--only", nargs="*", help="render only these scene IDs (others reuse earlier files)")
    a = ap.parse_args(argv)
    script = json.loads((a.episode / "script.json").read_text())
    out = (a.out or a.episode / "out").resolve(); out.mkdir(parents=True, exist_ok=True)
    cache = out / "tts-cache"; cache.mkdir(exist_ok=True)
    items = timeline(script, a.voice_dir, cache)
    total = sum(i["dur"] for i in items)
    print(f"{script['id']}: {len(items)} scenes, {total:.1f}s")
    for it in items:
        print(f"  {it['scene']['id']:<11} {it['dur']:6.2f}s  marks {', '.join(f'{m:.1f}' for m in it['marks'])}")
    episode_label = script["title"].split("·", 1)[1].strip() if "·" in script["title"] else script["title"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        anim = browser.new_page(viewport={"width": W, "height": H})
        anim.goto((HERE / "scenes.html").as_uri()); anim.wait_for_timeout(300)
        if a.stills is not None:
            byid = {i["scene"]["id"]: i for i in items}
            for spec in a.stills:
                name, t = spec.split(":"); it = byid[name]
                anim.evaluate("([n,t,m,e])=>render(n,t,m,e)", [name, float(t), it["marks"], episode_label])
                anim.screenshot(path=str(out / f"still-{name}-{t}.png")); print("  still", name, t)
            browser.close(); return
        console = None
        try:
            for it in items:
                sid, dest = it["scene"]["id"], out / f"scene-{it['scene']['id']}.mp4"
                if a.only and sid not in a.only and dest.exists():
                    continue
                if it["scene"]["kind"] == "animation":
                    animation_scene(anim, it, dest, episode_label)
                else:
                    if console is None:
                        console = Console(browser, out)
                    console.film(it, dest)
                print("  rendered", sid)
        finally:
            if console:
                console.close()
            browser.close()
    stem = script["id"]
    with (out / "scenes.txt").open("w") as f:
        for it in items:
            f.write(f"file 'scene-{it['scene']['id']}.mp4'\n")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(out / "scenes.txt"), "-c", "copy", str(out / "video.mp4")])
    write_wav(out / "narration.wav", np.concatenate([i["audio"] for i in items]))
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out / "video.mp4"), "-i", str(out / "narration.wav"), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", str(out / f"{stem}-nocaptions.mp4")])
    captions(items, out, stem)
    tmp = out / f"{stem}.part.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out / f"{stem}-nocaptions.mp4"), "-vf", f"subtitles={out / (stem + '.ass')}",
         *X264, "-c:a", "copy", "-movflags", "+faststart", str(tmp)])
    tmp.rename(out / f"{stem}.mp4")
    print("wrote", out / f"{stem}.mp4")


if __name__ == "__main__":
    main()
