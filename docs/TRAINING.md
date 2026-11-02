# QualityRag Training: Why It Exists, What It Does, and When to Use It

**Audience:** application developers, Java/Spring Boot architects, RAG engineers, technical reviewers, and policy owners  
**Level:** beginner → intermediate · **Time:** approximately 25–35 minutes  
**Scope:** experimental QualityRag metadata gate and the Java/Python/TypeScript semantic compiler prototype

> **Key idea:** A retrieved passage can be accurate and relevant yet still be **insufficient to justify an answer**. Retrieval success is not evidence completeness.

## Learning outcomes

After this lesson, you should be able to:
1. Explain the difference between *having a source*, *having relevant evidence*, and *satisfying all governing requirements*.
2. Identify five ways an apparently plausible RAG answer can be unjustified.
3. Model evidence obligations as a versioned PackSpec and interpret `ADMIT`, `REFUSE`, and `INCONCLUSIVE`.
4. Recognize what the current implementation **does not** verify.
5. Gate generation in application code and identify what additional evidence is needed.

## 1. The problem: plausible answers are not always justified

A typical retrieval-augmented generation (RAG) pipeline is:

```text
User question → retrieval → selected passages → language model → answer
```

Retrieval can return genuine, relevant passages. But *relevance* does not establish that all applicable conditions were retrieved. A response may omit an exception, mix jurisdictions, cite obsolete rules, count copies as corroboration, or silently promote an unverified claim to fact.

For high-consequence workflows, asking the model to “be careful” is insufficient as an **enforcement mechanism**: the application needs explicit conditions that can stop answer generation when required evidence is not established. QualityRag adds this *policy gate*:

```text
Question + declared PackSpec → required evidence obligations
Retrieved evidence + provenance metadata → QualityRag evaluation
                         ├─ ADMIT        → application may generate (other safeguards still apply)
                         ├─ REFUSE       → do not generate; show governing contradiction
                         └─ INCONCLUSIVE → do not generate; show missing evidence / Wgap
```

This is complementary to retrieval improvements, citations, model evaluation, and human review—not a replacement for them.

## 2. Realistic enterprise case: RAG over a large, unstructured document estate

**Scenario (synthetic):** A global bank's internal assistant answers operational questions from a corpus of **85,000 files**: PDFs, scanned procedures, intranet HTML pages, exported email threads, incident postmortems, Word runbooks, and compliance appendices. The numbers, documents, policy rules, and retrieval results in this lesson are **illustrative**, not measurements of a real deployment.

**User asks:** *“Can our on-call team automatically restore the EU payments gateway after a failed sanctions-screening dependency, or do we need approval?”*

### The underlying documents are not conveniently structured

| Source in the corpus | Example passage | Retrieval difficulty |
| :--- | :--- | :--- |
| **Payments Operations Handbook**, 240-page PDF, §7.3 | “On-call staff may initiate automated recovery after a dependency timeout.” | Highly relevant semantic match |
| **EU Financial Controls Annex**, scanned PDF, Appendix D, p. 187 | “Where a sanctions-screening dependency is unavailable, restoration requires compliance sign-off unless the documented emergency exception applies.” | Scanned appendix; depends on OCR quality; weak keyword match |
| **Incident INC-7421**, HTML postmortem | “Automated recovery reduced downtime during a gateway outage.” | Strong similarity; incident history is not governing approval |
| **2024 Runbook**, Word export | “Restart the gateway once the upstream connection stabilizes.” | Outdated revision competes with current handbook |
| **Regional Change Memo**, email archive | “The EU approval rule supersedes the generic recovery flow for screening outages.” | Buried in a message thread, potentially duplicate forwards |

The application retrieves and chunks this corpus, embeds the text, performs vector/hybrid search, reranks matches and sends selected snippets to an LLM. **The model usually sees only a tiny fraction of the total corpus.**

### Path A — RAG without explicit completeness governance

