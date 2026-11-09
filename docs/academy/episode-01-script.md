# Episode 01 — Your first evidence gate
Target: 4 minutes. Narrator: clear and conversational, no synthetic fallback.

**0:00 Hook** — You can retrieve the right document and still provide an answer nobody should trust. One relevant passage might omit an exception. And two documents might actually come from the same source. Let's run a real evidence gate.

**0:25 Setup** — Open QualityRag. This is an experimental deterministic metadata evaluator, not an LLM and not a source-authentication service. From the repository root, run: `PYTHONPATH=sdk/python python examples/python_demo.py`.

**0:55 Show the PackSpec** — This contract requires two independent sources and a one-day observation window. We declared these conditions before seeing the answer.

**1:25 First lab case** — Run `PYTHONPATH=sdk/python python docs/academy/episode-01-lab.py`. One witness? Inconclusive.

**1:55 Same-origin duplicates** — Two documents can be copies of one bulletin. Still one declared origin. Still inconclusive.

**2:25 Independent origins** — A second distinct origin changes the metadata verdict to ADMIT. It does NOT prove either source is authentic or correct.

**2:55 Contradiction** — A contradictory witness causes REFUSE under these declared rules. Supporting text cannot override it.

**3:20 Exercise** — Change the required count from two to three. Predict the outcome. Then reduce max age and examine reasons.

**3:45 Close** — Next we move from a generic count to a realistic missing policy exception using the enterprise RAG fixture. QualityRag is open source at github.com/cyrillesaxo/QualityRag.

**Video integrity:** Show terminal output from an actual run, with on-screen captions. Final MP4 is accepted only after verifying audible natural narration and synchronization.
