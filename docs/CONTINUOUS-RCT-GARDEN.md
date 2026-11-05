# Continuous RCT research growth

The earlier story counts verified components. They did not establish an
autonomous system that continually improves semantic grammar and activation.
This implementation connects the previously separate components into a durable
research loop; it does not establish mature semantic compression or AV1
superiority.

## What runs

`tools.activation_runtime.evolution.EvolutionGarden` owns a persistent sequence
of investigations in the existing append-only `Gardener` and Research Ledger.

1. Read earlier development failures, grammar programs, activation costs,
   dormant branches and the purpose-scoped research champion.
2. Ask a host-configured open-model Ollama endpoint for hypotheses and new
   paired grammar/activation programs. The model sees authorized training
   excerpts and development feedback, never evaluation content or paths.
3. Create a branch, fork, reopen a dormant parent, or synthesize two parents.
   Every candidate and counterexample remains in the tree.
4. Execute real encoding and activation in the existing syscall/resource
   sandbox. Compare candidate, current champion and untouched baseline on
   exactly the same source bytes and byte-exact purpose contract.
5. Retain content-addressed payloads, measured costs, source/code/runtime pins,
   test receipts, refusals and negative results. Ledger claims remain UNVERIFIED.
6. Advance a **research byte-cost champion** only for a strict improvement on
   the fresh evaluation cohort. Feed development findings into the next cycle.

The research champion is a versioned program plus activation plan and purpose
hash. It is not a production release, semantic ADMIT or scientific proof. Its
previous versions and experiments remain in the cycle journal and Garden.

## Grammar and activation are coupled

The first backend is a bounded reversible grammar, not a palette parameter
grid. Agents can learn named literal productions from training-source anchors
and compose them with delta, XOR, reversal, zlib and bzip2 rules. Names do not
authenticate semantic labels. Every decoded source/chunk is hash checked.

The same candidate specifies eager or on-demand chunk activation and chunk
size. Receipts record modules executed, productions actually materialized,
activation steps and timings. Different programs and activation plans create
different measured regimes. Unsupported executable operators are refused and
retained as research failures; arbitrary model-generated Python is never run.

This backend preserves meaning conservatively by preserving exact source
bytes. It does **not** infer scene graphs, invent executable operators, replace
canonical FF-RCT, or establish a mature purpose-selective semantic video codec.
Those are still research/integration work, not completed by this loop.

The configuration's `packspec` is a versioned **research objective contract**,
not a replacement for the existing compiled ConstraintIR, source authority or
signed release/admission pipeline. This first backend only accepts byte-exact
research objectives and always leaves QualityRag admission INCONCLUSIVE.

## AV1 floor and honest costs

With `baseline=AV1_PASSTHROUGH`, registration uses FFprobe to require actual AV1
input. The selected fallback is its original bytes with no added grammar
wrapper. Candidate packet size includes the complete grammar, chunk inventory,
hashes and residuals. A candidate is delivered only if its packet plus the
host-declared decoder-install bytes is strictly smaller. Unknown installation
cost forces untouched baseline delivery.

`decoder_install_bytes=0` is an explicit laboratory/preinstalled-runtime
assumption, not a measured claim about a new viewer. Set it to null when
unknown. Installation cost declarations are not independently authenticated.
AV1 decoder playback costs, device energy, monetary model/review costs and
population generalization are not established by these experiments. Provider
reported token/time counts, actual experiment wall time and activation costs
are retained; missing costs remain UNKNOWN. No full economic advantage is
asserted, and no production release is enabled.

## Growing without contaminating evaluation

Family/split declarations are host supplied. Identical bytes cannot cross
families/splits, and previously registered content cannot be relabeled after
restart. Each evaluation family is consumed once per frozen candidate batch.
Candidate and champion use the same current cohort; no cross-cohort score is
used as a matched comparison.

After fresh evaluation families are exhausted, development-only branches keep
growing within the budget. They cannot advance the champion. Continuous mode
reloads the host configuration between cycles, so newly authorized sources can
be added without deleting history. Declared families/rights references are not
independently verified corpus provenance or permission.

## Start on a research host

Supply a local workspace, an installed open model served by Ollama, and a
JSON configuration. Source paths must be absolute and host owned. Current
prototype limits are 64 sources, 262,144 bytes per source, four proposals per
cycle and eight typed operations per program.

```json
{
  "schema": "qualityrag.evolution-config/v1",
  "packspec": {
    "id": "exact-video",
    "revision": "v1",
    "purpose": "preserve-all-source-distinctions",
    "fidelity": "BYTE_EXACT",
    "baseline": "AV1_PASSTHROUGH",
    "decoder_install_bytes": null
  },
  "sources": [
    {"id":"train1","family":"scene1","split":"TRAIN","path":"/absolute/train-av1.mkv","rights_ref":"host-owned source"},
    {"id":"dev1","family":"scene2","split":"DEV","path":"/absolute/dev-av1.mkv","rights_ref":"host-owned source"},
    {"id":"eval1","family":"scene3","split":"EVALUATION","path":"/absolute/evaluation-av1.mkv","rights_ref":"host-owned source"}
  ],
  "max_candidates": 2
}
```

```bash
python -m tools.activation_runtime.evolution \
  --garden /absolute/workspace/gardens/research/events.sqlite \
  --config /absolute/research-config.json \
  --model YOUR_INSTALLED_OPEN_MODEL --continuous --work-limit 200

python -m tools.activation_runtime.evolution \
  --garden /absolute/workspace/gardens/research/events.sqlite --status
```

The existing service/console sees the same Garden database. Optional
`--public-contract-root /absolute/workspace/objects --tenant research` makes
only the purpose contract available to that tenant's existing source viewer.
Original sources, evaluation cases and detailed private receipts stay in the
worker's separate object store. Do not share a research database across tenants.
`gardener/evolution` is an authenticated, tenant-scoped read-only status route;
it does not let a web request start an agent or select a model endpoint.

The host authorizes sharing training excerpts with its configured model
endpoint. There is no automatic Claude/API-credit use, fake model fallback or
download of weights. A failed model request pauses with an explicit status.
An operator may use `--retry-provider`; that retry consumes additional durable
budget and reuses the same source snapshot. Restart does not reset spending.
Completed cycles are immutable; completed receipts survive a crash, while
interrupted unrecorded experiments are refused rather than silently repeated
as free work. Pending cycles require their original purpose and code pins.
Requests use a 45-second HTTP bound, a 65,536-byte planning-context bound and
explicit generation/context limits. Oversized or unfinished responses refuse
the cycle. The [Ollama chat protocol](https://docs.ollama.com/api/chat) supplies
the reported token/time fields; they are not independently measured USD costs.

## Evidence boundary

Tests cover multi-cycle growth, negative branches, reopening, synthesis,
research-champion retention, development-only growth, real AV1 fallback,
production/chunk round trips, scoped activation, cost-unknown fallback,
source/family leakage refusal, budget persistence and crash recovery.
The Ollama HTTP adapter is tested against a local protocol fixture. The
multi-generation proposer in tests is explicitly scripted, not a live model.
No installed Ollama/model service was available in the implementation host;
live autonomous research, long-horizon grammar improvement and representative
video gains remain **NOT VERIFIED**.

```bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_evolution.py' -v
```
