"""Actual AV1 encode/decode baseline with an explicit licensed-input manifest.

This is baseline instrumentation, not a Semantic Codex video decoder. An
uninstalled neural codec or absent rights evidence remains an unmet obligation.
Paths are host-selected local files; no URLs or shell strings are executed.
"""
from hashlib import sha256
import json
from fractions import Fraction
from pathlib import Path
import subprocess
from time import perf_counter_ns


def _run(args, timeout=60):
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError("Media command failed: " + result.stderr.decode(errors="replace")[-2000:])
    return result.stdout


def benchmark_av1(source, output, *, rights_ref, split_family):
    source, output = Path(source).resolve(), Path(output).resolve()
    if (not source.is_file() or source.stat().st_size > 100_000_000
            or not isinstance(rights_ref, str) or not rights_ref.strip()
            or not isinstance(split_family, str) or not split_family.strip()
            or source == output or output.exists()):
        raise ValueError("Bounded authorized input and fresh output path required")
    probe = json.loads(_run(["ffprobe", "-v", "error", "-show_streams",
                             "-show_format", "-of", "json", str(source)]))
    videos = [s for s in probe["streams"] if s["codec_type"] == "video"]
    if len(videos) != 1:
        raise ValueError("Exactly one video stream supported")
    v = videos[0]
    duration = float(probe["format"].get("duration", 0))
    if not 0 < duration <= 30 or not 0 < v["width"] <= 1920 or not 0 < v["height"] <= 1080:
        raise ValueError("Short bounded clip required")
    fps = Fraction(v.get("avg_frame_rate", "0/1"))
    if not 0 < fps <= 60 or duration * float(fps) * v["width"] * v["height"] * 3 > 100_000_000:
        raise ValueError("Decoded frame memory budget exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    start = perf_counter_ns()
    _run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(source),
          "-map", "0:v:0", "-map", "0:a?", "-c:v", "libaom-av1", "-cpu-used", "8",
          "-crf", "0", "-b:v", "0", "-c:a", "flac", str(output)])
    encode_ns = perf_counter_ns() - start
    def decoded(path):
        return _run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                     "-map", "0:v:0", "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"])
    baseline = decoded(source)
    start = perf_counter_ns()
    reconstructed = decoded(output)
    decode_ns = perf_counter_ns() - start
    exact = baseline == reconstructed
    return {"schema": "qualityrag.av1-baseline/v1", "rights_ref": rights_ref,
            "rights_verification": "CALLER_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
            "split_family": split_family, "source_sha256": sha256(source.read_bytes()).hexdigest(),
            "encoded_sha256": sha256(output.read_bytes()).hexdigest(),
            "source_bytes": source.stat().st_size, "encoded_bytes": output.stat().st_size,
            "encode_ns": encode_ns, "decode_ns": decode_ns,
            "decoded_frame_sha256": sha256(reconstructed).hexdigest(),
            "yuv420p_frame_bytes_equal": exact,
            "comparison_scope": "NORMALIZED_VIDEO_FRAME_BYTES_ONLY",
            "audio_timing_subtitles_identity": "NOT_INDEPENDENTLY_EVALUATED",
            "tool_version": _run(["ffmpeg", "-version"]).decode().splitlines()[0],
            "neural_codec": "NOT_INSTALLED", "semantic_codex_codec": "NOT_IMPLEMENTED",
            "energy_j": None, "total_cost_advantage": "NOT_ESTABLISHED",
            "qualityrag_admission": "INCONCLUSIVE", "can_generate": False}
