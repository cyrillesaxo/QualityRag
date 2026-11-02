package io.qualityrag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.*;

/** Experimental bounded ConstraintIR + WitnessGraph + Wgap evaluator.
 * Caller-provided origin and authority labels are NOT independently verified.
 */
public final class SemanticCompiler {
 private static final ObjectMapper M = new ObjectMapper();
 private SemanticCompiler() {}
 public static ObjectNode compile(JsonNode pack) {
  if(pack==null || !nonempty(pack,"id") || !nonempty(pack,"version") ||
      !pack.path("requirements").isArray() || pack.path("requirements").isEmpty())
   throw new IllegalArgumentException("Invalid PackSpec");
  ObjectNode ir=M.createObjectNode();ir.put("pack_id",pack.path("id").asText());ir.put("version",pack.path("version").asText());
  ArrayNode obligations=ir.putArray("obligations");Set<String> ids=new HashSet<>();
  for(JsonNode r:pack.path("requirements")){
   if(!nonempty(r,"id")||!ids.add(r.path("id").asText()))throw new IllegalArgumentException("Invalid/duplicate requirement");
   int min=1; if(r.has("min_independent_sources")){
    if(!r.path("min_independent_sources").isIntegralNumber()||!r.path("min_independent_sources").canConvertToInt())
     throw new IllegalArgumentException("Invalid minimum");
    min=r.path("min_independent_sources").intValue();
   }
   Long max=null;
   if(r.has("max_age_seconds")){
    if(!r.path("max_age_seconds").isIntegralNumber()||!r.path("max_age_seconds").canConvertToLong())
     throw new IllegalArgumentException("Invalid freshness");
    max=r.path("max_age_seconds").longValue();
   }
   String scope=r.has("scope")?r.path("scope").asText():"global";
   String authority=r.has("authority")?r.path("authority").asText():null;
   if(min<1||(max!=null&&max<0)||scope.isBlank()||(authority!=null&&authority.isBlank()))
    throw new IllegalArgumentException("Invalid obligation");
   ObjectNode o=obligations.addObject();o.put("requirement_id",r.path("id").asText());o.put("min_origins",min);
   if(max==null)o.putNull("max_age_seconds");else o.put("max_age_seconds",max);
   o.put("required_scope",scope);
   if(authority==null)o.putNull("required_authority");else o.put("required_authority",authority);
  }
  return ir;
 }
 public static ObjectNode evaluate(JsonNode pack,JsonNode evidence,Instant now) {
  if(evidence==null||!evidence.isArray()||now==null)throw new IllegalArgumentException("Invalid evidence or time");
  ObjectNode ir=compile(pack),out=M.createObjectNode();
  ArrayNode findings=out.putArray("findings"), nodes=M.createArrayNode(),groups=M.createArrayNode(),gaps=out.putArray("wgap");
  Map<String,List<String>> dependencies=new TreeMap<>();
  boolean refused=false,inconclusive=false;
  for(JsonNode o:ir.path("obligations")){
   String rid=o.path("requirement_id").asText(),scope=o.path("required_scope").asText();
   String authority=o.path("required_authority").isNull()?null:o.path("required_authority").asText();
   long max=o.path("max_age_seconds").isNull()?-1:o.path("max_age_seconds").longValue();
   int min=o.path("min_origins").intValue();
   Set<String> origins=new HashSet<>(),reasons=new TreeSet<>();boolean contradiction=false;
   for(JsonNode w:evidence){
    if(!rid.equals(w.path("requirement_id").asText()))continue;
    if(!nonempty(w,"id")||!nonempty(w,"origin")||!nonempty(w,"source_ref")||!nonempty(w,"observed_at")||
      !Set.of("SUPPORTS","CONTRADICTS","UNKNOWN").contains(w.path("status").asText())){
     reasons.add("INVALID_WITNESS");continue;
    }
    Instant observed;
    try {observed=Instant.parse(w.path("observed_at").asText());}
    catch(DateTimeParseException ex){reasons.add("INVALID_WITNESS");continue;}
    String origin=w.path("origin").asText();
    ObjectNode node=nodes.addObject();node.put("id",w.path("id").asText());node.put("origin",origin);node.put("requirement_id",rid);
    dependencies.computeIfAbsent(rid+"\u0000"+origin,k->new ArrayList<>()).add(w.path("id").asText());
    if(observed.isAfter(now)){reasons.add("FUTURE_WITNESS");continue;}
    if(max>=0&&observed.isBefore(now.minusSeconds(max))){reasons.add("STALE_WITNESS");continue;}
    if(!scope.equals(w.has("scope")?w.path("scope").asText():"global")){reasons.add("SCOPE_MISMATCH");continue;}
    if(authority!=null&&!authority.equals(w.path("authority").asText())){reasons.add("AUTHORITY_MISMATCH");continue;}
    switch(w.path("status").asText()){
     case "CONTRADICTS" -> contradiction=true;
     case "SUPPORTS" -> origins.add(origin);
     default -> reasons.add("UNKNOWN_WITNESS");
    }
   }
   String decision=contradiction?"REFUSE":origins.size()<min?"INCONCLUSIVE":"ADMIT";
   if(contradiction)reasons.add("CONTRADICTION");else if(origins.size()<min)reasons.add("INSUFFICIENT_INDEPENDENT_EVIDENCE");
   if(decision.equals("REFUSE"))refused=true;else if(decision.equals("INCONCLUSIVE"))inconclusive=true;
   ObjectNode f=findings.addObject();f.put("requirement_id",rid);f.put("verdict",decision);
   f.put("independent_sources",origins.size());f.put("missing_sources",Math.max(0,min-origins.size()));
   ArrayNode rs=f.putArray("reasons");reasons.forEach(rs::add);
   if(!decision.equals("ADMIT")){
    ObjectNode gap=gaps.addObject();gap.put("requirement_id",rid);gap.put("missing_sources",Math.max(0,min-origins.size()));
    ArrayNode gr=gap.putArray("reasons");reasons.forEach(gr::add);
   }
  }
  dependencies.forEach((key,ids)->{
   if(ids.size()<2)return;
   int split=key.indexOf('\u0000');ObjectNode group=groups.addObject();
   group.put("requirement_id",key.substring(0,split));group.put("origin",key.substring(split+1));
   ArrayNode witnessIds=group.putArray("witness_ids");ids.stream().sorted().forEach(witnessIds::add);
  });
  ObjectNode graph=M.createObjectNode();graph.set("nodes",nodes);graph.set("dependent_groups",groups);
  out.put("schema","qualityrag.compiled-result/v0.1");out.put("pack_id",pack.path("id").asText());
  out.put("pack_version",pack.path("version").asText());out.put("verdict",refused?"REFUSE":inconclusive?"INCONCLUSIVE":"ADMIT");
  out.set("constraint_ir",ir.path("obligations"));out.set("witness_graph",graph);
  return out;
 }
 private static boolean nonempty(JsonNode n,String k){return n!=null&&n.path(k).isTextual()&&!n.path(k).asText().isBlank();}
}
