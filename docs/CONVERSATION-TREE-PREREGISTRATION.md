# Conversation tree comparison — pre-registration (DRAFT, unsigned)

> **Status:** Draft for US-085. Not registered, not signed, not frozen. Every value marked **PROPOSED**
> is a placeholder for the owner to set before the gold set is opened. Nothing here has been run.

## Question

At a matched context budget, does a governed conversation tree with a conservation ledger and a
ledger-triggered read-back produce fewer stale-constraint violations and fewer dropped constraints than
loading the transcript or a summary of it?

## Arms

| Arm | Context given to the model | Runnable today |
|---|---|---|
| C0 | Whole transcript, newest turns first to the budget; also reported unbounded as a ceiling | Availability only |
| C1 | Summary compaction of the transcript | No: needs a summarizer |
| C2 | Turns in scope of the engine's current branch | Availability only |
| C3 | C2 plus the gate's required spans, read first | Availability only |
| C4 | C3 plus the differential branch test at each fork | No: needs model answers |
| D  | All spans residual (degenerate baseline) | Reported by the ledger as zero coverage |

Same model version, same budget and same latency ceiling for every arm.

## Endpoints

- **Primary 1 — stale-constraint violation rate:** answers at the final turn that follow a constraint a
  later user turn retired, over all retired constraints. Needs model answers and a judge independent of
  the system under test.
- **Primary 2 — dropped-constraint rate:** answers that fail to honor a constraint still binding at the
  final turn, over all binding constraints. Needs model answers.
- **Secondary, model-free:** constraint availability and retired-text exposure (`comparison.py`);
  unnecessary forks; user interruptions; false `INCONCLUSIVE`; words used; latency; cost.

Availability is necessary, not sufficient. It is never reported as a primary result.

## Hypotheses and decision rule

- **H1:** C3 has a lower stale-constraint violation rate than C0 at the matched budget.
- **H2:** C3 has a dropped-constraint rate no worse than C0 at the matched budget.
- Minimum practical effect for H1: **PROPOSED** 0.10 absolute. Non-inferiority margin for H2:
  **PROPOSED** 0.05 absolute.
- The claim advances only if the 95% interval for H1 excludes zero in the tree's favor and H2 holds.
- If C0 or C1 wins or ties at matched cost, that is the result and it is published.

## Data

- Gold set per US-084: **PROPOSED** at least 30 authorized long threads, two independent annotators,
  an expert for disagreements, frozen and fingerprinted before any system output is seen.
- Annotators mark, per user turn: the drift label, each constraint span, and whether the constraint is
  still binding on the answer to the final turn (`in_force_at_end`).
- Threads are split by source so that no thread used to tune the classifier or triggers is scored.
- Natural and injected cases are reported separately.

## Statistics

- Unit of analysis: (thread, constraint). Paired across arms on the same threads.
- Intervals: stratified bootstrap by thread. Multiple secondary endpoints corrected.
- Sample size: from a pilot estimate of the H1 effect, fixed before the holdout is opened.
- Stopping, exclusions and annotator-agreement threshold: **PROPOSED**, to be fixed by the owner.

## What would falsify the idea

- C0 matches or beats C3 on both primary endpoints whenever the transcript fits the budget.
- The fork rate or the `INCONCLUSIVE` rate makes the tree unusable at the cost ceiling.
- Trigger recall on the gold set is too low for the gate to protect unmarked constraints.
