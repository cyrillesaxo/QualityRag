# Fresh test of diagnosed correction constraints

21 October 2026. Executed frozen-policy test on fresh related synthetic seeds.

## Question

Does the correction-coverage repair transfer beyond the nine development inputs, when both arms have the same fallback candidates? The operational obligation is to enumerate exact zero/sparse correction alternatives, charge all support, values and framing, verify reconstruction, and select complete cost while retaining incumbents. This tests a constraint-guided representation policy, not hard constraints added to an unchanged candidate space.

## Frozen design

Before source generation, `protocol.json` fixed seeds 91121 and 91122; six categories per seed; 16 RGB frames, 96 by 96 pixels at 24 fps; source rules; baseline; intervention; diagnostic control; stopping rules and success criterion. Existing codec and generator code were hashed before any source was generated. No tuning followed observation. Cases include structured, changing-detail, independent motion, noise, occlusion and background drift. Background drift adds a frame-index offset modulo 256 to all structured-source samples.

The baseline selects among complete PH01, literal RGB and H.264 RGB lossless veryslow. PH01 itself tests AV1 profiles as defined by its archived implementation. The intervention adds frozen PH02 candidates. Both sides pay the same 33-byte comparison allowance for shape/dispatch framing. This allowance is accounting normalization, not an emitted or verified CH03 wrapper in this test. Saved candidate payloads and source arrays are provided. No market-wide or VVC/AV2 comparison is implied.

## Results

| Fresh clip | Baseline B | Selected B | Reduction | Selected branch |
|---|---:|---:|---:|---|
| structured_91121 | 1440 | 912 | 36.67% | PH02 |
| exceptions_91121 | 2408 | 1036 | 56.98% | PH02 |
| independent_91121 | 1456 | 928 | 36.26% | PH02 |
| noise_91121 | 442401 | 442401 | 0.00% | raw |
| occlusion_91121 | 2105 | 2105 | 0.00% | h264rgb |
| background_drift_91121 | 2996 | 2996 | 0.00% | h264rgb |
| structured_91122 | 1434 | 906 | 36.82% | PH02 |
| exceptions_91122 | 2292 | 1030 | 55.06% | PH02 |
| independent_91122 | 1462 | 934 | 36.11% | PH02 |
| noise_91122 | 442401 | 442401 | 0.00% | raw |
| occlusion_91122 | 2089 | 2089 | 0.00% | h264rgb |
| background_drift_91122 | 2833 | 2833 | 0.00% | h264rgb |

All twelve sources reconstruct exactly. Six strict wins and six ties satisfy the frozen bounded success criterion. The six ties are noise, occlusion and background drift, each on both seeds. Fallback retention explains non-regression; it is a selection property, not independent evidence of better structural modeling. The meaningful new observations are the six strict wins on fresh seeds.

Winning reductions range from 36.11% to 56.98%. Dense-zlib-only alternatives yield 6 strict improvements over the same baseline.

## Diagnostic result: the control also improves

Dense-zlib alone wins on the same six cases. Thus six fresh wins do not uniquely support the sparse/zero mechanism: generic residual-backend substitution is a viable explanation for crossing this weaker, declared baseline. Full PH02 is additionally 439-452 bytes smaller than the dense-only result on those cases. This separates the backend-switch effect from the incremental zero/sparse benefit. Unlike the earlier nine-case comparison against frozen VVC minima, this fresh comparison is not evidence that dense coding cannot beat competition.

| Clip | Baseline B | Dense-only B | Full PH02 B |
|---|---:|---:|---:|
| structured_91121 | 1440 | 1364 | 912 |
| exceptions_91121 | 2408 | 1475 | 1036 |
| independent_91121 | 1456 | 1380 | 928 |
| structured_91122 | 1434 | 1358 | 906 |
| exceptions_91122 | 2292 | 1472 | 1030 |
| independent_91122 | 1462 | 1386 | 934 |

## What is supported

The diagnosed correction-coverage obligation, implemented by expanding the residual grammar and selecting complete exact candidates, transfers to fresh related synthetic cases. Changes to residual representation are sufficient to improve this declared baseline on six cases. The narrower statement now has both development replay and fresh-seed witnesses.

The experiment does not establish that a newly added hard constraint mathematically causes lower cost. PH01 already selects complete cost among available alternatives. The effective intervention expands candidate availability; constraints govern eligibility and faithful accounting. These are complementary roles, not interchangeable terms.

## What remains unproved

The universal claim that every remaining codec loss is explained by missing constraints is not established. Occlusion and background drift remain unhelped by this frozen repair. They suggest different modeling limitations, but do not uniquely identify the next successful intervention. An indefinitely expandable definition of constraint would be unfalsifiable unless a proposed obligation predicts a measurable repair before testing.

RCT-specific discovery advantage is also unresolved. We did not compare how rapidly RCT and competent ordinary engineering identify the repair. Fresh seeds from a known generator are not an independent distribution or natural-footage validation. The same research renderer/decoder supplies exactness checks; this is not unaffiliated replication. H.264/AV1 are bounded configurations under the recorded current environment.

## Witness and anti-witness interpretation

- Six fresh strict gains support transfer of the frozen representation policy.
- Zero structural gains on six controls bound its domain and contradict a universal repair claim.
- Dense-only ablation tests whether a generic residual backend substitution explains the wins.
- Forced-zero candidates are checked against source equality whenever structural inference succeeds; parsing alone is not used as fidelity evidence.
- Identical fallback pools mitigate misleading gains from comparator asymmetry.
- Exact decodes, hashes and complete costs do not measure method superiority.

The main deceptive-witness risks are regime leakage (related synthetic to real video), proxy substitution (payload versus full delivery cost), aggregate masking (noise dominates total bytes), survivorship (omitting controls), and self-confirmation (shared generator and decoder). The report provides per-clip results, a common explicit accounting allowance and the complete twelve-case corpus. Independent verification remains open.

## Reproduction

`run.py` expects the archived codec modules in sibling `PH02_Causal_Audit/RCTV_Residual_Closure` and the generator in `PH02_Causal_Audit/RCTV_PH02_Validation`. The package includes those required Python sources. Requires NumPy, SciPy and FFmpeg with libaom and libx264rgb. Source and codec hashes, commands, every candidate cost and source/wire hashes are in `results.json`. The selected underlying payloads are exact; no production wrapper is claimed. The frozen protocol is inspectable, but a local hash alone is not a third-party timestamp or external preregistration.