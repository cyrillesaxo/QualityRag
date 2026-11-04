"""Transparent lifecycle scenarios and Pareto candidates, not observed savings."""
import math
from fractions import Fraction

COMPONENTS = ("compile", "encode", "residual", "model_distribution", "update",
              "storage", "bandwidth", "decode", "verification", "energy", "review")
COHORTS=("cold-new","frequent","smart-tv","mobile")
SCOPES=("fixed","per_title","per_install","per_update","baseline_per_view","candidate_per_view")


def _amount(value):
    """Use declared decimal spelling without implying measurement precision."""
    try:valid=type(value) in (int,float) and math.isfinite(value) and value>=0
    except OverflowError:valid=False
    if not valid:raise ValueError("Finite nonnegative numeric value required")
    return Fraction(str(value))


def _number(value):
    try:result=float(value)
    except OverflowError as exc:raise ValueError("Cost arithmetic exceeds finite output range") from exc
    if not math.isfinite(result):raise ValueError("Cost arithmetic exceeds finite output range")
    return result


def _bounds(lower,upper):
    """Round serialized endpoints outward; never narrow a declared interval."""
    result=[]
    for value,direction in ((lower,-math.inf),(upper,math.inf)):
        number=_number(value);rounded=Fraction(str(number))
        if (direction<0 and rounded>value) or (direction>0 and rounded<value):
            number=math.nextafter(number,direction)
            if not math.isfinite(number):raise ValueError("Cost interval exceeds finite output range")
        result.append(number)
    return {"lower":result[0],"upper":result[1]}


def _workloads(catalog_sizes,cohorts):
    if not isinstance(catalog_sizes,list) or not 1<=len(catalog_sizes)<=16 or any(type(n) is not int or not 1<=n<=2**63-1 for n in catalog_sizes):
        raise ValueError("Bounded positive integer catalog sizes required")
    if len(set(catalog_sizes))!=len(catalog_sizes):raise ValueError("Duplicate catalog size")
    if not isinstance(cohorts,dict) or set(cohorts)!=set(COHORTS):raise ValueError("All required viewer/device cohorts needed")
    for row in cohorts.values():
        if not isinstance(row,dict) or set(row)!={"installs","views","update_events"} or any(type(n) is not int or not 0<=n<=2**63-1 for n in row.values()):
            raise ValueError("Bounded integer cohort workload counts required")


