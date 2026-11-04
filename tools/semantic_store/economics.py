"""FF-RCT-inspired lifecycle accounting for paired retrieval (v0.8).

Consumes an actual v0.7 measurement receipt. Computes explicitly HYPOTHETICAL
repeat-query cost under a transparent workload/price scenario, and a
mathematical amortization boundary. It does not pretend synthetic fixture runs
are real performance evidence, does not treat filenames as equivalent visual
capability, and refuses a break-even claim when inputs are missing/ambiguous.
"""
from __future__ import annotations

import math
from typing import Any

from semantic_codex import CodexError
from store import digest

SCHEMA = "qualityrag.semantic-economics/v0.8"
MAX_QUERIES = 20


def _finite_nonnegative(x: Any, name: str) -> float:
    if type(x) not in (int,float) or not math.isfinite(x) or x < 0:
        raise CodexError(f"{name} must be a finite nonnegative number")
    return float(x)


def _positive_count(x: Any, name: str, cap: int) -> int:
    if type(x) is not int or not 0 <= x <= cap:
        raise CodexError(f"{name} must be an integer in 0..{cap}")
    return x


def evaluate_lifecycle(receipt: dict, *, repetitions_per_query: int,
                       changed_sources: int,
                       baseline_update_ms_per_source: float | None = None,
                       visual_update_ms_per_source: float | None = None,
                       baseline_storage_bytes: int | None = None,
                       visual_storage_bytes: int | None = None,
                       baseline_verification_ms: float | None = None,
                       visual_verification_ms: float | None = None,
                       price_per_cpu_second: float | None = None,
                       price_per_byte_month: float | None = None,
                       retention_months: float | None = None) -> dict:
    """Account for observed and supplied components, with explicit unknowns.

    A break-even query count is available ONLY when:
      1. update, verification, storage and prices are provided,
      2. the measured average semantic query is strictly faster than baseline,
      3. all timing measurements refer to the same workload/hardware as inputs.
    Even then, break-even is a *scenario calculation*, not observed savings.
    """
    if (not isinstance(receipt,dict) or
            receipt.get("schema")!="qualityrag.paired-visual-benchmark/v0.7"
            or receipt.get("admission")!="INCONCLUSIVE"
            or receipt.get("total_cost_comparison")!="NOT_ESTABLISHED"):
        raise CodexError("Expected an unadmitted v0.7 paired benchmark receipt")
    q=receipt.get("query_count")
    n=receipt.get("file_count")
    if (type(q) is not int or not 1<=q<=MAX_QUERIES or
            type(n) is not int or not 2<=n<=50):
        raise CodexError("Invalid finite benchmark dimensions")
    repetitions=_positive_count(repetitions_per_query,"repetitions_per_query",1_000_000)
    changed=_positive_count(changed_sources,"changed_sources",n)
    timings=receipt.get("timings")
    if (not isinstance(timings,dict) or timings.get("method")!="WALL_CLOCK_NON_ISOLATED_ONE_RUN"
            or timings.get("model_initialization_included") is not False
            or not isinstance(timings.get("queries"),list)
            or len(timings["queries"])!=q):
        raise CodexError("Unmeasured or mismatched query timing receipts")
    baseline_index=_finite_nonnegative(timings.get("directory_index_ms"),"baseline index time")
    additional_index=_finite_nonnegative(timings.get("visual_index_ms"),"visual index time")
    lexical=[]
    visual=[]
    seen=set()
    for item in timings["queries"]:
        if not isinstance(item,dict) or not isinstance(item.get("query_id"),str):
            raise CodexError("Invalid query timing")
        if item["query_id"] in seen:
            raise CodexError("Duplicate query timing")
        seen.add(item["query_id"])
        lexical.append(_finite_nonnegative(item.get("filename_lexical_ms"),"lexical query time"))
        visual.append(_finite_nonnegative(item.get("visual_query_ms"),"visual query time"))
    if seen != {m.get("query_id") for m in receipt.get("baseline_metrics",[])}:
        raise CodexError("Query timings do not align with the benchmark")
    if seen != {m.get("query_id") for m in receipt.get("visual_metrics",[])}:
        raise CodexError("Visual quality/timing mismatch")

    # Unknown extras must remain UNKNOWN and not silently become zero.
    provided=(baseline_update_ms_per_source, visual_update_ms_per_source,
              baseline_storage_bytes,visual_storage_bytes,
              baseline_verification_ms,visual_verification_ms,
              price_per_cpu_second,price_per_byte_month,retention_months)
    names=("baseline_update_ms_per_source","visual_update_ms_per_source",
           "baseline_storage_bytes","visual_storage_bytes",
           "baseline_verification_ms","visual_verification_ms",
           "price_per_cpu_second","price_per_byte_month","retention_months")
    values={}
    for key,val in zip(names,provided):
        values[key]=None if val is None else _finite_nonnegative(val,key)
    for key in ("baseline_storage_bytes","visual_storage_bytes"):
        original=values[key]
        if original is not None and (type(provided[names.index(key)]) is not int):
            raise CodexError("Storage inputs must be measured integer bytes")

    # 'visual' arm includes the SAME directory index plus incremental vectors.
    # Query projection is an explicit workload scenario, not a repeat experiment.
    observed={
        "baseline_initial_index_ms":baseline_index,
        "visual_initial_index_ms":baseline_index+additional_index,
        "baseline_query_ms_one_sweep":sum(lexical),
        "visual_query_ms_one_sweep":sum(visual),
        "per_query_samples":q,
        "model_load_cost":"NOT_MEASURED",
    }
    modeled={
        "query_executions":repetitions*q,
        "baseline_query_cpu_ms_estimate":sum(lexical)*repetitions,
        "visual_query_cpu_ms_estimate":sum(visual)*repetitions,
        "baseline_total_known_ms_estimate":baseline_index+sum(lexical)*repetitions,
        "visual_total_known_ms_estimate":baseline_index+additional_index+sum(visual)*repetitions,
        "update_cost":"UNKNOWN",
        "verification_cost":"UNKNOWN",
        "storage_cost":"UNKNOWN",
        "total_lifecycle_cost":"UNKNOWN",
    }
    complete=all(v is not None for v in values.values())
    break_even=None
    if complete:
        base_ms=(baseline_index+changed*values["baseline_update_ms_per_source"]
                 +values["baseline_verification_ms"])
        vision_ms=(baseline_index+additional_index
                   +changed*values["visual_update_ms_per_source"]
                   +values["visual_verification_ms"])
        baseline_cpu_ms=base_ms+sum(lexical)*repetitions
        visual_cpu_ms=vision_ms+sum(visual)*repetitions
        storage_base=values["baseline_storage_bytes"]*values["retention_months"]*values["price_per_byte_month"]
        storage_visual=values["visual_storage_bytes"]*values["retention_months"]*values["price_per_byte_month"]
        per_ms=values["price_per_cpu_second"]/1000
        total_base=baseline_cpu_ms*per_ms+storage_base
        total_vision=visual_cpu_ms*per_ms+storage_visual
        modeled.update({
            "update_cost":{"baseline_ms":changed*values["baseline_update_ms_per_source"],
                           "visual_ms":changed*values["visual_update_ms_per_source"]},
            "verification_cost":{"baseline_ms":values["baseline_verification_ms"],
                                 "visual_ms":values["visual_verification_ms"]},
            "storage_cost":{"baseline_currency":storage_base,"visual_currency":storage_visual},
            "total_lifecycle_cost":{"baseline_currency":total_base,"visual_currency":total_vision,
                                    "difference_visual_minus_baseline_currency":total_vision-total_base},
        })
        # Calculate generalized query count for same observed mean per-query
        # without projecting its sampling variance away.
        per_query_delta=(sum(lexical)-sum(visual))/q*per_ms
        fixed_delta=((vision_ms-base_ms)*per_ms + storage_visual-storage_base)
        if per_query_delta>0:
            break_even={"query_executions_required":
                        max(0,math.ceil(max(0,fixed_delta)/per_query_delta)),
                        "meaning":"MODELED_AMORTIZATION_ONLY_NO_PERFORMANCE_GUARANTEE"}
        else:
            break_even={"query_executions_required":None,
                        "reason":"VISUAL_QUERY_NOT_CHEAPER_UNDER_MEASURED_TIMINGS"}
    else:
        break_even={"query_executions_required":None,
                    "reason":"MISSING_UPDATE_STORAGE_VERIFICATION_OR_PRICE_INPUTS"}

    return {
        "schema":SCHEMA,"receipt_fingerprint":digest(receipt),
        "model_id":receipt.get("model_id"),
        "input_provenance":"V07_OBSERVED_WALL_CLOCK_PLUS_CALLER_SUPPLIED_SCENARIO",
        "workload":{"repetitions_per_query":repetitions,
                    "changed_sources":changed,"retention_months":values["retention_months"]},
        "observed_single_run":observed,
        "modeled_repeat_workload":modeled,
        "break_even":break_even,
        "unknown_costs":[k for k,v in values.items() if v is None],
        "semantic_parity":"NOT_ESTABLISHED_FILENAME_BASELINE_HAS_DIFFERENT_CAPABILITIES",
        "model_initialization_cost":"NOT_MEASURED",
        "network_and_energy_cost":"NOT_MEASURED",
        "source_preservation":"NOT_VERIFIED",
        "source_authenticity":"UNVERIFIED",
        "generalization":"UNMEASURED",
        "admission":"INCONCLUSIVE",
        "can_generate":False,
    }
