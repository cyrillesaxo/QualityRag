"""Build the Academy page: chapters.json + real lab output (+ optional video URL map) -> index.html.

    python docs/academy/build.py                     # videos load from episodes/<id>/<id>.mp4
    python docs/academy/build.py --videos urls.json  # e.g. hosted copies of the videos
"""
import argparse, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "index.html")
    a = ap.parse_args(argv)
    data = json.loads((HERE / "chapters.json").read_text())
    data["labs"] = {c["lab_file"]: subprocess.run([sys.executable, str(HERE / "labs" / c["lab_file"])], capture_output=True, text=True, check=True).stdout.strip("\n")
                    for c in data["chapters"]}
    data["videos"] = json.loads(a.videos.read_text()) if a.videos else {}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    a.out.write_text((HERE / "page.html").read_text().replace("/*__DATA__*/null", blob))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
