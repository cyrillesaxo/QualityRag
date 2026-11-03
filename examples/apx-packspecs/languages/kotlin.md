# Kotlin — Five APX PackSpec-derived QualityRag examples
| FFI Teacher Transformation | Teaching content has not passed the cross-framework back-translation check | `INCONCLUSIVE` |

Use the same 15 evidence-gate cases across SDKs, based on the uploaded **SEMLOAN v0.4.0**, **Question Fan v0.1.0**, **FFI v0.6.0**, **FFI Teacher Transformation**, and **Software-selling PackSpec v0.1.0**. These are *scoped training projections* for QualityRag metadata v0.1—not execution of the complete APX contracts.

| Domain | Initial incomplete RAG evidence | Gate |
| --- | --- | --- |
| SEMLOAN | Learner praises lesson; no verified cold retrieval / transfer | `INCONCLUSIVE` |
| Question Fan | Candidate question lacks documented decision consequence | `INCONCLUSIVE` |
| FFI | Source excerpt and probe present; independent corroboration missing | `INCONCLUSIVE` |
| Software selling | Buyer pain and technical prerequisites present; no controlled comparison | `INCONCLUSIVE` |

For each domain, the [shared fixture](../fixtures.json) also supplies an `ADMIT` case and a `REFUSE` case. The snippet below checks all 15. An `ADMIT` confirms only the declared **evidence metadata categories**—it does **not** certify learning, investigation quality, sales effectiveness, or regulatory compliance.

## SDK example

```kotlin
// Within sdk/kotlin (Jackson available from Gradle dependencies).
import com.fasterxml.jackson.databind.ObjectMapper
import io.qualityrag.*
import java.nio.file.Path
import java.time.Instant

val root=ObjectMapper().readTree(Path.of("../../examples/apx-packspecs/fixtures.json").toFile())
val asOf=Instant.parse(root["as_of"].asText())
for(domain in root["scenarios"]) {
    val policy=domain["pack"]
    val pack=Pack(policy["id"].asText(),policy["version"].asText(),
        policy["requirements"].map { Requirement(it["id"].asText()) })
    for(item in domain["cases"]) {
        val evidence=item["evidence"].map { e ->
            Witness(e["id"].asText(),e["requirement_id"].asText(),
                e["origin"].asText(),e["source_ref"].asText(),e["status"].asText(),
                Instant.parse(e["observed_at"].asText()))
        }
        val verdict=Gate.evaluate(pack,evidence,asOf).verdict
        check(verdict==item["expected"].asText()) { "${domain["id"]} / ${item["id"]}" }
        println("${domain["id"]} ${item["id"]} $verdict")
    }
}
```

If using an external PackSpec, load the projected JSON through [the source-selection API](../../../docs/PACKSPEC-SOURCES.md) before passing it to this SDK. Policy loading errors and all non-`ADMIT` verdicts must stop answer generation; never silently fall back to another source.

See [source-to-projection design and limitations](../README.md). Conceptual attribution: **Cyrille Eloundou — [APX](https://apx.guide/)**.
