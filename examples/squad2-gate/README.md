# SQuAD 2.0 false-admission benchmark

This is the first measurement of the QualityRag gate on **public data with evidence labels produced from text**. Earlier examples used hand-assigned `status` values.

Each question goes through the same pipeline:

```
retrieve top-k paragraphs (lexical, within the question's article)
  -> label each paragraph: does it contain the answer? (SUPPORTS / CONTRADICTS / UNKNOWN + span)
  -> gate with one requirement, "answer-present"
  -> ADMIT = answer, anything else = abstain
```

Ground truth is about the **retrieved context**, because that is all the gate can see:

- **positive**: the question is answerable and a gold answer string appears in a retrieved paragraph.
- **negative**: the question is one of SQuAD 2.0's adversarial unanswerable questions, *or* it is answerable but retrieval missed the paragraph with the answer.

```bash
PYTHONPATH=sdk/python python examples/squad2-gate/run_benchmark.py --n 1000           # downloads + caches the dev set
PYTHONPATH=sdk/python python examples/squad2-gate/run_benchmark.py --n 200 --llm      # adds the LLM labeler (needs `anthropic` + ANTHROPIC_API_KEY)
PYTHONPATH=sdk/python python -m unittest discover -s examples/squad2-gate -p 'test_*.py'   # CI fixture, no download
```

The dataset (SQuAD 2.0 dev, CC BY-SA 4.0) is downloaded on first run and cached outside the repository. The report records its SHA-256.

## First results (lexical labeler only)

Random sample of n = 1000 dev questions, seed 0, k = 1, dataset sha256 `80a5225e9490…`. 384 positives and 616 negatives.

| labeler | answer rate | false-admission rate | FAR (unanswerable) | FAR (retrieval miss) | admit precision | span hit rate |
|---|---|---|---|---|---|---|
| no gate | 1.000 | 1.000 | 1.000 | 1.000 | 0.384 | — |
| oracle | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| lexical@0.4 | 0.964 | 0.873 | 0.895 | 0.777 | 0.407 | 0.911 |
| lexical@0.6 | 0.773 | 0.602 | 0.647 | 0.402 | 0.445 | 0.933 |
| lexical@0.8 | 0.432 | 0.239 | 0.274 | 0.080 | 0.530 | 0.976 |
| lexical@1.0 | 0.221 | 0.097 | 0.113 | 0.027 | 0.586 | 0.988 |

With k = 3, the pattern is the same: at threshold 0.6 the answer rate is 0.745 and the false-admission rate is 0.664.

## What this shows

- **The gate is only as good as its labeler.** With oracle labels, the same 70-line gate gives zero false admissions at full coverage. With lexical labels, raising the threshold mostly trades answers for abstentions. At 0.6, the gate answers 77% of answerable questions but still admits 65% of the adversarial unanswerable ones.
- **The lexical labeler does catch retrieval misses** (wrong paragraph retrieved) much better than adversarial questions. Those questions were written to share wording with the paragraph, so word overlap cannot separate them.
- **Spans are useful even when the verdict is wrong.** When lexical labeling admits an answerable question, the cited sentence contains the gold answer 93% of the time at 0.6. Admissions are traceable.

The next comparison that matters is a semantic labeler (the `--llm` path, or an NLI model) on the same sample. It should be judged against two baselines: the oracle above and a plain "answer, or say you don't know" LLM with no gate. The LLM labeler fails closed: a SUPPORTS label counts only if its quote is an exact substring of the passage.

## Limits

SQuAD paragraphs are short, single-source Wikipedia text. There is no multi-source independence, no staleness and no contradiction, so this exercises the labeling step and the ADMIT/abstain decision, not the gate's corroboration logic. Answer matching is case-insensitive substring matching on gold answer strings. Retrieval is lexical within the gold article, which is easier than open-corpus retrieval.
