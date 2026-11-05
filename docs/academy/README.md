# QualityRag Academy

The Academy is a problem-driven training programme. Each chapter opens on a failure that RAG teams describe in their own words. It then shows what QualityRag does about it, using real SDK output, and ends with what QualityRag does **not** guarantee.

This release covers the first five chapters, the ones aimed at winning customers. The full twenty-chapter plan is in [docs/training/README.md](../training/README.md#qualityrag-academy-twenty-problems-one-episode-each).

| Chapter | The complaint | Video | Lab | Status |
|---|---|---|---|---|
| A1 | "It found the right document, but gave the wrong answer." | [watch](episodes/academy-a1-right-document-wrong-answer/academy-a1-right-document-wrong-answer.mp4) | [a1](labs/a1_right_document_wrong_answer.py) | Available now |
| A2 | "It confidently invents an answer when the evidence is missing." | [watch](episodes/academy-a2-governed-abstention/academy-a2-governed-abstention.mp4) | [a2](labs/a2_governed_abstention.py) | Available now |
| A3 | "Three sources agree, but they all copied the same original." | [watch](episodes/academy-a3-independent-sources/academy-a3-independent-sources.mp4) | [a3](labs/a3_independent_sources.py) | Available now |
| A4 | "It uses outdated policies, and picks a side when documents disagree." | [watch](episodes/academy-a4-stale-and-contradicting/academy-a4-stale-and-contradicting.mp4) | [a4](labs/a4_stale_and_contradicted.py) | Available now |
| A5 | "My PDF tables are completely messed up. How would I even know?" | [watch](episodes/academy-a5-unverified-extraction/academy-a5-unverified-extraction.mp4) | [a5](labs/a5_unverified_extraction.py) | Research preview |

## What each chapter contains

- **A cinematic episode, 1–1.5 minutes long.** It opens with the complaint, then shows the failure, the real lab output, the live console where it applies, and the boundary: what QualityRag does and does not do. Captions are burned in, with `.vtt` and `.srt` alongside.
- **An interactive chapter** in [index.html](index.html), built from [chapters.json](chapters.json). It includes:
  - Bloom's-taxonomy objectives and a learning-path choice (quick, standard or deep);
  - confidence checks before and after;
  - a scenario with Cloudina, Grumpy and Junior;
  - a verified real case (A2: *Moffatt v. Air Canada*, 2024 BCCRT 149; A3: *Mata v. Avianca*, S.D.N.Y. 2023);
  - active recall, the lab with its real output, a war game, a boss fight with hints that cost XP, and a quiz;
  - spaced-repetition review at 1, 3, 7, 14 and 30 days;
  - XP with daily decay, streaks, and hidden instructor notes.
- **A lab** in [labs/](labs/): a short script against the real Python SDK. It needs no model, keys or network. [labs/test_labs.py](labs/test_labs.py) checks that every lab still prints the verdicts the chapter teaches.

## Run it

```sh
python docs/academy/labs/a1_right_document_wrong_answer.py     # any lab, from the repository root
python docs/academy/labs/test_labs.py                          # check that the labs still teach the truth
python docs/academy/build.py                                   # rebuild index.html from chapters.json
python docs/training/render/render.py docs/academy/episodes/academy-a1-right-document-wrong-answer \
  --voice-dir voice --out out/a1                                # re-render an episode (see docs/training/README.md)
```

Open `index.html` from a local checkout to take the Academy offline. Progress is saved in your browser. The published Academy page saves progress privately to each signed-in learner's account.

## Honest boundaries

- The scenarios use the synthetic EU payments corpus. Its passages are invented.
- The real cases are summarised from the cited sources. They show the failure pattern; they are not claims about which technology those systems used.
- A5 is a research preview. QualityRag treats unchecked extraction as `UNKNOWN`, and Semantic Codex keeps source anchors and marks partial coverage. Table repair, OCR and table-structure validation are not implemented.
- Career salary ranges and translations, which are part of the Dodo v4 template, are left out until sourced figures and reviewed translations exist.
