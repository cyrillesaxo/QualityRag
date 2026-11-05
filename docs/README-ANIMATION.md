# QualityRAG README animation

The root [README](../README.md) embeds **`docs/assets/qualityrag-how-it-works.gif`**.
The binary GIF is generated reproducibly from the committed Python script,
[`scripts/build_qualityrag_readme_gif.py`](../scripts/build_qualityrag_readme_gif.py).
The file is a self-contained 960 × 540 nine-frame looping animation (~200 KB).

## Narrative and semantics

1. A user asks a fictional company-policy question.
2. Retrieval finds an original handbook and a copy.
3. A versioned PackSpec requires two *independent* source origins, currentness,
   and appropriate scope.
4. The two documents collapse to **one origin**, so the requirement is unsatisfied.
5. QualityRAG's deterministic gate returns **INCONCLUSIVE**; the application
   should abstain or obtain more evidence.
6. An independent process-owner document becomes available.
7. The supplied metadata now satisfies the contract: **ADMIT**.
8. The application can then generate a cited answer; QualityRAG itself is not
   an LLM or an automatic document-truth verifier.
9. The separate **experimental Semantic Garden** investigates grammar and
   activation changes; it does not auto-promote results into policy.

This is a schematic, fictional example. **ADMIT does not establish source
truth**, only satisfaction of the configured checks. The reference animations
are not experimental results or performance comparisons.

## Regenerate

Install Python 3.12+, Pillow, and the DejaVu Sans system fonts:

```bash
python -m pip install 'Pillow>=10,<13'
python scripts/build_qualityrag_readme_gif.py \
  --output docs/assets/qualityrag-how-it-works.gif
```

The generator checks that the result contains 9 frames, is 960 × 540,
and is no larger than 2 MB. GitHub Actions' animation workflow generates
and commits the GIF on its dedicated documentation branch; it doesn't need
API credentials, image models, proprietary fonts, user data, or external media.
GitHub will display the image by its relative path in the root README after
the generated asset is committed.

## Accessibility

The README image includes descriptive alternative text. The explanation in
this file repeats all major transitions as text so users who cannot view GIFs
can still understand the workflow. The animation is illustrative, loops, and
contains no rapidly flashing frames.