def lifecycle(values):
    if not isinstance(values, dict) or set(values) != set(COMPONENTS):
        raise ValueError("Every lifecycle cost component must be declared")
    unknown, total, assumptions = [], Fraction(0), []
    for name in COMPONENTS:
        item = values[name]
        if not isinstance(item, dict) or set(item) != {"value", "evidence", "unit"} or item["unit"] != "USD":
            raise ValueError("Cost value, evidence classification and common currency required")
        value = item["value"]
        if not isinstance(item["evidence"],str) or item["evidence"] not in {"OBSERVED", "ASSUMED", "UNKNOWN"}:
            raise ValueError("Unknown cost evidence class")
        if item["evidence"] == "UNKNOWN":
            if value is not None:
                raise ValueError("Unknown costs must have null value")
            unknown.append(name)
        else:
            total += _amount(value)
            if item["evidence"] == "ASSUMED":
                assumptions.append(name)
    return {"total_usd": None if unknown else _number(total), "known_subtotal_usd": _number(total),
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
            _amount(row[k])
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
    if type(model_bytes) is not int or not 0<=model_bytes<=2**63-1:raise ValueError("Integer model byte count required")
    compile_usd,encode_usd_per_title,baseline_usd_per_view,candidate_usd_per_view,model_usd_per_install,update_usd_per_install,verification_usd_per_title=map(_amount,
        (compile_usd,encode_usd_per_title,baseline_usd_per_view,candidate_usd_per_view,model_usd_per_install,update_usd_per_install,verification_usd_per_title))
    _workloads(catalog_sizes,cohorts)
    rows=[]
    for titles in catalog_sizes:
        for name in COHORTS:
            cohort=cohorts[name]
            setup=compile_usd+titles*(encode_usd_per_title+verification_usd_per_title)+cohort["installs"]*model_usd_per_install+cohort["update_events"]*update_usd_per_install
            marginal=baseline_usd_per_view-candidate_usd_per_view
            crossover=None if marginal<=0 else math.floor(setup/marginal)+1
            rows.append({"cohort":name,"titles":titles,"baseline_usd":_number(cohort["views"]*baseline_usd_per_view),
                "candidate_usd":_number(setup+cohort["views"]*candidate_usd_per_view),"break_even_views":crossover,
                "model_distribution_bytes":model_bytes*cohort["installs"],
                "result":"NO_CROSSOVER" if crossover is None else "SCENARIO_CROSSOVER",
                "evidence":"ASSUMED_SCENARIO_NOT_MEASURED_SAVINGS"})
    return rows


def research_frontier(candidates):
    """All economic/resource dimensions are required; unknown energy is unqualified."""
    import math
    dimensions=("bytes","latency_ms","energy_j","total_usd")
    if not isinstance(candidates,list) or len(candidates)>128:raise ValueError("Finite candidate inventory required")
    valid=[];unqualified=[];seen=set()
    for row in candidates:
        if not isinstance(row,dict) or set(row)!={"id","fidelity_pass",*dimensions}:raise ValueError("All Pareto dimensions required")
        from .common import identity
        identity(row["id"])
        if row["id"] in seen:raise ValueError("Duplicate candidate ID")
        seen.add(row["id"])
        if type(row["fidelity_pass"]) is not bool:raise ValueError("Explicit fidelity result")
        for dimension in dimensions:
            if row[dimension] is not None:_amount(row[dimension])
        if not row["fidelity_pass"] or any(row[d] is None for d in dimensions):
            unqualified.append(row["id"]);continue
        valid.append(row)
    frontier=[a["id"] for a in valid if not any(all(b[d]<=a[d] for d in dimensions) and any(b[d]<a[d] for d in dimensions) for b in valid if b["id"]!=a["id"])]
    return {"frontier":sorted(frontier),"unqualified":sorted(unqualified),"can_promote":False,
            "promotion":"REQUIRES_INDEPENDENT_SIGNED_REVIEW"}


def _interval_group(values):
    if not isinstance(values,dict) or set(values)!=set(COMPONENTS):raise ValueError("Every lifecycle component must have an explicit interval")
    low=Fraction(0);high=Fraction(0);unknown=[];assumed=[]
    for name in COMPONENTS:
        row=values[name]
        if not isinstance(row,dict) or set(row)!={"lower","upper","evidence","unit"} or row["unit"]!="USD":raise ValueError("USD cost interval and evidence class required")
        if not isinstance(row["evidence"],str) or row["evidence"] not in {"OBSERVED","ASSUMED","UNKNOWN"}:raise ValueError("Unknown cost evidence class")
        if row["evidence"]=="UNKNOWN":
            if row["lower"] is not None or row["upper"] is not None:raise ValueError("Unknown interval endpoints must be null")
            unknown.append(name);continue
        lower=_amount(row["lower"]);upper=_amount(row["upper"])
        if lower>upper:raise ValueError("Reversed cost interval")
        low+=lower;high+=upper
        if row["evidence"]=="ASSUMED":assumed.append(name)
    return low,high,unknown,assumed


def lifecycle_interval(values):
    low,high,unknown,assumed=_interval_group(values)
    return {"schema":"qualityrag.lifecycle-interval/v1","total_usd":None if unknown else _bounds(low,high),
            "known_subtotal_usd":_bounds(low,high),"unknown_components":unknown,"assumed_components":assumed,
            "classification":"INCONCLUSIVE" if unknown else ("SCENARIO" if assumed else "OBSERVED_INPUT_RANGE_SUM"),
            "interpretation":"DETERMINISTIC_INPUT_BOUNDS_NOT_CONFIDENCE_INTERVALS",
            "evidence_authority":"CALLER_DECLARED_NOT_INDEPENDENTLY_AUTHENTICATED","economic_advantage":"NOT_ESTABLISHED"}


def catalog_uncertainty(groups,*,catalog_sizes,cohorts):
    """Linear cost scenarios with explicit deterministic bounds, never ROI forecasts."""
    if not isinstance(groups,dict) or set(groups)!=set(SCOPES):raise ValueError("All fixed, workload and per-view cost scopes required")
    _workloads(catalog_sizes,cohorts)
    intervals={scope:_interval_group(groups[scope]) for scope in SCOPES}
    unknown={scope:row[2] for scope,row in intervals.items() if row[2]}
    assumed={scope:row[3] for scope,row in intervals.items() if row[3]}
    rows=[]
    for titles in catalog_sizes:
        for name in COHORTS:
            cohort=cohorts[name]
            row={"cohort":name,"titles":titles,**cohort,"economic_advantage":"NOT_ESTABLISHED"}
            if unknown:
                rows.append({**row,"result":"INCONCLUSIVE","setup_usd":None,"baseline_usd":None,"candidate_usd":None,
                    "savings_usd":None,"earliest_crossover_views":None,"guaranteed_crossover_views":None,"at_declared_views":"UNKNOWN"})
                continue
            setup=[sum((intervals[scope][i]*multiplier for scope,multiplier in
                   (("fixed",1),("per_title",titles),("per_install",cohort["installs"]),("per_update",cohort["update_events"]))),Fraction(0)) for i in (0,1)]
            base=intervals["baseline_per_view"][:2];candidate=intervals["candidate_per_view"][:2]
            marginal=[base[0]-candidate[1],base[1]-candidate[0]]
            earliest=None if marginal[1]<=0 else math.floor(setup[0]/marginal[1])+1
            guaranteed=None if marginal[0]<=0 else math.floor(setup[1]/marginal[0])+1
            baseline=[cohort["views"]*v for v in base]
            current=[setup[i]+cohort["views"]*candidate[i] for i in (0,1)]
            savings=[baseline[0]-current[1],baseline[1]-current[0]]
            rows.append({**row,"setup_usd":_bounds(*setup),"baseline_usd":_bounds(*baseline),"candidate_usd":_bounds(*current),
                "savings_usd":_bounds(*savings),"earliest_crossover_views":earliest,"guaranteed_crossover_views":guaranteed,
                "result":"NO_CROSSOVER" if earliest is None else ("GUARANTEED_CROSSOVER_WITHIN_INPUT_BOUNDS" if guaranteed is not None else "POSSIBLE_CROSSOVER_ONLY"),
                "at_declared_views":"GUARANTEED_SAVINGS_WITHIN_INPUT_BOUNDS" if savings[0]>0 else ("NO_SAVINGS_WITHIN_INPUT_BOUNDS" if savings[1]<=0 else "UNCERTAIN")})
    return {"schema":"qualityrag.catalog-uncertainty/v1","rows":rows,"unknown_components":unknown,"assumed_components":assumed,
            "interpretation":"DETERMINISTIC_INPUT_BOUNDS_NOT_CONFIDENCE_INTERVALS","classification":"INCONCLUSIVE" if unknown else "SCENARIO_NOT_MEASURED_SAVINGS",
            "evidence_authority":"CALLER_DECLARED_NOT_INDEPENDENTLY_AUTHENTICATED",
            "economic_advantage":"NOT_ESTABLISHED","can_promote":False}
