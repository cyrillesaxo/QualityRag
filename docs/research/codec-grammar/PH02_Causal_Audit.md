# PH01 to PH02: controlled mechanism audit

21 October 2026. Executed retrospective ablation; not independent replication.

## Verdict

**Supported on the nine archived development inputs:** PH02's added residual representations recover six wins while holding sources and the six successful structural prediction documents fixed. All nine rebuilt PH02 winners exactly match the archived payload bytes and SHA-256 values, and decode to their original sources.

**Not supported as stated:** adding constraints alone caused those wins. Inspection shows PH01 already compared complete file sizes among its available exact candidates. Its candidate grammar lacked PH02's correction alternatives. A requirement to consider economical correction alternatives can motivate the repair, but it combines a candidate-generation obligation with a representation expansion; it is not an extra fidelity constraint producing compression by itself.

**Disproved on these cases:** the explicit zero symbol was necessary to recover the six wins. Sparse coding of empty support retains all six wins and costs one extra byte on each of the four zero-residual cases.

## Design and interpretation rules

The protocol was written before executing this audit, but the historical results were already known. The audit reuses the archived source arrays, PH01 payloads and frozen native sizes. It recomputes inference, asserts exact document equality against each structural PH01 header, constructs residual candidates, decodes every candidate, and compares output hashes with archived PH02. No native encoder was rerun. Full framing and payload bytes are counted.

The alternatives tested were changed prediction, cost-policy-only improvement, explicit-zero necessity and uncharged framing. The primary stopping rules were source mismatch, prediction mismatch, failed reconstruction or historical replay mismatch. None occurred.

## Executed ablations

| Candidate grammar / policy | Wins against frozen best native |
|---|---:|
| PH01 incumbent | 0/9 |
| Full PH02 | 6/9 |
| PH02 without explicit zero | 6/9 |
| Sparse and sparse-zlib plus incumbent | 6/9 |
| Zero plus incumbent | 4/9 |
| Dense-zlib plus incumbent | 0/9 |
| PH02, but require at least 1,024 B saving over PH01 | 2/9 |

The last arm is a deliberately changed decision policy, not an alternative codec result. It shows how a restrictive policy can discard four genuine improvements even with the same available grammar. All arms retain PH01 as a candidate.

| Clip | PH01 B | PH02 B | No zero B | Dense only B | Frozen native B |
|---|---:|---:|---:|---:|---:|
| structured_3701 | 1888 | 912 | 913 | 1792 | 1263 |
| exceptions_3701 | 3903 | 1143 | 1143 | 2005 | 1875 |
| independent_3701 | 1936 | 960 | 961 | 1840 | 1332 |
| noise_3701 | 1240626 | 1240626 | 1240626 | 1240626 | 887970 |
| structured_3702 | 1892 | 916 | 917 | 1796 | 1246 |
| exceptions_3702 | 3753 | 1142 | 1142 | 2007 | 1820 |
| independent_3702 | 1936 | 960 | 961 | 1840 | 1346 |
| noise_3702 | 1240817 | 1240817 | 1240817 | 1240817 | 887970 |
| occlusion_3701 | 2834 | 2834 | 2834 | 2834 | 1261 |

## Exact mechanism accounting

Four sources have exactly zero residual. Their PH01 residual streams cost 977 B. PH02 retains identical compressed structure headers and adds a one-byte residual-mode selector with an empty correction payload. The complete saving is therefore 977 - 1 = 976 B per file. Removing zero mode chooses a one-byte empty sparse-support payload in addition to that selector: 975 B saved, with the same four native wins.

The two changing-detail sources select sparse-zlib and save 2,760 and 2,611 B over PH01. In this bounded intervention, neither prediction nor its structural document changes. Dense-zlib does not cross the native benchmark on any case. Thus the economic distinction is residual coding alternatives, especially sparse support, rather than better motion inference.

The two noise cases and occlusion case retain PH01 and still lose to the frozen native comparator. They are counterexamples to the stronger statement that this repair removes every competition gap.

## Why a pure extra constraint is insufficient here

Let A be a fixed finite candidate set, F its admissible subset and J the unchanged complete-byte objective. Adding a hard constraint yields F' contained in F. If F' is nonempty, min(J over F') is at least min(J over F). A restriction alone cannot lower the exact minimum over a fixed set. This elementary set argument does not forbid constraints from guiding a heuristic search toward previously ungenerated candidates. Such a process changes search or effective candidate availability, and needs a separate causal test.

PH02 expands A with new residual representations; PH01 already selects the minimum complete size among its generated candidates. The accurate RCT interpretation is: evidence reveals an expensive representational restriction; a revised grammar exposes cheaper exact alternatives; complete-cost selection retains them. Calling this only a missing constraint hides the implemented mechanism.

## Adversarial check and witness graph

A zero-mode stream was deliberately constructed for each of the six structurally inferred sources. It reconstructs exactly on all four truly zero-residual sources and fails source equality on both nonzero-residual sources. The decoder may parse the stream successfully; source equality, not parsing success, determines admissibility for the compression claim.

- Source hashes and unchanged prediction documents support causal isolation of the residual intervention.
- Exact candidate decodes and byte-identical archival replay support bounded mechanism attribution.
- Empty-support sparse alternatives contradict explicit-zero necessity.
- Existing complete-size selection contradicts attribution solely to newly added cost minimization.
- The three unchanged losses contradict sufficiency of this repair for the entire benchmark.
- These witnesses remain ambiguous with respect to whether RCT, ordinary engineering or another methodology would discover the repair faster.

## Deceptive-witness screen

| Class | Risk and treatment |
|---|---|
| Regime leakage | Development replay cannot establish fresh-source or natural-video superiority. |
| Coordinate masking | Exact image equality does not certify all parser states or physical scene inference. |
| Proxy substitution | Use whole payload bytes; preserve native framing differences as a limitation. |
| Coverage illusion | Nine inputs are finite evidence, not global proof. |
| Near-synonym witness | Separate hard constraint, candidate-generation obligation, grammar option and ranking policy. |
| Survivorship | Include all nine sources, especially all three continuing losses. |
| Authority laundering | Report executed assertions; do not infer independence from a script or formatted report. |
| Temporal witness | Hash archived inputs and byte-match historical winners; native costs remain historical. |
| Aggregate masking | Report per-clip outcomes and mode-specific ablations. |
| Self-confirming witness | Same research renderer/decoder and already-known corpus; independent verification remains open. |

## Limits and next falsifiable claim

This is a current execution of archived research code, not an unaffiliated replication. The native benchmark is not rerun, and the audit does not establish universal codec conformance or method-level superiority. Header equality isolates this intervention on six structural cases; it does not prove a general decomposition theorem for arbitrary codecs.

The remaining broad hypothesis should be stated prospectively: under equal budgets and independently assessed fidelity, targeted recovery of a diagnosed missing representation improves a prespecified fresh corpus more often than matched unguided changes. To evaluate whether RCT itself improves that process requires a competent control methodology and a frozen protocol. This audit neither proves nor disproves that method-level hypothesis.

## Reproduction

Run `python3 audit.py` in the unpacked package. Requires Python, NumPy, SciPy and FFmpeg capable of decoding the archived AV1 streams. `protocol.json` precedes this audit run; `audit_results.json` records source, code and output hashes, exactness, mode costs and environment identity. Native comparator bytes are frozen historical records. The package includes the residual-closure sources and payloads required for this replay.