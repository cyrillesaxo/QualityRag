"""Receipt revalidation along the dependency frontier (US-083).

A gate receipt stays VALID while the governance it was issued under is unchanged. Activity
on other branches, or new evidence on the same branch, does not invalidate it. Change-impact
recall and false-invalidation rate are UNMEASURED.
"""
from __future__ import annotations


def receipt_status(tree, receipt):
    """VALID or STALE, with reasons. A stale receipt must not be used to answer."""
    state = tree.replay()
    node = state["branches"].get(receipt.get("branch"))
    reasons = []
    if node is None or not node["active"]:
        reasons.append("BRANCH_INACTIVE")
    else:
        if node["packspecs"][-1]["version"] != receipt.get("packspec_version"):
            reasons.append("GOVERNANCE_AMENDED")
        retired_then = {row["obligation_id"] for row in receipt.get("obligations", [])
                        if row["status"] == "NOT_APPLICABLE"}
        if set(node["superseded"]) != retired_then:
            reasons.append("OBLIGATION_RETIRED")
    if [s["turn_id"] for s in state["standing"]] != receipt.get("standing_rules", []):
        reasons.append("STANDING_RULES_CHANGED")
    return {"status": "STALE" if reasons else "VALID", "reasons": reasons,
            "branch": receipt.get("branch"), "issued_snapshot": receipt.get("snapshot"),
            "current_snapshot": state["head"]}


def dependents(tree, branch):
    """Merged branches that inherited this branch's governance, and whether it has moved on since."""
    state = tree.replay()
    if branch not in state["branches"]:
        raise ValueError("Unknown branch")
    current = state["branches"][branch]["packspecs"][-1]["version"]
    out = []
    for name, node in state["branches"].items():
        parent = node["packspecs"][0]["parent_packspec"]
        if parent and parent["branch"] == branch:
            out.append({"branch": name, "active": node["active"],
                        "inherited_version": parent["version"], "parent_version": current,
                        # A fork is a snapshot: later parent amendments are not inherited silently.
                        "parent_advanced": current != parent["version"]})
    return out
