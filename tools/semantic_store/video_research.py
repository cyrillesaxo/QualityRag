"""Source-bound, cross-modal retrieval bundles for governed video research.

This combines nearby *candidate* witnesses; proximity is NOT corroboration.
Search remains lexical until a separately evaluated semantic index is added.
"""
from __future__ import annotations

from video_catalog import CatalogError, search_evidence, read_evidence
from video_sources import source_reference

MAX_WINDOW_MS = 60000
MAX_RESULTS = 20


def _reference(source, witness):
    span = witness["interval"]
    return {
        "source_id": source["source_id"],
        "revision": source["revision"],
        "media_sha256": source["media_sha256"],
        "witness_id": witness["id"],
        "modality": witness["modality"],
        "start_ms": span["start_ms"],
        "end_ms": span["end_ms"],
        "frame_sha256": witness.get("frame_sha256"),
        "text": witness["text"][:1000],
        "admission": "UNVERIFIED_OBSERVATION",
    }


def _near(a, b, radius):
    """Distance between two closed time intervals in milliseconds."""
    if a["end_ms"] < b["start_ms"]:
        return b["start_ms"] - a["end_ms"] <= radius
    if b["end_ms"] < a["start_ms"]:
        return a["start_ms"] - b["end_ms"] <= radius
    return True


def research_video_evidence(root: str, query: str, *, intent: str = "cross_modal",
                            limit: int = 8, window_ms: int = 3000,
                            source_ids: frozenset[str] | None = None) -> dict:
    if intent not in ("cross_modal", "visual", "spoken"):
        raise CatalogError("Intent must be cross_modal, visual or spoken")
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise CatalogError("Invalid research limit")
    if type(window_ms) is not int or not 0 <= window_ms <= MAX_WINDOW_MS:
        raise CatalogError("Invalid temporal window")
    # Current lexical search returns at most 30 hits; do not claim full recall.
    modality = {"cross_modal": "all", "visual": "video", "spoken": "audio"}[intent]
    result = search_evidence(root, query, modality=modality, limit=30, source_ids=source_ids)
    bundles = []
    cache = {}
    for hit in result["results"]:
        source_id = hit["source_id"]
        if source_id not in cache:
            cache[source_id] = read_evidence(root, source_id)
        artifact = cache[source_id]
        source = artifact["source"]
        anchor = next((w for w in artifact["witnesses"] if w["id"] == hit["witness_id"]), None)
        if anchor is None:
            raise CatalogError("Search result refers to missing witness")
        neighbors = [w for w in artifact["witnesses"]
                     if w["id"] != anchor["id"] and
                     _near(anchor["interval"], w["interval"], window_ms)]
        # Surface nearby audio and visual witnesses. Nearby testimony is
        # not automatically independent or consistent with the anchor.
        neighbors.sort(key=lambda w: (abs(w["interval"]["start_ms"] -
                                           anchor["interval"]["start_ms"]), w["id"]))
        neighbors = neighbors[:12]
        witness_refs = [_reference(source, anchor)] + [
            _reference(source, w) for w in neighbors]
        seen_modalities = {w["modality"] for w in witness_refs}
        has_visual = bool(seen_modalities & {"video", "ocr"})
        has_spoken = "audio" in seen_modalities
        bundles.append({
            "anchor": witness_refs[0],
            "nearby_witnesses": witness_refs[1:],
            "observed_modalities": sorted(seen_modalities),
            "visual_evidence_present": has_visual,
            "speech_evidence_present": has_spoken,
            "co_observation": "PRESENT_UNVERIFIED" if has_visual and has_spoken
                              else "SINGLE_MODALITY_OR_MISSING",
            "speech_visual_agreement": "NOT_EVALUATED",
            "physical_action_verified": False,
            "source_time_ref": {
                "source_id": source_id, "revision": source["revision"],
                "start_ms": anchor["interval"]["start_ms"],
                "end_ms": anchor["interval"]["end_ms"],
                "media_sha256": source["media_sha256"],
            },
            "source_reference": source_reference(root, source_id, anchor["interval"]["start_ms"]),
            "admission": "CANDIDATE_REQUIRES_REVIEW",
        })
        if len(bundles) >= limit:
            break
    if not bundles:
        coverage = "NO_MATCHES_IN_INDEX_NOT_PROOF_OF_ABSENCE"
    elif any(b["co_observation"] == "PRESENT_UNVERIFIED" for b in bundles):
        coverage = "CROSS_MODAL_CANDIDATES_FOUND_UNVERIFIED"
    else:
        coverage = "NO_CROSS_MODAL_CORROBORATION_ESTABLISHED"
    return {
        "schema": "qualityrag.video-research-bundles/v1",
        "query": query, "intent": intent,
        "retrieval": "BOUNDED_LEXICAL_CANDIDATES",
        "sampling_limit": "First 30 lexical matches; not comprehensive video coverage",
        "temporal_window_ms": window_ms,
        "bundles": bundles,
        "coverage": coverage,
        "governance": {
            "packspec": "NOT_BOUND",
            "conclusion": "INCONCLUSIVE",
            "missing_evidence_must_not_be_interpreted_as_absence": True,
            "audio_visual_proximity_is_not_confirmation": True,
        }
    }
