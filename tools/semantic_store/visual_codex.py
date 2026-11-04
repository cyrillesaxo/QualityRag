"""Bounded, non-biometric visual reference representation (v0.4).

Pillow supplies a 64-bit perceptual difference hash for image *appearance*.
Optional FFmpeg can sample video frames; neither is object detection, face
recognition, identity proof, or a semantic captioner. Every match is labeled
VISUAL_APPEARANCE_SIMILARITY_CANDIDATE, not "contains Cyrille".
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import subprocess

from semantic_codex import CodexError, SCHEMA
from store import digest

IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp"}
VIDEO_FORMATS = {"mp4", "mov", "mkv"}
MAX_IMAGE_PIXELS = 12_000_000
MAX_FRAMES = 12
MAX_FRAME_BYTES = 2_000_000
VIDEO_SECONDS = 60


def _dhash(image) -> str:
    from PIL import Image, ImageOps
    # EXIF orientation is applied to ensure stable frame interpretation.
    image = ImageOps.exif_transpose(image)
    scaled = image.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
    pixels = list(scaled.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return f"{bits:016x}"


def _image_fingerprint(data: bytes) -> tuple[str, dict]:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_FRAME_BYTES:
        raise CodexError("Image frame exceeds size limit")
    try:
        from PIL import Image, UnidentifiedImageError
        with Image.open(BytesIO(data)) as picture:
            width, height = picture.size
            if width < 2 or height < 2 or width * height > MAX_IMAGE_PIXELS:
                raise CodexError("Image dimensions outside bounded visual model")
            if picture.format not in ("PNG", "JPEG", "WEBP"):
                raise CodexError("Unsupported image container")
            key = _dhash(picture)
            return key, {"width": width, "height": height}
    except CodexError:
        raise
    except (OSError, ValueError, SyntaxError, ImportError) as exc:
        raise CodexError("Image parser unavailable or invalid input") from exc


def _video_frames(data: bytes, *, format: str) -> list[tuple[int, bytes]]:
    """Sample at deterministic seconds, up to 60 seconds; temporary video
    bytes are piped to ffmpeg, not written to persistent source custody.
    ffmpeg path must be chosen by a trusted host, never taken from the query.
    """
    if format not in VIDEO_FORMATS:
        raise CodexError("Unsupported video format")
    if not 0 < len(data) <= MAX_FRAME_BYTES:
        raise CodexError("Video input size exceeds limit")
    # One JPEG image per sample, up to one every five seconds. Running
    # ffmpeg is optional; missing tooling refuses indexing without fallback.
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
           "-i", "pipe:0", "-t", str(VIDEO_SECONDS), "-vf", "fps=1/5,scale=640:-2",
           "-frames:v", str(MAX_FRAMES), "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
    try:
        proc = subprocess.run(cmd, input=data, capture_output=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CodexError("Video sampling unavailable or timed out") from e
    if proc.returncode != 0 or len(proc.stdout) > 12_000_000:
        raise CodexError("Video frame extraction failed or exceeded cap")
    output = proc.stdout
    starts = [i for i in range(len(output) - 1) if output[i:i+2] == b"\xff\xd8"]
    ends = [i+2 for i in range(len(output) - 1) if output[i:i+2] == b"\xff\xd9"]
    if not starts or len(starts) != len(ends):
        raise CodexError("Video returned no complete frames")
    frames=[]
    for i, (start, end) in enumerate(zip(starts,ends)):
        if end <= start or end - start > MAX_FRAME_BYTES:
            raise CodexError("Invalid sampled frame")
        frames.append((i * 5000, output[start:end]))
    if len(frames) > MAX_FRAMES:
        raise CodexError("Too many sampled frames")
    return frames


def compile_visual(source: bytes, *, source_id: str, revision: str, format: str,
                   frame_sampler=None) -> dict:
    if (format not in IMAGE_FORMATS | VIDEO_FORMATS
            or not isinstance(source, bytes) or not 0 < len(source) <= MAX_FRAME_BYTES
            or not isinstance(source_id,str) or not 0 < len(source_id) <= 256
            or not isinstance(revision,str) or not 0 < len(revision) <= 256):
        raise CodexError("Invalid bounded visual source")
    if format in IMAGE_FORMATS:
        frames = [(0, source)]
    else:
        frames = (frame_sampler or _video_frames)(source, format=format)
    if (not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES
            or any(type(ms) is not int or ms < 0 or ms >= VIDEO_SECONDS*1000
                   or not isinstance(frame, bytes) for ms, frame in frames)):
        raise CodexError("Invalid bounded visual frame inventory")
    records=[]
    for i, (ms, frame) in enumerate(frames):
        visual_hash, dimensions = _image_fingerprint(frame)
        anchor = ({"kind":"image_frame",**dimensions}
                  if format in IMAGE_FORMATS else
                  {"kind":"video_frame","timestamp_ms":ms,**dimensions})
        records.append({"id":f"{source_id}#{i}","anchor":anchor,
                        "fields":{"visual_hash":{"type":"TEXT","value":visual_hash}},
                        "status":"STRUCTURAL_CANDIDATE"})
    result={
        "schema":SCHEMA,
        "source":{"source_id":source_id,"revision":revision,"format":format,
                  "sha256":sha256(source).hexdigest(),"bytes":len(source)},
        "records":records,
        "governance":{"packspec":"NOT_BOUND","admission":"INCONCLUSIVE"},
        "source_authenticity":"UNVERIFIED",
        "semantic_interpretation":"NOT_PERFORMED",
        "identity_recognition":"NOT_PERFORMED",
        "extraction_coverage":"BOUNDED_VISUAL_REFERENCE_ONLY",
        "visual_method":"64_BIT_DHASH_NOT_IDENTITY_OR_OBJECT_SEMANTICS",
        "reconstruction":{"source_bytes_required":True,
                          "source_bytes_embedded":False,
                          "exact_source_bytes_recoverable_from_ir":False},
    }
    result["fingerprint"]=digest(result)
    return result


def hamming64(a: str,b: str) -> int:
    if (not isinstance(a,str) or not isinstance(b,str)
            or len(a)!=16 or len(b)!=16 or
            any(c not in "0123456789abcdef" for c in a+b)):
        raise CodexError("Expected two 64-bit lowercase perceptual hashes")
    return (int(a,16)^int(b,16)).bit_count()