Illustrative top-ranked passages returned by the retriever:

```text
Rank  Score  Source                                 Extract
 1    .92   Payments Operations Handbook §7.3      "On-call may initiate automated recovery..."
 2    .88   Incident INC-7421                       "Automated recovery reduced downtime..."
 3    .86   2024 Runbook                            "Restart once upstream stabilizes..."
 4    .80   Mirrored handbook excerpt              "Automated recovery..."
```

**Missing from the model's context:** the EU Financial Controls Annex and superseding change memo.

A plausible but unsupported model answer is:

> “Yes. On-call can automatically restart the gateway following the dependency failure, consistent with the operations handbook.”

This answer can cite genuine documents and still be **operationally unsafe** because it omits the controlling regional exception. This is a *possible* failure, not a claim that all ordinary RAG systems fail.

### Path B — Same retrieval, with QualityRag

A domain owner uses QualityRag Studio to define a server-owned PackSpec for the decision category `eu-payments-screening-recovery`:

```json
{
  "id": "eu-payments-screening-recovery",
  "version": "1.0",
  "requirements": [
    {"id": "recovery-procedure", "min_independent_sources": 1},
    {"id": "eu-screening-control", "min_independent_sources": 1},
    {"id": "applicable-approval-or-exception", "min_independent_sources": 1}
  ]
}
```

The metadata builder maps verified retrieval candidates to obligations. It must not mark an obligation `SUPPORTS` merely because a passage mentions relevant words; the metadata builder itself needs trusted source validation and a correct requirement match.

```text
Question
  ↓
Vector/hybrid retrieval over 85,000 unstructured files
  ↓
Chunks 1–4 retrieved, all about generic recovery
  ↓
QualityRag checks declared evidence obligations:
  recovery-procedure                SATISFIED
  eu-screening-control              MISSING
  applicable-approval-or-exception  MISSING
  ↓
INCONCLUSIVE
  ↓
Application withholds the answer and asks for the annex /
compliance approval evidence; optionally launches targeted retrieval
```

The base evaluator **does not automatically search again**; targeted re-retrieval is a responsibility of the surrounding application. The experimental semantic compiler can expose missing declared obligations as `Wgap`.

### Reproducible synthetic document corpus and retrieval fixture

The repository now contains a [six-document training corpus](../examples/enterprise-rag/corpus.json), an [executable retrieval simulation](../examples/enterprise-rag/demo.py), and [regression tests](../examples/enterprise-rag/test_demo.py). The corpus represents PDF, scanned-PDF, Word, HTML, and email formats **as JSON metadata and text excerpts**; it does not contain real binary files or run OCR, vector embedding, or a production retriever.

```bash
PYTHONPATH=sdk/python python examples/enterprise-rag/demo.py
PYTHONPATH=sdk/python python -m unittest discover -s examples/enterprise-rag -p 'test_*.py'
```

The first scripted retrieval returns only the generic recovery rule, incident history, outdated runbook, and a mirror of the handbook. The gate returns `INCONCLUSIVE` for two missing requirements. The second scripted retrieval supplies the annex and memo; the metadata gate returns `ADMIT`, **which is not operational permission to restart the gateway**. Verification of the approval reference, source authenticity, and correct policy applicability are additional necessary controls.

### Working SDK simulation: retrieval returned too little

From the repository root:

```bash
PYTHONPATH=sdk/python python - <<'PY'
from qualityrag import evaluate

pack = {
    "id": "eu-payments-screening-recovery",
    "version": "1.0",
    "requirements": [
        {"id": "recovery-procedure"},
        {"id": "eu-screening-control"},
        {"id": "applicable-approval-or-exception"}
    ],
}
# Simplified metadata extracted from the four *retrieved* chunks.
# No governing EU control or approval exception was retrieved.
evidence = [{
    "id": "handbook-chunk-7.3",
    "requirement_id": "recovery-procedure",
    "origin": "ops-handbook-current",
    "source_ref": "pdf:ops-handbook#page=74",
    "status": "SUPPORTS",
    "observed_at": "2026-11-02T10:00:00Z",
}]
result = evaluate(pack, evidence, as_of="2026-11-02T10:05:00Z")
assert result["verdict"] == "INCONCLUSIVE"
for item in result["findings"]:
    print(item["requirement_id"], item["verdict"])
PY
```

