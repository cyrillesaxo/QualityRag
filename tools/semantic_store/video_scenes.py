"""Bounded low-resolution visual change-point proposals.

This does NOT recognize actions, objects, or verified scene boundaries.
It identifies abrupt changes in decoded luminance; camera movement, lighting,
cuts and compression artifacts can all trigger it. Gradual motion may be missed.
"""
from __future__ import annotations
import subprocess

from video_evidence import VideoEvidenceError

WIDTH = 32
HEIGHT = 18
PIXELS = WIDTH * HEIGHT


def luminance_frame(path, time_ms, *, decoder=None):
    if type(time_ms) is not int or time_ms < 0:
        raise VideoEvidenceError("Invalid frame time")
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
               "-ss", f"{time_ms / 1000:.3f}", "-i", str(path),
               "-frames:v", "1", "-vf", f"scale={WIDTH}:{HEIGHT},format=gray",
               "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    runner = decoder or subprocess.run
    result = runner(command, capture_output=True, check=True, timeout=45)
    pixels = result.stdout
    if not isinstance(pixels, bytes) or len(pixels) != PIXELS:
        raise VideoEvidenceError("Invalid low-resolution frame")
    return pixels


def normalized_frame_difference(left, right):
    if not isinstance(left, bytes) or not isinstance(right, bytes) or len(left) != PIXELS or len(right) != PIXELS:
        raise VideoEvidenceError("Invalid grayscale frame")
    return sum(abs(a-b) for a, b in zip(left, right)) / (PIXELS * 255)


def propose_change_windows(path, duration_ms, *, cadence_ms=2000,
                           threshold=0.24, margin_ms=600,
                           max_probes=200, max_windows=50, decoder=None):
    """Return time-bounded candidate regions of visual change.

    Detection uses regular probe times, not selected image-model results, so
    every sample is reproducible. No score is treated as a likelihood.
    """
    if (type(duration_ms) is not int or duration_ms <= 0
            or type(cadence_ms) is not int or cadence_ms < 250
            or type(margin_ms) is not int or margin_ms < 1
            or type(max_probes) is not int or not 2 <= max_probes <= 1000
            or type(max_windows) is not int or not 1 <= max_windows <= 500
            or type(threshold) not in (int, float) or not 0 <= threshold <= 1):
        raise VideoEvidenceError("Invalid scene scan settings")
    times = list(range(0, duration_ms, cadence_ms))
    if len(times) > max_probes:
        raise VideoEvidenceError("Scene probe budget exceeded")
    previous = None
    changes = []
    for ms in times:
        current = luminance_frame(path, ms, decoder=decoder)
        if previous is not None:
            score = normalized_frame_difference(previous, current)
            if score >= threshold:
                changes.append((ms, score))
                if len(changes) > max_windows:
                    raise VideoEvidenceError("Scene transition budget exceeded")
        previous = current
    windows = []
    for at, score in changes:
        begin = max(0, at - margin_ms)
        end = min(duration_ms, at + margin_ms + 1)
        if windows and begin <= windows[-1]["end_ms"]:
            windows[-1]["end_ms"] = max(windows[-1]["end_ms"], end)
            windows[-1]["peak_difference"] = max(windows[-1]["peak_difference"], round(score, 5))
        else:
            windows.append({"start_ms": begin, "end_ms": end,
                            "peak_difference": round(score, 5)})
    return {"windows": windows,
            "change_points_ms": [at for at, _ in changes],
            "receipt": {"detector": "luminance-absolute-difference/v1",
                        "cadence_ms": cadence_ms, "threshold": threshold,
                        "probed_frames": len(times), "candidate_transition_count": len(changes),
                        "interpretation": "UNVERIFIED_CHANGE_POINT"}}
