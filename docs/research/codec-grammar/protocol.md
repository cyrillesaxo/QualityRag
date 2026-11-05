# PH01 → PH02 experimental reproduction protocol (v0.1)

This is a **proposed reproduction protocol**, not a transcript of the original historical experiment. It deliberately does not invent original parameters, source clips, source code, metric definitions or experimental logs.

## 1. Unit of evaluation and hypothesis

One paired observation compares a candidate construction and named native baseline on the **same** precisely identified input, measured under matching preservation constraints. Record clip ID, SHA-256, media properties, candidate grammar version, baseline codec/version, command lines, decoder install/reuse assumptions, machine profile, and output metrics.

- **H1 expressive reach:** PH02's grammar adds reachable constructions absent from PH01.
- **H2 matched performance:** An improvement persists when inputs, preservation contracts, baseline settings, resource limits and evaluation criteria are matched.
- **H3 causal contribution:** Ablating specific grammar productions removes the improvement while other conditions stay fixed.
- **H4 transfer:** The advantage survives separately sealed synthetic holdouts and real-video inputs.
- **H5 lifecycle economy:** End-to-end cost (including decoder installation, setup, transmission, amortization and failures) improves in the target workload.

Treat these as separate hypotheses. H1 does not prove H2; H2 does not prove H3, H4, or H5.

## 2. Inputs and baselines

Maintain a manifest of every source input, its custodian/license, SHA-256 and exact data split (training, grammar-development, validation, sealed holdout, real-video). No input should move between splits after inspection. Compare at least PH01, PH02, and native AV1; include other codecs only when their versions and configurations are fully disclosed. Use actual native binaries and report their hashes. Specify decode output requirement: bit-exact reversibility or predeclared rate-distortion/perceptual threshold. Never change the preservation condition mid-comparison.

For each arm, pin CPU/GPU/OS, thread count, target quality/rate settings, startup costs, timeouts, random seeds, software hashes, codec flags, and failures. **Do not infer** these from reported win counts.

## 3. Grammar construction and search

Record which existing codecs/implementations influenced each production, their license and provenance, and precisely which operation or structure was extracted. Publish:

- PH01 grammar and PH02 grammar as machine-readable versions, with semantic diffs;
- candidate AST / composition, validity constraints, encoder and decoder behavior;
- mutation/composition operators and allowed search budget;
- candidate generation seeds, rejection reasons, objective and ranking algorithm;
- the complete candidate trace, including failed and dominated candidates;
- held-out candidates and trials, without retrospectively rewriting success definitions.

Distinguish a **new candidate construction** from a mere reconfiguration or wrapper of an existing codec. Review novelty relative to available codec literature rather than asserting patent-level novelty from performance results.

## 4. Gate before score

A candidate must satisfy all predeclared PackSpec requirements before its score can be counted. Examples: original-source custody, decoder availability, exact or bounded-quality reconstruction, required semantic preservation, source provenance, dependency license, and explicit fallback behavior.

- **ADMIT**: evidence supplied satisfies the declared local checks; not proof of source truth.
- **REFUSE**: explicit contractual violation/contradiction.
- **INCONCLUSIVE**: missing evidence, unknown install cost, incomplete coverage or unverified claims.

Do not turn INCONCLUSIVE into a performance win. Record fallback as a separate outcome and include fallback bytes/cost where relevant.

## 5. Measurement and reporting

Publish a row for **every clip × arm × repeat**, including errors, no-result cases, outliers and fallback. At minimum record output bytes, source bytes, decode success, quality metrics (if lossy), encode/decode wall time, peak memory, power/energy if measured, setup and decoder distribution cost, hardware, experiment timestamp and SHA-256 receipts. If a measure is unknown, encode null/unknown, never zero.

Define the original “win” predicate explicitly; if unavailable, mark historical win counts **unverified**. For a new run, preregister a primary endpoint and report wins/losses/ties, paired differences, uncertainty and distributions—not only win percentage. Separate synthetic and real-video regime summaries.

## 6. Critical ablations

Run a controlled factorial design:
1. PH01 grammar + original search budget.
2. PH02 grammar + **the same** search budget.
3. PH02 grammar with individually removed added productions.
4. PH01 grammar + any changed optimizer/activation mechanism, holding other settings fixed.
5. PH02 grammar + changed optimizer/activation mechanism.
6. Exact native baseline, plus decoder-install-amortization sensitivity.

If controls differ, report the confound rather than attributing gain to grammar expansion. Record cases where the broader grammar increases search time or fails to improve results.

## 7. Admission, release, and review

Maintain immutable experiment receipts and reviewer decisions in Semantic Store. A Garden research champion is not automatically a production codec release. Require independent replication on fresh held-out workloads, lifecycle cost accounting, robustness tests, and license/security checks before production claims.

**Reproduction status at protocol publication:** no original PH01/PH02 executable source or per-run evidence is included in this directory. This protocol enables a future independently checkable experiment; it does not itself replicate the reported PH02 findings.
