# Codec grammar discovery — research and reproduction entry point

**Author/research context:** Cyrille Eloundou · DODO LLC · APX / QualityRag  
**Status:** Research dossier. Historical results are reported from the project's research discussion, **not independently reproduced in this repository**. This directory contains no original PH01/PH02 codec source, source clip corpus, per-clip measurement table, or independently auditable run logs as of this addition.

## Research question

Can a new codec construction be discovered by extracting an executable grammar from *existing* codecs, then composing, extending, and testing productions beyond the individual source implementations?

The distinctive move is **grammar induction and expansion**, not merely hyperparameter tuning or selecting a codec from a fixed menu. Existing codec implementations embody reusable representation choices: prediction, transform, segmentation, temporal reuse, quantization, entropy coding, transport, and decoder obligations. Discovering a new combination requires an expressive search language whose candidate construction and decode behavior are explicit.

The causal hypothesis is: **an optimizer cannot discover a candidate excluded by its grammar**. PH01 → PH02 motivated this hypothesis but the numbers alone do not establish that grammar expansion, rather than changed workloads, baselines or settings, caused the difference. Consult the ablation requirements before asserting causality.

## Historical results (reported, not repository-verified)

| Study | Reported observation | Scope and important constraint |
| --- | --- | --- |
| PH01 | 0 wins across 9 stronger-native-baseline comparisons | Baseline settings, clips, and raw scores are not yet deposited |
| PH02 | 6 wins across 9 small synthetic-video comparisons in an AV1 comparison program | Synthetic-video regime only; not a claim of general AV1 superiority |
| Fresh synthetic transfer | 7 wins, 1 tie across 8 clips | Fresh synthetic clips; original per-clip receipts not yet deposited |
| Ablations | Challenged the initial explanation of PH02 gains | No isolated causal conclusion without factorial comparisons |
| Real-video boundary | Structural candidate declined; AV1 fallback was used | Must count fallback, install work and losses; do not cherry-pick |

**These are project-reported outcomes.** The exact meaning of “win” (byte size, rate-distortion, perceptual quality, wall time, complete lifecycle economics) must be recovered from original run definitions and published with raw metrics before numerical comparison can be independently checked.

## Why this belongs in QualityRag

- **Semantic Store:** versioned source inputs, candidate grammars, codec constructions, activation lenses, measurements, provenance, and immutable experiment receipts.
- **Semantic Garden:** failed trials and counterexamples seed investigations; agents propose revised grammar or activation mechanisms; versions are compared under matched constraints.
- **QualityRag / QualityGate:** PackSpec defines preservation, completeness, provenance, decoder availability, and admission conditions. An improvement in one metric is not automatically permission to lose a required distinction.
- **APX / RCT:** supplies regime-aware constraint and workload reasoning. Internally validated research and publicly reproducible findings must be described separately.

The original video codec and the current repository's [Semantic Codex IR](../../SEMANTIC-CODEX-V0.1.md) are **distinct artifacts**: the IR prototype indexes structured cross-format records; it is not PH02 and must not be presented as a replacement implementation. The [continuous RCT research PR #70](https://github.com/cyrillesaxo/QualityRag/pull/70) is related infrastructure but not proof that PH02 is reproduced.

## Reproduce / independently challenge

1. Read [protocol.md](protocol.md) for candidate construction, matched baselines, validity gates, holdouts, and reporting.
2. Use [result-manifest.schema.json](result-manifest.schema.json) to validate the shape of each future run receipt; it is a **schema, not historical evidence**.
3. Obtain the original PH01/PH02 code, codec sources and licenses, exact command lines, seeds, clip inputs and checksums, native comparison settings, environment manifests, per-clip measurements, failures and ablation transcripts from their custodians.
4. Deposit original files without altering them under a documented data release or immutable externally hosted release; preserve source hashes and license/provenance information. Do not add private material without authorization.
5. Run matched comparisons. Require decoding/semantic obligations to pass *before* comparing compression ratios. Publish failures and fallback observations.
6. Publish independent reproduction outcomes separately from the historical report, with a fresh run ID and an explicit investigator identity.

### Evidence inventory

| Artifact needed | Present here? |
| --- | --- |
| Research question and reported outcomes | Yes |
| Explicit reproduction protocol and validation schema | Yes |
| PH01 and PH02 source implementations | **No** |
| Extracted production grammar and grammar evolution diff | **No** |
| Original synthetic and real-video assets with SHA-256 | **No** |
| Original full per-run measurements and environment | **No** |
| Native AV1 baseline settings and exact commands | **No** |
| Independent replication receipts | **No** |

**Do not fabricate missing artifacts.** Add them only from preserved primary records, and record their lineage.

## Related work already in this repository

- [Semantic Codex v0.1](../../SEMANTIC-CODEX-V0.1.md)
- [Semantic Codex economics](../../SEMANTIC-CODEX-ECONOMICS-V0.8.md)
- [RCT induced grammar](../../RCT-INDUCED-GRAMMAR-v1.1.md)
- [RCT compositional operator AST](../../RCT-COMPOSITIONAL-OPERATOR-AST-v1.3.md)
- [RCT PackSpec governance bridge](../../RCT-PACKSPEC-GOVERNANCE-BRIDGE-v1.6.md)
- [Semantic Store tools](../../../tools/semantic_store/README.md)

## Public claim boundary

Say: *“In internal synthetic-video experiments, an expanded codec grammar produced reported scoped wins; we are publishing the protocol and seeking reproducibility.”*

Do **not** say: *“QualityRag beats AV1”*, *“PH02 was independently replicated”*, or *“the current Semantic Store implements the PH02 codec”* unless evidence for those specific claims is subsequently deposited and reviewed.

## Recovered primary research documents (October 21, 2026)

- [PH02 causal audit](PH02_Causal_Audit.md): original retrospective nine-case mechanism audit, with source/decoder reconstruction and byte-level replay **reported by its authors**; the archived binary payloads and audit runtime are **not included here**.
- [Fresh correction test](Fresh_Constraint_Test.md): original 12-case frozen-policy report (six strict improvements and six ties); dense-only alternatives also improve the same six, so the causal interpretation is bounded.
- [Reported tables](reported-tables.json): verbatim numerical values transcribed from those two research reports into typed JSON for review; not original packet outputs.
- [Arithmetic checker](verify_reported_tables.py): run `python3 docs/research/codec-grammar/verify_reported_tables.py` to recompute counts and table consistency with Python standard library. This does **not** execute PH02, validate original hashes, or rerun native encoders.

**Distinct studies:** the fresh twelve-case test here (6/12 strict improvements, 6 ties) is **not** the separately reported eight-clip 7/1 transfer comparison. Do not combine their denominators or treat 7/1 as PH02-only evidence without the original SC06/PH02 selection record.

**Original audit package still required for packet replay:** `audit.py`, `protocol.json`, `audit_results.json`, `RCTV_Residual_Closure/`, `RCTV_PH02_Validation/`, archived source arrays and candidate payloads, and FFmpeg/native baseline configuration. The similarly named standalone `audit.py` in other research assets is not necessarily the PH02 script. Preserve the bundle exactly as originally archived; do not substitute a different codec audit.
