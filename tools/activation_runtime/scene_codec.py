"""Executable lossless scene-state reference codec, not learned semantic compression.

A shared palette grammar describes each frame's backdrop and timeline; exact
RGB residuals preserve everything else. This deliberately modest predictive
codec is a falsifiable baseline, not a claim of FF-RCT or perceptual understanding.
"""
from __future__ import annotations

import base64
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter_ns
import zlib

MODEL_SCHEMA = "qualityrag.scene-palette/v1"
PAYLOAD_SCHEMA = "qualityrag.scene-video/v1"
MAX_RAW = 24_000_000
MAX_FRAMES = 120


def canon(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 40_000_000:
        raise ValueError("Codec payload byte budget exceeded")
    return raw


def digest(value):
    return sha256(canon(value)).hexdigest()


def _run(args, *, data=None, timeout=30):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError("Bounded media operation failed")
    return result.stdout


def frames(path):
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError("Bounded local source required")
    probe = json.loads(_run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(path)]))
    streams = probe["streams"]
    video = [s for s in streams if s["codec_type"] == "video"]
    if len(video) != 1 or any(s["codec_type"] not in {"video", "audio"} for s in streams):
        raise ValueError("Unsupported tracks must not be silently discarded")
    v = video[0]
    width, height = v["width"], v["height"]
    fps = Fraction(v.get("avg_frame_rate", "0/1"))
    duration = float(probe["format"].get("duration", 0))
    if (not 0 < width <= 512 or not 0 < height <= 512 or not 0 < fps <= 30
            or not 0 < duration <= 10 or duration * float(fps) > MAX_FRAMES
            or duration * float(fps) * width * height * 3 > MAX_RAW):
        raise ValueError("Clip exceeds prototype memory/frame/device limits")
    # Reject variable timing, reordering or nonzero origin rather than changing it.
    times = json.loads(_run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "frame=best_effort_timestamp_time",
                             "-of", "json", str(path)]))["frames"]
    for i, row in enumerate(times):
        if abs(float(row.get("best_effort_timestamp_time", -1)) - float(i / fps)) > 0.001:
            raise ValueError("Only zero-origin constant-frame-rate input is supported")
    raw = _run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0",
                "-pix_fmt", "rgb24", "-fps_mode", "passthrough", "-f", "rawvideo", "-"])
    size = width * height * 3
    if not raw or len(raw) > MAX_RAW or len(raw) % size or len(raw)//size != len(times):
        raise ValueError("Frame inventory mismatch or memory budget")
    audio_streams = [s for s in streams if s["codec_type"] == "audio"]
    if len(audio_streams) > 1:
        raise ValueError("Multiple audio streams unsupported")
    audio = None
    if audio_streams:
        a = audio_streams[0]
        if not 0 < int(a["sample_rate"]) <= 96000 or not 0 < a["channels"] <= 2:
            raise ValueError("Audio format outside bounded profile")
        if abs(float(a.get("start_time","0")))>0.000001:
            raise ValueError("Nonzero audio origin requires an unsupported timing adapter")
        audio = _run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
                      "-c:a", "pcm_s32le", "-f", "wav", "-"])
        if len(audio) > 8_000_000:
            raise ValueError("Audio byte budget")
    # ffprobe's local filename is a host locator, not content from the source bytes.
    probe["format"].pop("filename",None)
    return {"width": width, "height": height, "fps": str(fps),
            "frames": [raw[i:i+size] for i in range(0, len(raw), size)],
            "audio": audio, "source_frame_pts":[row["best_effort_timestamp_time"] for row in times], "source_sha256": sha256(path.read_bytes()).hexdigest(),
            "metadata": probe}