Expected output:

```text
recovery-procedure ADMIT
eu-screening-control INCONCLUSIVE
applicable-approval-or-exception INCONCLUSIVE
```

This is a **deterministic metadata-gating demonstration**, not a running vector database, OCR pipeline, or generative model benchmark.

### What happens after targeted retrieval?

Imagine a second retrieval finds the annex and memo. The application still must establish applicability and source authority: Is the annex effective for **this EU gateway, this outage category, and this time**? Does the emergency exception apply? Does a newer revision supersede the memo?

A document's existence is not enough; the **correct governing interpretation** may depend on cross-document references and precedence. This is why the larger roadmap includes constraint extraction, authority/scope resolution, deceptive-witness challenges and governed policy authoring.

### Why the policy belongs outside the application

| Application-owned logic | QualityRag Studio + external policy |
| :--- | :--- |
| Each service encodes its own approval checks | Domain owners maintain versioned obligations centrally |
| Rule changes require redeployment or manual coordination | Registry can bind approved revisions to services/environments |
| Coverage differs between Java/Python/etc. implementations | Shared policy intent; SDKs still need cross-language semantic parity |
| Difficult to know which revision was used | Registry records binding and digest; production-grade signing is future work |

**Critical boundary:** QualityRag v0.1 can only report omissions against **requirements that somebody declared**. It cannot currently discover every hidden constraint across 85,000 unstructured documents, authenticate the documents, or prove that a PackSpec is complete. The Studio/registry is a development prototype, not yet a production governance service.

### What this example establishes—and what it does not

- **Establishes:** an incomplete retrieved context can be blocked when a declared obligation has no supporting evidence.
- **Does not establish:** better semantic retrieval, automated discovery of every governing exception, correct parsing of scanned PDFs, source truth, or improved accuracy at a measured rate.
- **Practical evaluation:** build a labeled corpus with known exceptions; measure unsafe admissions, appropriate abstentions, latency, and policy authoring burden against a well-configured conventional RAG baseline.

---

## 3. Five worked examples

All scenarios below are **fictional training examples**. They are *not* actual medical, employment, eligibility, financial, or legal rules.

### Example A — The hidden exception

**Question:** “Does the applicant qualify?”

**Retrieved passage:** “Applicants who complete the core application qualify.”

**Additional governing rule:** “Applicants must also provide an up-to-date identity-verification document.”

**Naive failure:** A system answers “Yes” using the true but incomplete core rule.

**QualityRag contract:** The policy owner declares two obligations, `core-rule` and `verification-exception`. The first has evidence; the second does not.

**Result:** `INCONCLUSIVE` with an unresolved `verification-exception` obligation.

**Why it matters:** Correct citation of the broad rule is not proof that required exceptions have been evaluated.

**Important limit:** The current implementation cannot automatically discover an exception that nobody declared in the PackSpec. That requires policy authoring, retrieval checks, and future semantic machinery.

### Example B — Two documents, one origin

**Question:** “Has this product requirement been independently confirmed?”

**Evidence:** Doc A and Doc B both repeat a statement from the same bulletin.

**Naive failure:** The application treats two retrieved documents as two independent confirmations.

**PackSpec:** `min_independent_sources: 2`.

**Result:** `INCONCLUSIVE` because both witness records have the **same declared origin**.

**Why it matters:** More citations do not necessarily mean more independent evidence.

**Limit:** Caller-provided origin strings must themselves be verified upstream. Two different labels could still conceal a common source.

