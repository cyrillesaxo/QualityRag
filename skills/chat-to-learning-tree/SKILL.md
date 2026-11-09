---
name: chat-to-learning-tree
description: Convert a user-supplied AI chat into a provenance-preserving, FF-RCT candidate learning tree, with minimal PackSpecs and optional short lessons.
---
# Chat to learning tree (FF-RCT candidate)

## Trigger
Use when user requests ChatGPT/Claude conversation → learning tree, concept expansion, or a tree of shorts.

## Contract
1. Process only one expressly authorized thread. Never import unrelated conversations.
2. Preserve the original raw message order and text; store a SHA-256 fingerprint and message references. Do not mutate originals.
3. Generate the *smallest* root PackSpec: learning objective, essential claims, known exceptions, coverage status, and source obligations.
4. Propose at most 5 initial child concepts; distinguish prerequisite/support/exception links from expansion links. A tree is the navigation view over a potential DAG.
5. Treat chat claims as unverified. Use QualityRAG ADMIT / REFUSE / INCONCLUSIVE only after a real evidence gate; the baseline scanner always emits INCONCLUSIVE.
6. Model FF-RCT operations as bounded *candidate* transformations: identify concepts, retain critical distinctions, preserve provenance, record unresolved compression costs and epistemic uncertainty. Do not claim semantic equivalence, full grammar invention, or optimal compression.
7. Add a video only when a user activates a concept *and* its PackSpec and factual sources have been reviewed. Use an original 30–60 second short with an optional 5-card LexyRead Ladder.
8. Require explicit approval for consequential edits. Redact sensitive content before publication or shared reuse.

## Procedure
1. Load UTF-8 text or JSON messages from an explicitly selected source.
2. Run `python skills/chat-to-learning-tree/chat_to_tree.py thread.json --title "Topic" -o tree.json`. This yields a deterministic *candidate* seed, not semantic analysis.
3. Review each concept's source_message_ids, contradictions, implied claims, and missing exceptions. Amend the candidate graph with traceable review receipts.
4. Promote root and activated child PackSpecs only after approved QualityRAG evidence checks. Abstain on unresolved claims.
5. Produce an optional original storyboard and verify its statements before rendering any video.
6. Store comprehension outcomes; expand only requested or misunderstood concepts, subject to cost budget.

## Output
`ff-rct-learning-tree/candidate-v0.1` JSON: source hash, minimal root PackSpec, candidate nodes, source message IDs, typed edges, unresolved gaps, empty shorts queue.

## Integration
Balafons AI conversation import stores immutable source; this skill creates the candidate tree; QualityRAG gates promotion; LexyRead displays Ladder; the video composer renders activated nodes. No production integrations are implied by this skill.

## Acceptance
Deterministic baseline, finite branching, no invented source, no unsupported ADMIT, preserved conversation, and reviewable lineage.
