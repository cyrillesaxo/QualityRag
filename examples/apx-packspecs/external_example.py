"""Run all original-source-derived training cases with external PackSpec loading.

Does not implement the original APX PackSpec semantic machinery.
"""
import json
from pathlib import Path
from qualityrag import evaluate
from qualityrag.sources import from_properties

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
for scenario in data["scenarios"]:
    pack_file = ROOT / "policies" / (scenario["id"] + ".json")
    load_policy = from_properties({
        "qualityrag.packspec.source": "file",
        "qualityrag.packspec.path": str(pack_file),
    })
    for case in scenario["cases"]:
        result = evaluate(load_policy(), case["evidence"], as_of=data["as_of"])
        assert result["verdict"] == case["expected"], scenario["id"] + "/" + case["id"]
        print(scenario["id"], case["id"], result["verdict"])
