"""Transparent lifecycle scenarios and Pareto candidates, not observed savings."""
import math

COMPONENTS = ("compile", "encode", "residual", "model_distribution", "update",
              "storage", "bandwidth", "decode", "verification", "energy", "review")


def lifecycle(values):
    if not isinstance(values, dict) or set(values) != set(COMPONENTS):
        raise ValueError("Every lifecycle cost component must be declared")
    unknown, total, assumptions = [], 0.0, []
    for name in COMPONENTS:
        item = values[name]
        if not isinstance(item, dict) or set(item) != {"value", "evidence", "unit"} or item["unit"] != "USD":
            raise ValueError("Cost value, evidence classification and common currency required")
        value = item["value"]
        if item["evidence"] not in {"OBSERVED", "ASSUMED", "UNKNOWN"}:
            raise ValueError("Unknown cost evidence class")
        if item["evidence"] == "UNKNOWN":
            if value is not None:
                raise ValueError("Unknown costs must have null value")
            unknown.append(name)
        else:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Finite nonnegative cost required")
            total += value
            if item["evidence"] == "ASSUMED":
                assumptions.append(name)
    return {"total_usd": None if unknown else total, "known_subtotal_usd": total,
            "unknown_components": unknown, "assumed_components": assumptions,
            "classification": "INCONCLUSIVE" if unknown else ("SCENARIO" if assumptions else "OBSERVED_INPUT_SUM"),
            "economic_advantage": "NOT_ESTABLISHED"}


def pareto(candidates):
    """Minimize bytes, latency and energy only after all declared fidelity checks pass."""
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 128:
        raise ValueError("Bounded candidate set required")
    seen = set()
    eligible = []
    for row in candidates:
        if not isinstance(row, dict) or set(row) != {"id", "bytes", "latency_ms", "energy_j", "fidelity_pass"}:
            raise ValueError("Explicit Pareto dimensions required")
        from .common import identity
        identity(row["id"])
        if row["id"] in seen or type(row["fidelity_pass"]) is not bool:
            raise ValueError("Duplicate candidate or invalid fidelity")
        seen.add(row["id"])
        for k in ("bytes", "latency_ms", "energy_j"):
            if type(row[k]) not in (int, float) or not math.isfinite(row[k]) or row[k] < 0:
                raise ValueError("Invalid measured dimension")
        if row["fidelity_pass"]:
            eligible.append(row)
    dimensions = ("bytes", "latency_ms", "energy_j")
    return sorted(a["id"] for a in eligible if not any(
        all(b[k] <= a[k] for k in dimensions) and any(b[k] < a[k] for k in dimensions)
        for b in eligible if b["id"] != a["id"]))


def catalog_scenarios(*,model_bytes,compile_usd,encode_usd_per_title,baseline_usd_per_view,
                      candidate_usd_per_view,model_usd_per_install,update_usd_per_install,
                      verification_usd_per_title,catalog_sizes,cohorts):
    """Scenario break-even, with cold install/update costs assigned to each cohort."""
    import math
    numeric=(model_bytes,compile_usd,encode_usd_per_title,baseline_usd_per_view,
             candidate_usd_per_view,model_usd_per_install,update_usd_per_install,verification_usd_per_title)
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in numeric):
        raise ValueError("Complete nonnegative lifecycle scenario inputs required")
    if not isinstance(catalog_sizes,list) or not 1<=len(catalog_sizes)<=16 or not isinstance(cohorts,dict) or set(cohorts)!={"cold-new","frequent","smart-tv","mobile"}:
        raise ValueError("All required viewer/device cohorts needed")
    rows=[]
    for titles in catalog_sizes:
        if type(titles) is not int or titles<1:raise ValueError("Positive catalog size")
        for name,cohort in cohorts.items():
            if set(cohort)!={"installs","views","update_events"} or any(type(v) is not int or v<0 for v in cohort.values()):
                raise ValueError("Explicit cohort workload counts required")
            setup=compile_usd+titles*(encode_usd_per_title+verification_usd_per_title)+cohort["installs"]*model_usd_per_install+cohort["update_events"]*update_usd_per_install
            marginal=baseline_usd_per_view-candidate_usd_per_view
            crossover=None if marginal<=0 else math.floor(setup/marginal)+1
            rows.append({"cohort":name,"titles":titles,"baseline_usd":cohort["views"]*baseline_usd_per_view,
                "candidate_usd":setup+cohort["views"]*candidate_usd_per_view,"break_even_views":crossover,
                "model_distribution_bytes":model_bytes*cohort["installs"],
                "result":"NO_CROSSOVER" if crossover is None else "SCENARIO_CROSSOVER",
                "evidence":"ASSUMED_SCENARIO_NOT_MEASURED_SAVINGS"})
    return rows


def research_frontier(candidates):
    """All economic/resource dimensions are required; unknown energy is unqualified."""
    import math
    dimensions=("bytes","latency_ms","energy_j","total_usd")
    if not isinstance(candidates,list) or len(candidates)>128:raise ValueError("Finite candidate inventory required")
    valid=[];unqualified=[]
    for row in candidates:
        if set(row)!={"id","fidelity_pass",*dimensions}:raise ValueError("All Pareto dimensions required")
        from .common import identity
        identity(row["id"])
        if type(row["fidelity_pass"]) is not bool:raise ValueError("Explicit fidelity result")
        if not row["fidelity_pass"] or any(row[d] is None for d in dimensions):
            unqualified.append(row["id"]);continue
        if any(type(row[d]) not in (int,float) or not math.isfinite(row[d]) or row[d]<0 for d in dimensions):
            raise ValueError("Invalid measured dimension")
        valid.append(row)
    frontier=[a["id"] for a in valid if not any(all(b[d]<=a[d] for d in dimensions) and any(b[d]<a[d] for d in dimensions) for b in valid if b["id"]!=a["id"])]
    return {"frontier":sorted(frontier),"unqualified":sorted(unqualified),"can_promote":False,
            "promotion":"REQUIRES_INDEPENDENT_SIGNED_REVIEW"}