def train_model(sources):
    if not isinstance(sources, list) or not 1 <= len(sources) <= 16:
        raise ValueError("Bounded declared training corpus required")
    colors = Counter()
    identities = []
    for source in sources:
        item = frames(source)
        identities.append(item["source_sha256"])
        for frame in item["frames"][:8]:
            for i in range(0, len(frame), 3*256):
                colors[tuple(frame[i:i+3])] += 1
    palette = [list(color) for color, _ in sorted(colors.items(), key=lambda x: (-x[1], x[0]))[:16]]
    return {"schema": MODEL_SCHEMA, "algorithm": "flat-backdrop-rgb-xor/v1",
            "palette": palette, "training_sources": sorted(set(identities)),
            "interpretation": "PIXEL_PREDICTION_NOT_SEMANTIC_TRUTH"}


def _model(model):
    if (not isinstance(model, dict) or model.get("schema") != MODEL_SCHEMA
            or model.get("algorithm") != "flat-backdrop-rgb-xor/v1"
            or not isinstance(model.get("palette"), list) or not 1 <= len(model["palette"]) <= 16):
        raise ValueError("Incompatible shared model")
    for color in model["palette"]:
        if not isinstance(color, list) or len(color) != 3 or any(type(x) is not int or not 0 <= x <= 255 for x in color):
            raise ValueError("Invalid palette")
    return model


