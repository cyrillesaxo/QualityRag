"""Source-to-receipt integration with existing PackSpec and typed RCT code."""
from __future__ import annotations

import copy
import csv
from io import StringIO
from pathlib import Path
import sys
from time import perf_counter_ns

from .common import canonical, fingerprint, strict_json
from .artifacts import verify_manifest
from .contracts import validate

TOOLS = Path(__file__).resolve().parents[1]
for directory in ("packspec_compiler", "semantic_store"):
    path = str(TOOLS / directory)
    if path not in sys.path:
        sys.path.insert(0, path)
from finite_activation import encode, execute, digest
from rct_typed_grammar import induce_typed_rule, validate_typed_rule, compile_typed_lens
from rct_packspec_bridge import bind_candidate, evaluate_bound_lens


def ingest_csv(raw):
    """Exact original custody plus CSV records with physical line ranges.

    No SQL execution, inferred numeric conversion, or duplicate column merging.
    """
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 65536:
        raise ValueError("Bounded CSV bytes required")
    reader = csv.reader(StringIO(raw.decode("utf-8"), newline=""), strict=True)
    header = next(reader, None)
    if not header or len(header) > 128 or len(set(header)) != len(header) or any(not k for k in header):
        raise ValueError("Unique nonempty CSV columns required")
    records = []
    previous_line = reader.line_num
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError("Malformed CSV") from exc
    # Read again to retain physical line locations, including quoted newlines.
    reader = csv.reader(StringIO(raw.decode("utf-8"), newline=""), strict=True)
    next(reader)
    for index, row in enumerate(reader):
        if len(records) >= 1024 or len(row) != len(header):
            raise ValueError("CSV row budget or shape violation")
        records.append({"row": index + 1, "line_start": previous_line + 1,
                        "line_end": reader.line_num, "fields": dict(zip(header, row))})
        previous_line = reader.line_num
    return {"schema": "qualityrag.csv-source/v1",
            "source_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "columns": header, "records": records, "normalization": "NONE",
            "unsupported_structure": "CSV_ONLY"}


def activate_signed(raw, artifact, *, signed_manifest, trusted_keys, store,
                    tenant, minimum_sequence, ir, witnesses, as_of):
    """Signed compatibility before any transition; no semantic self-approval."""
    validate("transform", artifact)
    validate("packspec", ir)
    source_sha = __import__("hashlib").sha256(raw).hexdigest()
    artifact_sha = fingerprint(artifact)
    compatibility = verify_manifest(
        signed_manifest, trusted_keys, tenant=tenant, policy_ir_sha256=ir["ir_sha256"],
        source_sha256=source_sha, artifact_sha256=artifact_sha,
        minimum_sequence=minimum_sequence, as_of=as_of, store=store)
    if store.get(source_sha) != raw or strict_json(store.get(artifact_sha)) != artifact:
        raise ValueError("Custody mismatch")
    receipt = execute(raw, artifact, expected_artifact_sha256=digest(artifact),
                      ir=ir, witnesses=witnesses, as_of=as_of)
    receipt["compatibility"] = compatibility
    validate("receipt", receipt)
    return receipt


COMPILER_VERSION = "rct-typed-v1.4"


class RCTCache:
    """Host-local compiled decision cache; changing any input invalidates reuse."""
    def __init__(self):
        self.entries = {}
        self.hits = 0

    def evaluate(self, training, labels, heldout, heldout_labels, grammar, ir, *,
                 purpose, witnesses, as_of):
        inputs = {"training": fingerprint(training), "labels": fingerprint(labels),
                  "grammar": fingerprint(grammar), "ir": fingerprint(ir)}
        key = fingerprint({"training": training, "labels": labels, "grammar": grammar,
                           "ir": ir, "compiler": COMPILER_VERSION})
        start = perf_counter_ns()
        hit = key in self.entries
        if hit:
            self.hits += 1
            rule = copy.deepcopy(self.entries[key])
        else:
            rule = induce_typed_rule(training, labels, grammar)
            if len(self.entries) >= 32:
                self.entries.pop(next(iter(self.entries)))
            self.entries[key] = copy.deepcopy(rule)
        compile_ns = perf_counter_ns() - start
        receipt = {"schema": "qualityrag.activation-rct/v1", "rule": rule,
                   "cache_key": key, "cache_hit": hit, "cache_hits_total": self.hits,
                   "compiler_version": COMPILER_VERSION, "input_fingerprints": inputs,
                   "compiled_bytes": len(canonical(rule)), "lookup_or_compile_ns": compile_ns,
                   "qualityrag_admission": "INCONCLUSIVE", "can_generate": False}
        if rule["status"] != "CANDIDATE":
            receipt["finite_constraint_result"] = "UNKNOWN"
            return receipt
        assessment = validate_typed_rule(training, rule, heldout, heldout_labels, grammar)
        lens = compile_typed_lens(heldout, rule=rule, assessment=assessment, grammar=grammar,
                                  lens_id="activation-rct", purpose=purpose)
        binding = bind_candidate(lens, ir, purpose=purpose)
        gate = evaluate_bound_lens(lens, ir, binding, witnesses, {}, as_of)
        receipt.update(assessment=assessment, binding=binding, gate=gate,
                       finite_constraint_result=assessment["finite_graph_verdict"])
        return receipt
