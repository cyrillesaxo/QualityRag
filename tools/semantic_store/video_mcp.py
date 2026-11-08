"""Prototype MCP interface to QualityRAG's allowlisted local video catalog.

Run over stdio for local development only. Remote deployment requires a
separate authenticated service, tenant isolation and sandboxed model workers.
No external social-media URL ingestion is provided by this server.
"""
from __future__ import annotations

import os
from pathlib import Path

from video_research import research_video_evidence
from video_hybrid import search_hybrid, local_encoder
from video_catalog import (
    analyze_authorized_media, read_evidence, search_evidence, _root
)


def configured_root() -> str:
    value = os.environ.get("QUALITYRAG_VIDEO_ROOT")
    if not value:
        raise RuntimeError("Set QUALITYRAG_VIDEO_ROOT to an authorized local media directory")
    return str(_root(value))


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install mcp Python SDK to enable the MCP adapter") from exc
    server = FastMCP("QualityRAG Video Evidence")

    @server.tool()
    def search_video_evidence(query: str, modality: str = "all", limit: int = 10) -> dict:
        """Search approved video/audio observations with source IDs and time spans.
        Returns candidate/unverified matches, not verified claims or an answer."""
        return search_evidence(configured_root(), query, modality=modality, limit=limit)

    @server.tool()
    def research_video_question(query: str, intent: str = "cross_modal",
                                limit: int = 8, window_ms: int = 3000) -> dict:
        """Retrieve timestamp-cited speech and visual evidence candidates.

        Nearby visual observations do not verify speech, and missing matches
        never imply an absent action. Returns no synthesized truth verdict.
        """
        return research_video_evidence(
            configured_root(), query, intent=intent,
            limit=limit, window_ms=window_ms)

    @server.tool()
    def hybrid_search_video(query: str, limit: int = 10,
                            lexical_weight: float = 0.5) -> dict:
        """Search locally indexed authorized witness text using lexical+dense relevance.

        Requires an operator-built, provenance-checked index and local model.
        Embedding similarity never verifies visual observations or spoken facts.
        """
        model_dir = os.environ.get("QUALITYRAG_VIDEO_EMBED_MODEL_DIR")
        model_id = os.environ.get("QUALITYRAG_VIDEO_EMBED_MODEL_ID")
        if not model_dir or not model_id:
            raise RuntimeError("Operator must configure local embedding model and model ID")
        return search_hybrid(
            configured_root(), query, embedder=local_encoder(model_dir),
            model_id=model_id,limit=limit,lexical_weight=lexical_weight)

    @server.tool()
    def inspect_video_evidence(source_id: str) -> dict:
        """Read a hashed video evidence artifact and unresolved provenance states."""
        return read_evidence(configured_root(), source_id)

    @server.tool()
    def analyze_local_video(relative_path: str, source_id: str,
                            revision: str = "r1", asr_model: str = "",
                            vision_model: str = "", interval_ms: int = 5000,
                            max_frames: int = 60) -> dict:
        """Analyze an already-authorized local media file within an allowlisted root.

        This may load explicitly selected local ASR or Ollama model weights.
        There is no YouTube downloader, general web crawler, or auto-ingestion.
        """
        return analyze_authorized_media(
            configured_root(), relative_path, source_id=source_id,
            revision=revision, asr_model=asr_model or None,
            vision_model=vision_model or None,
            interval_ms=interval_ms, max_frames=max_frames)

    return server


if __name__ == "__main__":
    create_server().run()
