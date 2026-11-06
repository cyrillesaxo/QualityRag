# QualityRag Academy

The Academy is a problem-driven training programme. Each chapter opens on a failure that RAG teams describe in their own words. It then shows what QualityRag does about it, using real SDK output, and ends with what QualityRag does **not** guarantee.

This release covers eleven chapters:

- A1–A5 are aimed at winning customers.
- A6–A8 are the research track. Each pairs a pattern that works today with a research prototype.
- A12–A14 are the measurement track, built on branch replay of labelled cases and on Evolution's held-out families. The full twenty-chapter plan is in [docs/training/README.md](../training/README.md#qualityrag-academy-twenty-problems-one-episode-each).

| Chapter | The complaint | Video | Lab | Status |
|---|---|---|---|---|
| A1 | "It found the right document, but gave the wrong answer." | [watch](episodes/academy-a1-right-document-wrong-answer/academy-a1-right-document-wrong-answer.mp4) | [a1](labs/a1_right_document_wrong_answer.py) | Available now |
| A2 | "It confidently invents an answer when the evidence is missing." | [watch](episodes/academy-a2-governed-abstention/academy-a2-governed-abstention.mp4) | [a2](labs/a2_governed_abstention.py) | Available now |
| A3 | "Three sources agree, but they all copied the same original." | [watch](episodes/academy-a3-independent-sources/academy-a3-independent-sources.mp4) | [a3](labs/a3_independent_sources.py) | Available now |
| A4 | "It uses outdated policies, and picks a side when documents disagree." | [watch](episodes/academy-a4-stale-and-contradicting/academy-a4-stale-and-contradicting.mp4) | [a4](labs/a4_stale_and_contradicted.py) | Available now |
| A5 | "My PDF tables are completely messed up. How would I even know?" | [watch](episodes/academy-a5-unverified-extraction/academy-a5-unverified-extraction.mp4) | [a5](labs/a5_unverified_extraction.py) | Research preview |
| A6 | "The answer is spread across three files, and RAG only reads one." | [watch](episodes/academy-a6-combine-documents/academy-a6-combine-documents.mp4) | [a6](labs/a6_combine_documents.py) | Available pattern + research (explicit, anchored link candidates) |
| A7 | "It can't understand our diagrams, or our images, or our videos." | [watch](episodes/academy-a7-images-and-video/academy-a7-images-and-video.mp4) | [a7](labs/a7_images_and_video.py) | Research preview (visual appearance search; identity unknown) |
| A8 | "It gave the right rule, for the wrong customer or region." | [watch](episodes/academy-a8-wrong-scope/academy-a8-wrong-scope.mp4) | [a8](labs/a8_wrong_scope.py) | Available pattern + research (purpose-scoped lens) |
| A12 | "We can't tell if our RAG is getting better, or just sounding better." | [watch](episodes/academy-a12-measure-improvement/academy-a12-measure-improvement.mp4) | [a12](labs/a12_measure_improvement.py) | Experimental (branch replay: answer rate and false-admission rate) |
| A13 | "Excellent in the demo, unreliable in production." | [watch](episodes/academy-a13-demo-vs-production/academy-a13-demo-vs-production.mp4) | [a13](labs/a13_demo_vs_production.py) | Experimental (held-out scoring; Evolution needs fresh families to promote) |
| A14 | "Every change breaks something, and we find out from customers." | [watch](episodes/academy-a14-every-change-breaks/academy-a14-every-change-breaks.mp4) | [a14](labs/a14_every_change_breaks.py) | Experimental (replay every flip before release; promotion is signed review) |

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
python docs/academy/labs/a1_right_document_wrong_answer.py     # any lab, from the repository root (A7 needs Pillow)
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
- A6–A8 use the Semantic Store research prototypes. Every research output stays `INCONCLUSIVE`:
  - A6: link candidates come only from explicit `RELATE` declarations.
  - A7: visual matches measure appearance and never identity. The reversed-arrow diagram scores distance 0.
  - A8: purpose contracts are not authenticated.
- The A8 policies are invented. They are not statements of law.
- A12–A14 use synthetic recorded cases. The labels stand for a reviewer's decision. Replay re-evaluates recorded evidence; it doesn't re-run retrieval or labelling.
- Career salary ranges and translations, which are part of the Dodo v4 template, are left out until sourced figures and reviewed translations exist.
