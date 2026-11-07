"""Opt-in local-media video perception pipeline for Semantic Store candidates.

Dependencies: ffmpeg/ffprobe; optional faster-whisper; optional local Ollama vision.
No YouTube downloader or remote provider is invoked. No model output is a verdict.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from video_evidence import compile_video_evidence, VideoEvidenceError
from video_temporal import group_observations
from video_scenes import propose_change_windows
from video_transitions import propose_visual_transitions, vision_transition_ollama
from video_tracking import associate_detections, track_events


def media_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_duration_ms(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, check=True, timeout=30).stdout.decode("utf-8").strip()
    seconds = float(out)
    if not math.isfinite(seconds) or seconds <= 0:
        raise VideoEvidenceError("Invalid video duration")
    return int(seconds * 1000)


def sample_times(duration_ms, interval_ms=5000, windows=None, max_frames=200):
    """Regular control samples + dense inspection near requested time windows."""
    if (type(duration_ms) is not int or duration_ms <= 0
            or type(interval_ms) is not int or interval_ms < 250
            or type(max_frames) is not int or not 1 <= max_frames <= 1000):
        raise VideoEvidenceError("Invalid sampling configuration")
    times = set(range(0, duration_ms, interval_ms))
    if windows:
        for window in windows:
            if not isinstance(window, dict):
                raise VideoEvidenceError("Invalid inspection window")
            a, b = window.get("start_ms"), window.get("end_ms")
            if (type(a) is not int or type(b) is not int
                    or not 0 <= a < b <= duration_ms):
                raise VideoEvidenceError("Invalid inspection window interval")
            times.update(range(a, b, max(250, interval_ms // 5)))
            times.add(b - 1)
    ordered = sorted(times)
    if len(ordered) > max_frames:
        raise VideoEvidenceError("Frame budget exceeded; increase interval or frame limit explicitly")
    return ordered


def extract_frame(path, time_ms, *, max_width=768):
    if type(time_ms) is not int or time_ms < 0 or type(max_width) is not int or not 64 <= max_width <= 1920:
        raise VideoEvidenceError("Invalid frame extraction request")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-ss", f"{time_ms / 1000:.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale='min({max_width},iw)':-2",
         "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        capture_output=True, check=True, timeout=60)
    if not result.stdout or len(result.stdout) > 10_000_000:
        raise VideoEvidenceError("Could not decode bounded frame")
    return result.stdout


def asr_faster_whisper(path, model_name):
    """Optional local model. No model is downloaded without explicit invocation."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise VideoEvidenceError("Install faster-whisper to enable ASR") from exc
    model = WhisperModel(model_name, device="auto", compute_type="auto")
    segments, info = model.transcribe(str(path), word_timestamps=True,
                                       vad_filter=True)
    out = []
    for index, segment in enumerate(segments):
        a, b = round(segment.start * 1000), round(segment.end * 1000)
        if b <= a or not segment.text.strip():
            continue
        out.append({"id": f"audio-{index}", "modality": "audio",
                    "interval": {"start_ms": a, "end_ms": b},
                    "text": segment.text.strip(), "provider": f"faster-whisper:{model_name}",
                    "confidence": None})
    return out, {"provider": "faster-whisper", "model": model_name,
                 "language": info.language, "trust": "UNVERIFIED_OUTPUT"}


