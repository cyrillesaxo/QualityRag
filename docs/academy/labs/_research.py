"""Shared setup for the research-track labs: puts the Semantic Store prototypes on the path."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "semantic_store"))
