# QualityRag activation research runtime

This is an executable research reference. It includes a lossless palette
scene-state codec, typed preservation/activation, signed streaming, a review
workspace and bounded deterministic research agents. It does not establish
learned semantic compression, canonical FF-RCT parity, clinical/legal correctness
or an independently validated production release.

## Install and verify

From the repository root, use Python 3.12 and Node 24. FFmpeg/ffprobe and
libseccomp are required for video and isolated-agent integration tests.

~~~bash
python -m pip install -r tools/activation_runtime/research/requirements.lock.txt
python -m unittest discover -s tools/activation_runtime/tests -p 'test_*.py' -v
python -m unittest discover -s tools/packspec_compiler -p 'test_finite_activation.py' -v
python -m tools.activation_runtime.audit
python -m tools.activation_runtime.run_research --out /tmp/qualityrag-research-run
~~~

The authored fixture clips are not a representative 100-clip corpus.
The measured reference codec is larger than AV1 in the committed experiment.
No byte, quality, cost or energy advantage is inferred from that run.

For pinned original APX WBC/RCoC checks, set QUALITYRAG_APX_ROOT to the absolute
path of tools/activation_runtime/vendor/apx, or to an APX checkout
at 9a4f8a3e4a3fe77d576369217525e54d0162b8b0 with packages/apx-wbc/src and
packages/apx-rcoc/src present. A missing source is an explicit error; optional
tests SKIP when the checkout is not configured. There is no Python substitute.

For the real browser test:

~~~bash
python -m pip install playwright==1.56.0
python -m playwright install chromium
QUALITYRAG_BROWSER_TESTS=1 python -m unittest discover -s tools/activation_runtime/tests -p 'test_browser.py' -v
~~~

## Open the local review workspace

~~~bash
python -m tools.activation_runtime.bootstrap --root /tmp/qualityrag-local
python -m tools.activation_runtime.cli serve --root /tmp/qualityrag-local/state --keys /tmp/qualityrag-local/public-keys.json --port 8769
~~~

Open http://127.0.0.1:8769 and paste the token from the generated browser-token.txt.
Bootstrap creates local research keys with private file permissions and a
24-hour access token. It does not create independent scientific review.
The workspace supports branch search, source history, change previews, reversible
pruning/reopening and review feedback. The configured host source allowlist runs
a bounded proposal scan every 60 seconds. No agent can validate or promote a claim.

Bind directly only to loopback. Use a separately configured authenticated TLS
gateway for remote deployment. Trust maps, tenant assignment and version floors
are host configuration, not request parameters.

## Run the actual scene-state reference codec

~~~bash
python -m tools.activation_runtime.cli train-scene --source training.mkv --out model.json
python -m tools.activation_runtime.cli encode-scene --source heldout.mkv --model model.json --out payload.json
python -m tools.activation_runtime.cli decode-scene --payload payload.json --model model.json --out reconstructed.mkv
~~~

The supported bounded profile is zero-origin CFR RGB24 plus normalized PCM32
audio, at most 512x512, 30fps, 120 frames and 10 seconds. Unsupported tracks
refuse rather than silently disappear. A shared backdrop palette plus exact
residuals reconstructs all normalized frame pixels. Full playback decoding
rechecks frames, source presentation timestamps and audio samples after writing
the playable file. Corrupt/missing/reordered residuals or incompatible models
refuse. Original source bytes remain in custody.

This is a predictive reference codec, not a semantic scene understanding model
or canonical FF-RCT implementation. Original container bytes are not recreated.

## Module map

| Module | Runnable behavior |
|---|---|
| contracts, fixtures, schemas | Eight versioned local JSON Schemas with valid examples and negative validation |
| preservation | Exact/approximate/unknown obligations, source anchors, omission inventory and independent signed IR binding |
| interpreter | Bounded PRESERVE/TRANSITION/ACTIVATE/VERIFY/FALLBACK with actual output checks and one checked fallback |
| adapters | Text, CSV row/line anchors and PDF page anchors; canonical extraction candidates remain quarantined |
| artifacts, authority | Immutable tenant-scoped custody, Ed25519 manifests, access principals, independent review binding and durable nonces |
| search, pipeline | Actual existing typed RCT compiler in a hard resource/syscall sandbox; identity baseline, held-out checks and policy-keyed cache |
| scene_codec, streaming | Actual encoded payload/playable output, signed decoder/model/index, independent segments, seek/pause/resume/representation switch and fallback |
| device, pilot | Sparse module planning/compilation, resumable atomic updates, version floor, CPU/RAM/wall limits and explicit unavailable power/device evidence |
| gardener, proposals | Append-only forks/synthesis/pruning/reopening, deterministic replay, ledger claims, bounded periodic suggestions and reviewer-reported outcome metrics. Branch `evidence_status` is read from the Research Ledger's effective status (never set by the Gardener); a synthesis reports its own claim, never its parents'. `gardener/event` accepts optional `evidence_ids`, which must already exist in the tenant's ledger (recorded host-side); TEST requires them. An UNRESOLVED_CHALLENGE suggestion clears once a TEST follows the latest CHALLENGE and is not raised for pruned branches. Duplicate detection is exact-statement only; paraphrase and contradiction detection are not implemented. The console's Research tree panel (web/garden.js) shows the tree live with query, replay and branch actions; `gardener/query`, the SDKs, `cli garden` and `mcp_server.py` give developers and agents the same access (docs/GARDENER-CONSOLE.md) |
| agents, roles | Six schema-constrained deterministic agents in separate default-deny seccomp/RLIMIT processes; disagreement blocks promotion |
| experiments | Immutable preregistration, family-leakage checks, proposer holdout denial, paired statistics and actual fixed/decoder-only/paired codec runs |
| neural_baseline | Offline hash-pinned CompressAI intraframe adapter; absent dependencies/weights refuse, lossy output cannot qualify as exact |
| economics | Full declared lifecycle components, cold/frequent/TV/mobile scenarios, no-crossover outcomes and full-dimension Pareto gates |
| service, cli, SDKs | Signed-principal HTTP API, local review UI, external PackSpec CLI, Python and TypeScript wire clients |
| release, audit | Independent signed pilot gate, critical-loss stop conditions, complete story inventory and evidence fingerprints |