### Example C — An outdated source

**Question:** “What is the current version of this process?”

**Evidence:** A document supports the policy but was last observed outside the permitted 24-hour freshness window.

**PackSpec:** `max_age_seconds: 86400`.

**Result:** `INCONCLUSIVE` with `STALE_EVIDENCE` and insufficient current support.

**Why it matters:** Historical accuracy does not automatically justify a claim about the present.

**Limit:** `observed_at` is a timestamp supplied by the evidence collector, not independent proof that the underlying facts are current.

### Example D — A governing contradiction

**Question:** “Can this operation proceed?”

**Evidence:** One governing record supports the operation, while another applicable record contradicts it.

**Result:** `REFUSE` with `CONTRADICTION`, even if there are enough supporting origins.

**Why it matters:** Counting supporting documents cannot erase an unresolved governing contradiction.

**Limit:** Scope and authority must be established; an irrelevant, fabricated, or out-of-scope contradiction should not silently become a governing fact.

### Example E — Wrong scope, convincing answer

**Question:** “Is the requirement satisfied in Region B?”

**Evidence:** The retrieved record applies only to Region A.

**Extended PackSpec:** A requirement with `scope: "Region-B"`.

**Result:** The experimental Java/Python/TypeScript semantic compiler reports `SCOPE_MISMATCH` and `INCONCLUSIVE`.

**Why it matters:** Transferring a valid rule into the wrong jurisdiction, actor, timeframe, or product can invalidate the conclusion.

**Limit:** The base v0.1 gate in all ten languages does not yet enforce the extended scope field; use the extended compiler where available.

## 3. Hands-on lab — duplicate provenance

Create this PackSpec:

```json
{
  "id": "training.duplicate-origin",
  "version": "1",
  "requirements": [
    {
      "id": "independent-confirmation",
      "min_independent_sources": 2,
      "max_age_seconds": 3600
    }
  ]
}
```

And provide these two witness records:

```json
[
  {
    "id": "doc-1",
    "requirement_id": "independent-confirmation",
    "origin": "bulletin-A",
    "source_ref": "example:bulletin-A:copy-1",
    "status": "SUPPORTS",
    "observed_at": "2026-11-02T10:00:00Z"
  },
  {
    "id": "doc-2",
    "requirement_id": "independent-confirmation",
    "origin": "bulletin-A",
    "source_ref": "example:bulletin-A:copy-2",
    "status": "SUPPORTS",
    "observed_at": "2026-11-02T10:00:00Z"
  }
]
```

Run this example from the repository root:

```bash
PYTHONPATH=sdk/python python - <<'PY'
from qualityrag import evaluate

pack = {
    "id": "training.duplicate-origin", "version": "1",
    "requirements": [
        {"id": "independent-confirmation",
         "min_independent_sources": 2, "max_age_seconds": 3600}
    ]
}
evidence = [
    {"id": "doc-1", "requirement_id": "independent-confirmation",
     "origin": "bulletin-A", "source_ref": "example:bulletin-A:copy-1",
     "status": "SUPPORTS", "observed_at": "2026-11-02T10:00:00Z"},
    {"id": "doc-2", "requirement_id": "independent-confirmation",
     "origin": "bulletin-A", "source_ref": "example:bulletin-A:copy-2",
     "status": "SUPPORTS", "observed_at": "2026-11-02T10:00:00Z"}
]
result = evaluate(pack, evidence, as_of="2026-11-02T10:05:00Z")
assert result["verdict"] == "INCONCLUSIVE"
print(result)
PY
```

**Experiment:** Replace the second witness's declared origin with `bulletin-B`. The evaluator now returns `ADMIT` *under the supplied metadata*. Ask yourself: who verified that Bulletin B was genuinely independent? That check belongs upstream.

## 4. What “admission” actually means

