# QualityRag Academy — hands-on developer video series

Inspired by short, task-oriented developer tutorials: each lesson starts with a runnable objective, uses a real repository example, shows the expected output, explains limitations, and ends with a self-check.

**Public source:** [QualityRag](https://github.com/cyrillesaxo/QualityRag) (Apache-2.0) · **Status:** experimental v0.1. The evidence gate evaluates supplied metadata, not source truth or production suitability.

## Module 1: Evidence governance
| Episode | Goal | Command |
|---|---|---|
| 01. First evidence gate | Distinguish INCONCLUSIVE, ADMIT, REFUSE using real code | `PYTHONPATH=sdk/python python examples/python_demo.py` |
| 02. Write a PackSpec | Reproduce missing-exception checks against synthetic enterprise documents | `PYTHONPATH=sdk/python python examples/enterprise-rag/demo.py` |
| 03. Integrate QualityRag | Gate answer generation on evidence metadata | `PYTHONPATH=sdk/python python -m unittest discover -s sdk/python/tests` |
| 04. Witness independence | Detect same-origin duplicates, stale evidence, contradictions | [Training examples](../TRAINING.md) |

## Module 2: Representations and retrieval research
| Episode | Goal | Source |
|---|---|---|
| 05. Semantic Codex | Explain the four representation regimes | [experiment design](../SEMANTIC-CODEX-FOUR-REGIMES-V1.md) |
| 06. Run a four-regime experiment | Compare bounded candidate operations | `tools/semantic_store/run_four_regime_experiment.py` |
| 07. Semantic Store | Inspect revision-bound candidates and typed relations | [store guide](../../tools/semantic_store/README.md) |
| 08. Multimodal scene search | Inspect bounded sampled-frame candidate matching | [scene research](../SEMANTIC-CODEX-SCENES-V0.5.md) |

## Module 3: Research and governance
09. WitnessGraph; 10. Studio and policy versions; 11. Semantic Garden experimental review loop; 12. RAG reliability pilot methodology.

## Video production acceptance criteria
- Capture **actual running code and output** at a recorded repository revision; do not fabricate Studio UIs.
- Natural voice, synchronized with video, must be present in the final MP4; verify audio and video streams.
- Provide readable captions, transcript, exercise and expected result.
- Clearly distinguish metadata admission from source authenticity or semantic correctness.
- A student reproduces the lab from a clean checkout; regression tests pass.
- Mark synthetic fixtures and research-only components explicitly.

## Episode 01 — first evidence gate

Run `PYTHONPATH=sdk/python python examples/python_demo.py`; expect **INCONCLUSIVE** because only one origin is present where two independent sources are required. The next lab, `docs/academy/episode-01-lab.py`, walks through four cases. Run with `PYTHONPATH=sdk/python python docs/academy/episode-01-lab.py`.

For the full instructor narration, see [Episode 01 script](episode-01-script.md). Modules 02 and 03 are scripted in [scripts](episode-02-03-scripts.md); those are not yet recorded videos.

**Note:** the previously supplied onboarding video was revoiced with Grady in Higgsfield, but that is distinct from the new hands-on lesson.