def vision_ollama_local(frame_bytes, *, model_name, endpoint="http://127.0.0.1:11434"):
    """Send a frame only to loopback Ollama, never to an arbitrary remote URL."""
    if endpoint.rstrip("/") not in ("http://127.0.0.1:11434", "http://localhost:11434"):
        raise VideoEvidenceError("Only loopback Ollama is supported")
    if not isinstance(model_name, str) or not model_name.strip() or len(model_name) > 128:
        raise VideoEvidenceError("Invalid vision model")
    prompt = ("Describe only what is visibly present in this single frame. "
              "Report objects, spatial relationships, text, and possible actions; "
              "do not claim motion or action completion from one image. "
              "Say 'uncertain' when necessary. Do not identify people.")
    data = json.dumps({"model": model_name,
                       "messages": [{"role": "user", "content": prompt,
                                     "images": [base64.b64encode(frame_bytes).decode("ascii")]}],
                       "stream": False, "options": {"temperature": 0}}).encode("utf-8")
    request = Request(endpoint.rstrip("/") + "/api/chat", data=data,
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise VideoEvidenceError("Local vision inference failed")
        payload = response.read(1_000_001)
    if len(payload) > 1_000_000:
        raise VideoEvidenceError("Vision output too large")
    try:
        output = json.loads(payload)
        description = output["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise VideoEvidenceError("Invalid vision-model response") from exc
    if not isinstance(description, str) or not description.strip():
        raise VideoEvidenceError("Empty vision-model response")
    return description[:10000]


def compile_local_media(path, *, source_id, revision, asr_model=None,
                        vision_model=None, interval_ms=5000, max_frames=200,
                        inspection_windows=None, vision=None,
                        detect_scene_changes=False, scene_cadence_ms=2000,
                        scene_threshold=0.24, detect_transitions=False,
                        transition_compare=None, max_transition_pairs=40,
                        detections=None):
    """Run explicitly requested local adapters and produce unverified evidence.

    A vision callable can replace Ollama for testing or another reviewed provider.
    No inference is made if neither model is selected.
    """
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise VideoEvidenceError("Media path must be a file")
    duration_ms = probe_duration_ms(path)
    witnesses = []
    receipts = []
    if asr_model:
        speech, receipt = asr_faster_whisper(path, asr_model)
        for w in speech:
            w["interval"]["end_ms"] = min(w["interval"]["end_ms"], duration_ms)
            if w["interval"]["start_ms"] < w["interval"]["end_ms"]:
                witnesses.append(w)
        receipts.append(receipt)

    if (detect_scene_changes or detect_transitions) and not vision_model:
        raise VideoEvidenceError("Scene-aware sampling requires a vision model")
    active_windows = list(inspection_windows or [])
    if detect_scene_changes:
        scene_scan = propose_change_windows(
            path, duration_ms, cadence_ms=scene_cadence_ms,
            threshold=scene_threshold)
        active_windows.extend(
            {"start_ms": w["start_ms"], "end_ms": w["end_ms"]}
            for w in scene_scan["windows"])
        receipts.append(scene_scan["receipt"])

    if vision_model:
        analyzer = vision or (lambda b: vision_ollama_local(b, model_name=vision_model))
        sampling_times = sample_times(duration_ms, interval_ms, active_windows, max_frames)
        if detect_transitions and len(sampling_times) - 1 > max_transition_pairs:
            raise VideoEvidenceError("Transition pair budget exceeded")
        previous_frame = None
        transition_candidates = []
        comparator = transition_compare or (lambda a, b: vision_transition_ollama(
            a, b, model_name=vision_model))
        for i, at in enumerate(sampling_times):
            frame = extract_frame(path, at)
            description = analyzer(frame)
            if not isinstance(description, str) or not description.strip():
                raise VideoEvidenceError("Empty visual observation")
            item = {
                "id": f"frame-{i}", "modality": "video",
                "interval": {"start_ms": at, "end_ms": min(at + 1, duration_ms)},
                "text": description[:10000], "provider": f"vision:{vision_model}",
                "frame_sha256": hashlib.sha256(frame).hexdigest()}
            witnesses.append(item)
            if detect_transitions and previous_frame is not None:
                transition_candidates.extend(propose_visual_transitions(
                    [(previous_frame, (item, frame))], compare=comparator))
            previous_frame = (item, frame)
        receipts.append({"provider": "ollama-local" if vision is None else "injected-vision",
                         "model": vision_model, "sampling_interval_ms": interval_ms,
                         "sampled_frames": sum(w["modality"] == "video" for w in witnesses),
                         "trust": "UNVERIFIED_OUTPUT"})
    events = group_observations(witnesses, duration_ms, window_ms=interval_ms)
    if detect_transitions:
        for i, candidate in enumerate(transition_candidates):
            events.append({
                "id": f"transition-{i}", "label": "candidate visual attribute transition",
                "interval": candidate["interval"],
                "witnesses": [candidate["before_witness"], candidate["after_witness"]],
                "changes": [candidate],
                "constraints": [{"name": "transition_verified", "state": "UNKNOWN",
                                 "witnesses": [candidate["before_witness"], candidate["after_witness"]]}]
            })
        receipts.append({"provider": "ollama-local" if transition_compare is None else "injected-comparator",
                         "model": vision_model, "task": "paired-frame-attribute-comparison",
                         "pair_count": len(transition_candidates),
                         "trust": "UNVERIFIED_OUTPUT"})
    if detections is not None:
        if not vision_model:
            raise VideoEvidenceError("Tracking requires a vision model and hashed visual witnesses")
        tracks = associate_detections(detections, witnesses)
        events.extend(track_events(tracks))
        receipts.append({"provider": "caller-supplied-detections", "task": "geometric-track-proposals",
                         "detection_count": len(detections), "track_count": len(tracks),
                         "trust": "UNVERIFIED_OUTPUT"})
    return compile_video_evidence(
        source_id=source_id, revision=revision, media_sha256=media_hash(path),
        duration_ms=duration_ms, witnesses=witnesses, events=events,
        model_receipts=receipts)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Opt-in local video evidence candidates")
    parser.add_argument("media", help="Local media file; no network downloads")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--asr-model", default=None,
                        help="Explicitly opt into local faster-whisper inference")
    parser.add_argument("--vision-model", default=None,
                        help="Explicitly opt into loopback Ollama vision inference")
    parser.add_argument("--interval-ms", type=int, default=5000)
    parser.add_argument("--max-frames", type=int, default=200)
    parser.add_argument("--scene-scan", action="store_true",
                        help="Detect candidate abrupt visual changes before vision inference")
    parser.add_argument("--scene-cadence-ms", type=int, default=2000)
    parser.add_argument("--scene-threshold", type=float, default=0.24)
    parser.add_argument("--compare-transitions", action="store_true",
                        help="Opt into paired-frame visual attribute comparisons")
    parser.add_argument("--max-transition-pairs", type=int, default=40)
    parser.add_argument("--detections-json", default=None,
                        help="Optional JSON array of externally generated bounding-box detections")
    parser.add_argument("--inspection-windows", default=None,
                        help="Path to JSON array of dense sample windows")
    parser.add_argument("--output", required=True, help="Output candidate evidence JSON")
    args = parser.parse_args(argv)
    windows = None
    if args.inspection_windows:
        windows = json.loads(Path(args.inspection_windows).read_text(encoding="utf-8"))
        if not isinstance(windows, list):
            raise VideoEvidenceError("Expected array of inspection windows")
    if not args.asr_model and not args.vision_model:
        parser.error("Select --asr-model and/or --vision-model")
    detections = None
    if args.detections_json:
        detections = json.loads(Path(args.detections_json).read_text(encoding="utf-8"))
    artifact = compile_local_media(
        args.media, source_id=args.source_id, revision=args.revision,
        asr_model=args.asr_model, vision_model=args.vision_model,
        interval_ms=args.interval_ms, max_frames=args.max_frames,
        inspection_windows=windows, detect_scene_changes=args.scene_scan,
        scene_cadence_ms=args.scene_cadence_ms,
        scene_threshold=args.scene_threshold,
        detect_transitions=args.compare_transitions,
        max_transition_pairs=args.max_transition_pairs,
        detections=detections)
    Path(args.output).write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
