"""Validate inventory coverage and fingerprints; never self-certify completion."""
import json
from pathlib import Path
import re
from hashlib import sha256


def audit(root=None):
    root = Path(__file__).resolve().parents[2] if root is None else Path(root)
    inventory = json.loads((root / "tools/activation_runtime/capabilities.json").read_text())
    stories = inventory["stories"]
    wanted = {"US-"+str(n).zfill(3) for n in range(1,52)}
    actual = [x["story_id"] for x in stories]
    if len(actual) != 51 or len(set(actual)) != 51 or set(actual) != wanted:
        raise ValueError("Missing or duplicate story coverage")
    declared = set("US-"+x for x in re.findall(r"\*\*US-(\d{3}) ·", (root / "FR.MD").read_text()))
    if declared != wanted:
        raise ValueError("Inventory differs from FR.MD")
    for item in stories:
        if item["status"] not in {"PARTIAL", "NOT_STARTED", "BLOCKED"}:
            # This local checker is deliberately unable to verify merges or independent
            # scientific acceptance. Such a status needs a separate trusted verifier.
            raise ValueError("Unverified completion/status claim")
        if not item["remaining"].strip():
            raise ValueError("Missing acceptance limitations")
        for module in item["modules"]:
            path = (root / module["path"]).resolve()
            if root.resolve() not in path.parents or sha256(path.read_bytes()).hexdigest() != module["sha256"]:
                raise ValueError("Missing or altered implementation evidence")
    return {"stories": 51, "done": 0,
            "counts": {s:sum(x["status"] == s for x in stories) for s in ("PARTIAL","NOT_STARTED","BLOCKED")},
            "independent_validation": "NOT_ESTABLISHED"}


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
