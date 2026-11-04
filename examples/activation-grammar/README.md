# Synthetic video fidelity counterexample

The fixture `video.json` is **not compressed video**. Its declared byte counts and activation timings are synthetic. It shows why the smallest payload does not necessarily satisfy a PackSpec-like exact-information contract.

Run from repository root:

```bash
PYTHONPATH=tools/semantic_store python - <<'PY'
import json
from activation_constraints import evaluate
with open('examples/activation-grammar/video.json') as f:
    fxt = json.load(f)
result = evaluate(fxt['grammar'], fxt['contract'], fxt['observations'],
    max_activation_ms=25, max_model_bytes=600000000,
    baseline_regime='av1-reference')
for r in result['regimes']:
    print(r['regime'],r['finite_constraint_result'],r['violations'],r['unresolved'])
print('candidate:',result['selected_candidate'])
print('admission:',result['qualityrag_admission'])
PY
```

The **generative** regime is UNSAT for this task: it does not declare exact preservation of subtitles and license plates. The **generative-with-residuals** candidate declares preservation but its model cost is 500 MB, so a simple non-amortized `payload_bytes + model_bytes` estimate favors the AV1 reference (all numeric values are assumptions, not measured comparisons). This is a warning against claiming compression gains before measuring distribution and amortization.

The same fixture with `max_model_bytes=100000000` rejects both generative alternatives on a model-size budget. No real video is decoded; the exact-field claims have not been independently verified. The output is always `qualityrag_admission=INCONCLUSIVE`.
