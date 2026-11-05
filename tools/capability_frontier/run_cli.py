"""Execute opt-in, no-tool API trials from a frozen research manifest."""
import argparse
import json
from pathlib import Path
from runner import OpenAICompatibleAdapter, run_manifest

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--endpoint", required=True, help="Trusted HTTPS /chat/completions endpoint")
    p.add_argument("--model", required=True)
    p.add_argument("--key-env", default="OPENAI_API_KEY")
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--input-price-microusd-per-million", type=int, required=True)
    p.add_argument("--output-price-microusd-per-million", type=int, required=True)
    a = p.parse_args()
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    adapter = OpenAICompatibleAdapter(
        endpoint=a.endpoint, model=a.model, api_key_env=a.key_env,
        input_microusd_per_million=a.input_price_microusd_per_million,
        output_microusd_per_million=a.output_price_microusd_per_million)
    def provisional_exact_audit(case, output):
        # This is only a provisional exact-answer comparator, never a
        # semantic verifier, source authenticity proof, or APX admission.
        return {"constraint_violations": int(output != case["expected"]),
                "auditor_ref": "LOCAL_PROVISIONAL_EXACT_MATCH"}
    outcome = run_manifest(manifest, adapter, audit=provisional_exact_audit, trials=a.trials)
    Path(a.output).write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
    print("Experiment:", outcome["report"]["execution_status"])
    print("Provisional holdout gains:", len(outcome["report"]["frontier_expansions"]))
    print("Warning: local exact matching is not independent semantic verification")

if __name__ == "__main__":
    main()
