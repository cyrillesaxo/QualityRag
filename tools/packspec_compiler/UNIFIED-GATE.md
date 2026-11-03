# Unified QualityRag decision gate v0.1

**Research lineage:** Cyrille Eloundou — [APX](https://apx.guide/).

The unified gate combines existing QualityRag **evidence completeness** and **bounded deterministic semantic checks** under one **fail-closed generation point**. It does not pretend that supporting witness metadata proves claims true.

## Processing

~~~text
Approved source-grounded ConstraintIR
              |
              v
   Validate IR fingerprint and
   declared node inventory
              |
        +-----+------+
        |            |
 Evidence-presence  Temporal/probe
  obligations       + unsupported
        |            |
        v            v
 v0.1 metadata      Bounded semantic
   evaluator         runtime
        |            |
        +-----+------+
              |
 REFUSE > INCONCLUSIVE > ADMIT
              |
    Are all checks ADMIT?
            /    \
          no      yes
          |        |
       block    Host verifies
       model    source/witness/
                observation trust
                 /       \
               no         yes
               |           |
              block     May generate
~~~

The host attestation verifier is an explicit application integration point; **this repository cannot authenticate the supplied source files or observation metadata by itself**. Do not provide a verifier that always returns \`True\` in production.

## Python server-side example

From the repository root, with the compiler dependencies installed:

~~~python
import sys
sys.path.insert(0, "tools/packspec_compiler")
from unified_gate import guarded_generate

# ir = previously source-inspected and reviewer-mapped ConstraintIR
# witnesses = retrieved evidence with provenance identifiers
# observations = event timestamps and independently measured probe outputs

def verify_attestation(source, witnesses, observations):
    # Application-owned verifier: check source release approval and
    # cryptographic signatures / immutable logs for every witness
    # and observation used by the evaluation.
    # Return False on any missing/mismatched record.
    return enterprise_attestation_service.verify(source, witnesses, observations)

result = guarded_generate(
    ir, witnesses, observations, "2026-11-02T10:05:00Z",
    generator=lambda: chat_client.complete(prompt),
    verify_attestation=verify_attestation,
)
if not result["generated"]:
    # Surface the evidence/semantic blockers to the user.
    return result["decision"]
return result["answer"]
~~~

\`enterprise_attestation_service\` is an **illustrative host integration dependency**, not included in this repository. Until a trusted verifier is implemented, the gate returns \`INCONCLUSIVE\` and does not generate.

## Decision rules

| Evidence gate | Semantic runtime | Host attestation | Unified verdict | Generate? |
| --- | --- | --- | --- | --- |
| ADMIT | ADMIT | Validated | ADMIT | Yes |
| ADMIT | ADMIT | Missing/false/exception | INCONCLUSIVE | No |
| ADMIT | INCONCLUSIVE | Any | INCONCLUSIVE | No |
| INCONCLUSIVE | ADMIT | Any | INCONCLUSIVE | No |
| REFUSE | Any | Any | REFUSE | No |
| Any | REFUSE | Any | REFUSE | No |

If a checked subsystem has **no applicable nodes**, it is labeled \`NOT_APPLICABLE\` rather than pretending to have passed an obligation. An IR must still have at least one node. Unimplemented \`AUTHORITY\` or \`PREDICATE\` nodes are routed to the semantic runtime and remain \`INCONCLUSIVE\`. The gate never deletes those nodes merely to secure an \`ADMIT\`.

A failed or unverified attestation never overrides a \`REFUSE\`; no attestation callback is invoked until the specified evidence and semantic checks pass.

## Critical boundaries

- The gate validates the *shape*, local fingerprint, reviewed-node flags and IR inventory. These are not cryptographic signatures or authenticated reviewer identities.
- The evidence SDK counts distinct \`origin\` strings. This is not reliable independence or provenance attestation.
- The semantic runtime compares supplied timestamps and values. It does not run probes or establish the integrity of an event log.
- The host's attestation verifier must validate all inputs the decision relies upon. Its return value is a trust boundary controlled by the integrating application.
- Calling \`evaluate_unified\` directly returns a decision receipt; only \`guarded_generate\` is a wrapper around the supplied answer generator. Application code can still bypass the wrapper unless it deliberately enforces the architecture.
- \`ADMIT\` means specified, supported checks passed and the host verifier accepted the inputs. It does not establish that the original APX PackSpec was completely recovered or that every regulatory/learning/business claim is correct.
- No network access, credential issuance, or signing of PackSpecs is performed by this Python module.

## Verification

~~~bash
python -m pip install -r tools/packspec_compiler/requirements.txt
python -m unittest discover -s tools/packspec_compiler/tests -p 'test_*.py'
~~~

The tests cover mixed ADMIT, REFUSE and INCONCLUSIVE outcomes; host attestation absent, false or raising errors; deferred authority; IR tampering and source mismatch; all-evidence or all-semantic IR; and proof that the generator is called only on full admission.

**Next engineering milestone:** implement real attestation adapters and signed canonical PackSpec bundles, then move the unified gate into the language SDKs and Spring Boot answer generation integration.