Python SDK lives in sdk/python/qualityrag_activation; TypeScript SDK is
sdk/typescript/src/activation.ts. Both call the same canonical API. Golden
tests exercise actual HTTP parity for validation/evaluation/trace/fallback.
Unsupported options refuse; request bodies cannot select tenant or backdate time.

## Reproduce the paper and figures

~~~bash
python -m tools.activation_runtime.research.build_report --receipt tools/activation_runtime/research/receipts/engineering-v1.json --out /tmp/qualityrag-paper
~~~

The committed report, SVG figure and receipts are under research/paper and
research/receipts. The report states the negative codec result and missing
independent evidence. See research/prior-art.md for primary comparators and
research/protocol.json for the unregistered protocol template.

## Trust and acceptance boundaries

Hashes prove byte identity, not truth. A release signature authenticates a
configured signer and exact scope, not a reviewer's correctness. A detached
self-reported VERIFIED receipt never authorizes activation or module switching:
the signed source envelope is verified again at the point of use.

The agent backend is deterministic typed search, not an LLM or an autonomous
mathematical discovery claim. Its sandbox prevents file opening, sockets and
child process creation. Unsupported sandbox hosts fail closed.

The supplied evidence does not contain a representative independently reviewed
100-clip corpus, licensed neural weights, physical mobile/TV power/thermal runs,
independent clinical/legal adjudication or canonical FF-RCT reconstruction.
Those remain explicit acceptance gates. No parent story becomes DONE merely
because its software is committed or its authored tests pass.


## Complete reviewed workflow and story review packet

Run `python -m tools.activation_runtime.worked_workflows --out /tmp/reviewed-workflows`
for twelve complete success/refusal/fallback examples across four separate domain
PackSpecs. Inputs, signed requests, actual interpreter traces and receipts are
saved together. These use authored test authorities, not independent domain review.

The authenticated `/api/activate-plan` endpoint and Python `activate_plan`,
TypeScript `activatePlan` and CLI `activate-plan` clients support the same reviewed
finite workflow with host-configured per-tenant author/reviewer authority.
See [the configuration and integration guide](../../docs/REVIEWED-ACTIVATION-WORKFLOW.md).

Run `python -m tools.activation_runtime.delivery --out /tmp/story-delivery` to
produce a JSON/Markdown packet listing all 51 stories and 204 exact criteria,
runnable evidence and each remaining acceptance requirement. It is an audited
source inventory, not automatic acceptance. Once signed completion receipts are
present, provide the host's public-key map with `--completion-keys keys.json` and
its evaluation time with `--as-of <ISO-timestamp>` to verify DONE entries.


## Typed source observations

Use `python -m tools.activation_runtime.cli observations --source
<UTF-8-file> --request <observation-drafts.json>` to construct a bounded graph or
apply its optional total ID rename. The authenticated observations endpoint and
both SDKs support the same operation. Role endpoints and temporal dependencies
are checked against actual declared node kinds; anchors are revalidated against
the original bytes. Unknown annotation meaning remains unknown. This is not a
claim of canonical APX K/B/C/T/12G parity. See
[the source-observation graph guide](../../docs/SOURCE-OBSERVATION-GRAPH.md).


## Workspace source workflows

The local review workspace also runs already signed transformations from source
and request files, downloads exact server receipts, and inspects source-observation
graphs with optional ID transitions. Existing source hashes support read-only
inspection. Token switching clears results and discards delayed old responses.
See [workspace workflows](../../docs/REVIEW-WORKSPACE-WORKFLOWS.md) for configuration,
limits and the staged `run_reviewed` / `runReviewed` API.


## Inventory story acceptance

US-001 alone can close against its objective software criteria using live,
commit-bound GitHub source/CI evidence. This does not accept research claims or
waive another story's signed review or merge prerequisite. Private-repository
replay uses a host `GITHUB_TOKEN` with read-only access. See
[inventory acceptance](../../docs/INVENTORY-ACCEPTANCE.md).


## Versioned schema catalog

`python -m tools.activation_runtime.cli catalog` checks all ten schema/example
pairs, canonical round-trip and required rejection witnesses. It does not grant
semantic admission. US-002's source/CI completion check and its evidence renewal
procedure are described in [catalog acceptance](../../docs/SCHEMA-CATALOG-ACCEPTANCE.md).