| Decision | Meaning | Recommended behavior |
| :--- | :--- | :--- |
| `ADMIT` | Declared metadata obligations are satisfied | Proceed only if all other application safeguards allow it |
| `REFUSE` | A governing contradiction is recorded | Block the answer and expose bounded reasons |
| `INCONCLUSIVE` | At least one required obligation is unresolved | Block the answer and request targeted evidence |

**Never interpret ADMIT as “the answer is true.”** It does not certify facts, ensure an exhaustive PackSpec, or evaluate the final generated answer.

## 5. Why not rely on RAG improvements alone?

| Technique | Useful for | What it does not guarantee |
| :--- | :--- | :--- |
| Better chunking / search | Finding relevant passages | Every governing exception has been retrieved |
| Reranking | Prioritizing likely relevant passages | Independent source provenance |
| Prompt instructions | Influencing generation style | Deterministic refusal when evidence is incomplete |
| Citations | Showing where a statement came from | Scope, freshness, or completeness of justification |
| LLM-as-judge | Evaluating candidate answers | A reproducible, source-authenticated policy decision |
| **QualityRag** | Enforcing *declared* evidence requirements before generation | Automatically discovering unknown policies or proving source truth |

QualityRag is most useful where a wrong-but-plausible answer has a meaningful cost and the required evidence can be expressed explicitly.

## 6. When QualityRag is a good fit

Consider using it for governed knowledge assistants, enterprise decision-support, regulated operational procedures, audit support, approval workflows, and retrieval systems that need traceable reasons for abstaining.

For low-stakes creative writing or casual chat, a pre-generation policy gate may add more complexity than value. Adoption should follow measured false-admission risk, policy coverage, operator cost, and latency—not a generic claim that every RAG system needs this software.

## 7. Current implementation vs roadmap

| Capability | Available today? |
| :--- | :--- |
| Metadata evidence checks and three-way decisions | Yes: all ten SDK foundations |
| Shared v0.1 conformance scenarios | Yes |
| Scope/authority-labeled ConstraintIR, WitnessGraph groups, Wgap | Experimental: Java, Python, TypeScript |
| Spring Boot answer gate | Yes |
| Central QualityRag Studio and local service/policy registry | Yes, local development prototype |
| Java remote-policy resolution | Under review in PR #12 |
| Automatic unknown-exception discovery | No |
| Full APX deceptive-witness D15, G1–G12, HCR and semantic completeness proof | No |
| Independently authenticated source provenance | No |
| Production-ready signed central policy distribution | No |

## 8. Knowledge check

1. Three web pages quote the same official bulletin. Do you have three independent origins? **No, not necessarily.**
2. The general rule is correct but a declared exception has not been retrieved. What is the verdict? **INCONCLUSIVE.**
3. One valid governing witness contradicts three supporting witnesses. What is the verdict? **REFUSE.**
4. Is an `ADMIT` decision proof that the final LLM answer is correct? **No.**
5. Does a PackSpec automatically know all relevant exceptions? **No; policy completeness must be established separately.**

## Research lineage and attribution

This training builds on semantic governance and PackSpec ideas associated with **Cyrille Eloundou** and the **APX project** ([apx.guide](https://apx.guide/)). APX addresses intent and constraint verification across software systems; QualityRag experiments with explicit evidence obligations before RAG answer generation. The approaches are related, but their implementations and validation status differ.

**Reference:** Cyrille Eloundou, *APX: semantic governance and PackSpec concepts*, project website: https://apx.guide/. This is a **project reference**, not a peer-reviewed citation or empirical proof that QualityRag improves RAG correctness.

## Continue learning

- [Main documentation](README.md)
- [Quickstart](quickstart.md)
- [Concepts and reason codes](concepts.md)
- [APX-inspired architecture](ADR-0001-semantic-constraint-compiler.md)
- [Standalone Studio / registry](STUDIO-REGISTRY.md)
- [Cross-language fixtures](CONFORMANCE.md)
