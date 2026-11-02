package io.qualityrag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

/** Checks supplied metadata against a policy, not the authenticity of its sources. */
public final class QualityRag {
    private static final ObjectMapper JSON = new ObjectMapper();
    private QualityRag() {}

    public static ObjectNode evaluate(JsonNode pack, JsonNode evidence, Instant asOf) {
        if (pack == null || !textPresent(pack, "id") || !textPresent(pack, "version")
                || !pack.path("requirements").isArray() || pack.path("requirements").isEmpty()
                || evidence == null || !evidence.isArray() || asOf == null) {
            throw new IllegalArgumentException("Invalid policy, evidence, or time");
        }
        Set<String> requirementIds = new HashSet<>();
        for (JsonNode req : pack.path("requirements")) {
            if (!textPresent(req, "id") || !requirementIds.add(req.get("id").asText())) {
                throw new IllegalArgumentException("Duplicate or invalid requirement ID");
            }
        }
        ArrayNode findings = JSON.createArrayNode();
        boolean refused = false, inconclusive = false;
        for (JsonNode req : pack.path("requirements")) {
            String id = req.get("id").asText();
            int minimum = 1;
            if (req.has("min_independent_sources")) {
                if (!req.get("min_independent_sources").isIntegralNumber()
                        || !req.get("min_independent_sources").canConvertToInt()) throw new IllegalArgumentException("Invalid minimum");
                minimum = req.get("min_independent_sources").intValue();
            }
            Long maxAge = null;
            if (req.has("max_age_seconds")) {
                if (!req.get("max_age_seconds").isIntegralNumber()
                        || !req.get("max_age_seconds").canConvertToLong()) throw new IllegalArgumentException("Invalid max age");
                maxAge = req.get("max_age_seconds").longValue();
            }
            if (minimum < 1 || (maxAge != null && maxAge < 0)) throw new IllegalArgumentException("Invalid thresholds");
            Set<String> origins = new HashSet<>(), reasons = new TreeSet<>();
            boolean contradicted = false;
            for (JsonNode row : evidence) {
                if (!id.equals(row.path("requirement_id").asText())) continue;
                if (!textPresent(row,"id") || !textPresent(row,"origin") || !textPresent(row,"source_ref")
                        || !textPresent(row,"observed_at")) {
                    reasons.add("INVALID_EVIDENCE"); continue;
                }
                String status = row.path("status").asText();
                if (!Set.of("SUPPORTS","CONTRADICTS","UNKNOWN").contains(status)) {
                    reasons.add("INVALID_EVIDENCE"); continue;
                }
                Instant observed;
                try { observed = Instant.parse(row.get("observed_at").asText()); }
                catch (DateTimeParseException e) { reasons.add("INVALID_EVIDENCE"); continue; }
                if (observed.isAfter(asOf)) { reasons.add("FUTURE_EVIDENCE"); continue; }
                if (maxAge != null && observed.isBefore(asOf.minusSeconds(maxAge))) {
                    reasons.add("STALE_EVIDENCE"); continue;
                }
                if (status.equals("CONTRADICTS")) contradicted = true;
                else if (status.equals("SUPPORTS")) origins.add(row.get("origin").asText());
                else reasons.add("UNKNOWN_EVIDENCE");
            }
            String verdict = contradicted ? "REFUSE" : origins.size() < minimum ? "INCONCLUSIVE" : "ADMIT";
            if (contradicted) reasons.add("CONTRADICTION");
            else if (origins.size() < minimum) reasons.add("INSUFFICIENT_INDEPENDENT_EVIDENCE");
            refused |= verdict.equals("REFUSE");
            inconclusive |= verdict.equals("INCONCLUSIVE");
            ObjectNode finding = findings.addObject();
            finding.put("requirement_id", id);
            finding.put("verdict", verdict);
            finding.put("independent_sources", origins.size());
            ArrayNode rs = finding.putArray("reasons");
            reasons.forEach(rs::add);
        }
        ObjectNode result = JSON.createObjectNode();
        result.put("schema", "qualityrag.result/v0.1");
        result.put("pack_id", pack.get("id").asText());
        result.put("pack_version", pack.get("version").asText());
        result.put("verdict", refused ? "REFUSE" : inconclusive ? "INCONCLUSIVE" : "ADMIT");
        result.set("findings", findings);
        return result;
    }

    public static ObjectNode evaluate(JsonNode pack, JsonNode evidence) {
        return evaluate(pack, evidence, Instant.now());
    }

    private static boolean textPresent(JsonNode node, String key) {
        return node != null && node.has(key) && node.get(key).isTextual() && !node.get(key).asText().isBlank();
    }
}
