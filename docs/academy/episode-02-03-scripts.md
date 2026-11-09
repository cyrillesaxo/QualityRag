# Episode 02 — Your first PackSpec: the missing exception
Target: 5–6 min. **Synthetic enterprise case**, not a real customer deployment.

0:00 — The operational handbook says restart; the regional control annex may require approval. What happens when retrieval misses the annex?

0:30 — Open `docs/TRAINING.md` and explain the declared obligations `recovery-procedure`, `eu-screening-control`, `applicable-approval-or-exception`.

1:15 — Open `examples/enterprise-rag/corpus.json`. These are **JSON fixtures**, not scanned binary PDFs, OCR, live embeddings or LLM calls.

2:00 — Run `PYTHONPATH=sdk/python python examples/enterprise-rag/demo.py`. Compare the first scripted retrieval's INCONCLUSIVE with second scripted retrieval's ADMIT.

3:10 — Inspect exactly which obligations were missing, and why more generic passages would not satisfy them.

4:10 — Emphasize that the metadata gate cannot find an exception nobody declared, authenticate the annex or authorize restarting the gateway.

5:10 — Exercise: modify an evidence requirement and rerun. End with a regression check.

# Episode 03 — Put the evidence gate before generation
Target: 6–8 min.

0:00 — Adding 'be careful' to an LLM prompt is not the same as enforcement.

0:30 — Show the architecture: question → retrieval → source-aware evidence builder → versioned PackSpec evaluator → application decision.

1:10 — Run `PYTHONPATH=sdk/python python examples/python_demo.py` and inspect INCONCLUSIVE. Show that the application must withhold generation on REFUSE and INCONCLUSIVE.

2:30 — Write three tests (missing evidence, contradiction, metadata obligations met) and assert result handling. For ADMIT, additional source authority and semantic applicability checks remain necessary.

4:30 — Explain metadata trust boundary, independent origins, timestamp validation and how policy versions matter.

6:00 — Exercise: add a controlled targeted-retrieval branch that does not silently issue an answer.

**Do not invent an actual production deployment, observed ROI, or authenticated source truth.** Both scripts require screen capture and verified natural narration before they become videos.
