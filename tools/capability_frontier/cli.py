"""CLI to evaluate independently audited capability runs."""
import argparse
import json
from pathlib import Path
from frontier import evaluate

def main():
    parser = argparse.ArgumentParser(description="Evaluate paired capability-frontier runs")
    for name in ("cases", "runs", "budget", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--min-trials", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    receipt = evaluate(load(args.cases), load(args.runs),
                       budget=load(args.budget),
                       min_trials=args.min_trials,
                       success_threshold=args.threshold)
    Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("Held-out:", receipt["holdout_cases"],
          "Potential expansion:", len(receipt["frontier_expansions"]),
          "Regressions:", len(receipt["regressions"]))
    print("CAUTION: upstream measurements and audit provenance must be independently verified")

if __name__ == "__main__":
    main()