def encode(source, model):
    _model(model)
    item = frames(source)
    start = perf_counter_ns()
    records, fallback = [], 0
    for index, frame in enumerate(item["frames"]):
        mean = [sum(frame[channel::3]) // (len(frame)//3) for channel in range(3)]
        code = min(range(len(model["palette"])), key=lambda n: sum(
            (mean[c]-model["palette"][n][c])**2 for c in range(3)))
        backdrop = bytes(model["palette"][code])
        residual = bytes(value ^ backdrop[i % 3] for i, value in enumerate(frame))
        compressed = zlib.compress(residual, 9)
        mode, payload = ("xor-zlib", compressed) if len(compressed) < len(frame) else ("raw", frame)
        fallback += mode == "raw"
        records.append({"index": index, "backdrop": code, "mode": mode,
                        "frame_sha256": sha256(frame).hexdigest(),
                        "data": base64.b64encode(payload).decode()})
    payload = {"schema": PAYLOAD_SCHEMA, "codec": "scene-palette-rgb/v1",
               "runtime_abi": "python-scene-reference/v1", "model_sha256": digest(model),
               "source_sha256": item["source_sha256"], "width": item["width"], "height": item["height"],
               "fps": item["fps"], "frame_count": len(records), "frames": records,
               "audio_wav": base64.b64encode(item["audio"]).decode() if item["audio"] else None,
               "source_frame_pts":item["source_frame_pts"],
               "normalized_profile": "RGB24_CFR_AND_PCM32_AUDIO",
               "original_metadata": item["metadata"]}
    return payload, {"encode_ns": perf_counter_ns()-start, "payload_bytes": len(canon(payload)),
                     "model_bytes": len(canon(model)), "fallback_ratio": fallback/len(records),
                     "qualityrag_admission": "INCONCLUSIVE", "can_generate": False}


def _inflate(data, expected):
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(data, expected+1)
    except zlib.error as exc:
        raise ValueError("Corrupt residual stream") from exc
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Residual length, trailing data or decompression budget violation")
    return raw


def decode_frames(payload, model, *, start=0, stop=None, implementation="scalar"):
    _model(model)
    if implementation not in {"scalar","strided"}:raise ValueError("Unsupported decoder implementation")
    if (not isinstance(payload, dict) or payload.get("schema") != PAYLOAD_SCHEMA
            or payload.get("codec") != "scene-palette-rgb/v1"
            or payload.get("runtime_abi") != "python-scene-reference/v1"
            or payload.get("model_sha256") != digest(model)):
        raise ValueError("Payload/model/runtime compatibility mismatch")
    w, h, count = payload.get("width"), payload.get("height"), payload.get("frame_count")
    if (type(w) is not int or type(h) is not int or not 0 < w <= 512 or not 0 < h <= 512
            or type(count) is not int or not 1 <= count <= MAX_FRAMES
            or count*w*h*3 > MAX_RAW):
        raise ValueError("Decoded memory/frame budget")
    stop = count if stop is None else stop
    if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= count:
        raise ValueError("Invalid seek range")
    records = payload.get("frames")
    if not isinstance(records, list) or len(records) != count:
        raise ValueError("Missing frame segments")
    if any(not isinstance(row, dict) or row.get("index") != i for i, row in enumerate(records)):
        raise ValueError("Out-of-order or duplicate segment")
    output = []
    for row in records[start:stop]:
        code = row.get("backdrop")
        if type(code) is not int or not 0 <= code < len(model["palette"]):
            raise ValueError("Missing grammar code")
        try:
            data = base64.b64decode(row["data"], validate=True)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("Invalid residual") from exc
        if row.get("mode") == "xor-zlib":
            residual = _inflate(data, w*h*3)
            bg = bytes(model["palette"][code])
            if implementation=="strided":
                decoded=bytearray(len(residual))
                for channel in range(3):
                    table=bytes(value ^ bg[channel] for value in range(256))
                    decoded[channel::3]=residual[channel::3].translate(table)
                frame=bytes(decoded)
            else:
                frame = bytes(value ^ bg[i % 3] for i, value in enumerate(residual))
        elif row.get("mode") == "raw" and len(data) == w*h*3:
            frame = data
        else:
            raise ValueError("Unsupported residual mode")
        if sha256(frame).hexdigest() != row.get("frame_sha256"):
            raise ValueError("Residual/frame integrity mismatch")
        output.append(frame)
    return output


def decode(payload, model, output):
    target = Path(output).resolve()
    if target.exists():
        raise ValueError("Output must be new")
    start = perf_counter_ns()
    decoded = decode_frames(payload, model)
    fps = Fraction(payload["fps"])
    if not 0 < fps <= 30:
        raise ValueError("Frame rate budget")
    with tempfile.TemporaryDirectory() as temp:
        raw_path = Path(temp)/"frames.rgb"
        raw_path.write_bytes(b"".join(decoded))
        args = ["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "rawvideo",
                "-pixel_format", "rgb24", "-video_size", str(payload["width"])+"x"+str(payload["height"]),
                "-framerate", str(fps), "-i", str(raw_path)]
        if payload["audio_wav"] is not None:
            audio = base64.b64decode(payload["audio_wav"], validate=True)
            if len(audio) > 8_000_000:
                raise ValueError("Audio byte budget")
            wav = Path(temp)/"audio.wav"
            wav.write_bytes(audio)
            args += ["-i", str(wav)]
        args += ["-c:v", "ffv1", "-pix_fmt", "bgr0", "-c:a", "pcm_s32le", str(target)]
        _run(args)
    # Verify the playable output, not merely the in-memory decoded buffer.
    observed=frames(target)
    if observed["frames"]!=decoded or [Fraction(t) for t in observed["source_frame_pts"]]!=[Fraction(t) for t in payload["source_frame_pts"]]:
        target.unlink()
        raise ValueError("Playable output frame or timestamp mismatch")
    if payload["audio_wav"] is not None:
        expected_pcm=_run(["ffmpeg","-nostdin","-v","error","-i","pipe:0","-f","s32le","-"],
                          data=base64.b64decode(payload["audio_wav"],validate=True))
        actual_pcm=_run(["ffmpeg","-nostdin","-v","error","-i",str(target),"-map","0:a:0","-f","s32le","-"])
        if expected_pcm!=actual_pcm:
            target.unlink();raise ValueError("Playable output audio sample mismatch")
    return {"decode_ns": perf_counter_ns()-start, "decoded_frames": len(decoded),
            "output_sha256": sha256(target.read_bytes()).hexdigest(),
            "fidelity": "EXACT_NORMALIZED_RGB_FRAMES_VERIFIED", "can_generate": False}


def segment_index(payload):
    count = payload["frame_count"]
    if not isinstance(count, int) or count != len(payload["frames"]):
        raise ValueError("Invalid frame index")
    fps = Fraction(payload["fps"])
    return [{"index": i, "time": str(Fraction(payload["source_frame_pts"][i])), "model_sha256": payload["model_sha256"],
             "dependencies": [], "segment_sha256": digest(row)} for i, row in enumerate(payload["frames"])]
