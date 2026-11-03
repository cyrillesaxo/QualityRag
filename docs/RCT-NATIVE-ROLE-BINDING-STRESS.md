# Original APX role-binding stress: confirmed falsification result

## Reproducible evidence (2026-11-03)

- **Original private APX GitHub Actions run:** [41726055119](https://github.com/cyrillesaxo/apx/actions/runs/41726055119)
- **Run result:** successful native compilation and engine execution. This means the measurement code executed successfully; it does **not** mean semantic detection was successful.
- **APX checkout revision recorded by runner:** `52018f0677f53eccd75fc0951e16af5247c8f8fe`
- **Stress dataset raw SHA-256:** `cb01d8f9f0fc9f86e560f9f771cdae1d99be5cf01153c5a7657a69a391392ecd`
- **Native artifact:** `qualityrag-original-apx-native-scorecard` (contains both original and stress scorecard JSON)
- **Corpus:** `tools/semantic_store/data/semantic_role_binding_stress_v1.json` (the APX runner's matching copy is `scripts/qualityrag-role-binding-stress.json`)

## Measured results

| Label group | Number | Original APX comparator flagged `REFUSE` | Inconclusive / not detected |
| --- | ---: | ---: | ---: |
| Consequential role/entity/unit/order change | 12 | **0** | **12** |
| Harmless wording controls | 6 | **0** | **6** |

**Observed detection: 0/12.** This is a meaningful *counterexample to generalizing* the previous 18/18 synthetic result, not a statistical estimate of population accuracy.

Examples include:
- `Alice must pay Bob` → `Bob must pay Alice` (obligor/beneficiary inversion)
- `left eye` → `right eye` (laterality)
- `5 psi` → `5 bar` (unit)
- `before` → `after` (ordering)
- `Account Alpha` → `Account Beta` (recipient identity)

These differences can leave the original comparator's finite lexical atom fingerprints unchanged. The native comparator correctly remains `INCONCLUSIVE` instead of granting permission, but it cannot be claimed to have detected the actual drift.

## Consequences for QualityRag architecture

1. The semantic primitive **must include typed relational structure** (participants, roles, operands, units and dependency/temporal edges), not just token multiset conservation.
2. Preserve exact source-version anchoring and explicit reviewer obligations, including `K,b,c,t`, 12G, WBC and RCOC coordinate separation. A signed assertion is not independent truth.
3. Do not patch this benchmark to appear perfect by refusing every changed string. That approach would lose the distinction between harmless paraphrase and consequential role reversal.
4. Evaluation must report inconclusive consequential cases as missed or unresolved, even when QualityRag does not generate from them.
5. The next research test is whether **reviewed, version-bound typed role graphs** expose these inversions without inventing a general natural-language parser. Automated role extraction requires independent evaluation, and the original comparison cannot be made safe by test-specific word lists.

**No ADMIT, disclosure, or FF-RCT compression follows from this diagnostic.** The original dataset was hand-authored; independent expert adjudication and true source authority remain pending.
