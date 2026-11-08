"""Permission-scoped video source registry. Metadata is declared, not verified.

URLs are citation hints only, never fetched. Only explicitly published,
rights-approved source URLs may be returned as playable links.
"""
from __future__ import annotations
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from video_catalog import CatalogError, _root, _artifact_id, read_evidence

ALLOWED_HOSTS = {"www.youtube.com", "youtube.com", "youtu.be", "www.vimeo.com",
                 "vimeo.com", "www.tiktok.com", "www.instagram.com"}
RIGHTS = {"owned", "licensed", "explicit_permission", "unknown", "restricted"}
MAX_REGISTRY_BYTES = 512 * 1024


def _file(root):
    base = _root(root)
    dest = base / ".video-evidence" / "sources.json"
    dest.parent.mkdir(exist_ok=True)
    if dest.is_symlink():
        raise CatalogError("Source registry must not be a symlink")
    return dest


def _url(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 2048:
        raise CatalogError("Invalid source URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port or (
        parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise CatalogError("Only supported HTTPS public video page hosts may be referenced")
    if not parsed.path or parsed.path == "/":
        raise CatalogError("A specific video page is required")
    # Do not allow arbitrary tracking parameters into generated citation links.
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, "", ""))


def _load(root):
    dest = _file(root)
    if not dest.exists():
        return {}
    if dest.stat().st_size > MAX_REGISTRY_BYTES:
        raise CatalogError("Source registry exceeds size budget")
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as e:
        raise CatalogError("Invalid source registry") from e
    if not isinstance(data, dict):
        raise CatalogError("Invalid source registry structure")
    return data


def register_source(root, *, source_id, revision, media_sha256,
                    title, rights, public_url=None, allow_public_citation=False):
    _artifact_id(source_id)
    if (not isinstance(revision, str) or not 1 <= len(revision) <= 80 or
        not isinstance(media_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", media_sha256) or
        not isinstance(title, str) or not 1 <= len(title.strip()) <= 200 or rights not in RIGHTS or
        type(allow_public_citation) is not bool):
        raise CatalogError("Invalid source registration fields")
    evidence = read_evidence(root, source_id)
    src = evidence["source"]
    if (revision != src["revision"] or media_sha256 != src["media_sha256"]):
        raise CatalogError("Source registration and evidence provenance differ")
    normalized = _url(public_url)
    if allow_public_citation and (rights not in {"owned", "licensed", "explicit_permission"} or not normalized):
        raise CatalogError("Public citation needs permission and a video page")
    entry = {"source_id":source_id,"revision":revision,"media_sha256":media_sha256,
             "title":title.strip(),"rights":rights,"public_url":normalized,
             "allow_public_citation":allow_public_citation}
    registry = _load(root)
    if source_id in registry:
        if registry[source_id] != entry:
            raise CatalogError("Existing source registration differs; no silent rights or URL changes")
        return {"status":"ALREADY_REGISTERED","source_id":source_id}
    if len(registry) >= 1000:
        raise CatalogError("Source registry is full")
    registry[source_id] = entry
    dest = _file(root)
    payload = json.dumps(registry,sort_keys=True,indent=2).encode("utf-8")
    if len(payload) > MAX_REGISTRY_BYTES:
        raise CatalogError("Source registry exceeds size budget")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=dest.parent,prefix=".source-",delete=False) as fd:
            temp = Path(fd.name)
            fd.write(payload)
        os.replace(temp,dest)
    finally:
        if temp is not None: temp.unlink(missing_ok=True)
    return {"status":"REGISTERED","source_id":source_id}


def source_reference(root, source_id, time_ms):
    _artifact_id(source_id)
    if type(time_ms) is not int or time_ms < 0:
        raise CatalogError("Invalid source timestamp")
    registry = _load(root)
    entry = registry.get(source_id)
    if entry is None:
        return {"source_id":source_id,"citation_status":"NO_APPROVED_PUBLIC_REFERENCE"}
    evidence = read_evidence(root,source_id)
    if (entry["media_sha256"] != evidence["source"]["media_sha256"] or
        entry["revision"] != evidence["source"]["revision"]):
        raise CatalogError("Registered source and indexed media mismatch")
    if not entry["allow_public_citation"] or entry["rights"] not in {"owned","licensed","explicit_permission"}:
        return {"source_id":source_id,"citation_status":"PRIVATE_OR_UNLICENSED"}
    url = _url(entry.get("public_url"))
    if not url:
        return {"source_id":source_id,"citation_status":"MISSING_PUBLIC_URL"}
    parsed = urlsplit(url)
    if parsed.hostname in {"youtu.be","www.youtube.com","youtube.com","vimeo.com","www.vimeo.com"}:
        separator = "&" if parsed.query else "?"
        url += separator + urlencode({"t":time_ms//1000})
        status = "TIMESTAMP_URL_CANDIDATE"
    else:
        # Do not invent timestamp syntax for arbitrary provider players.
        status = "PUBLIC_PAGE_NO_TIMED_DEEPLINK"
    return {"source_id":source_id,"revision":entry["revision"],
            "title":entry["title"],"url":url,"citation_status":status,
            "source_permissions":"DECLARED_NOT_INDEPENDENTLY_VERIFIED",
            "start_ms":time_ms}
