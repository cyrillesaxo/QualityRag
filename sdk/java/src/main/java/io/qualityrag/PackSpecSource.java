package io.qualityrag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Objects;

/** Explicit choice of policy authority. No implicit fallback across sources. */
@FunctionalInterface
public interface PackSpecSource {
  JsonNode load();

  static PackSpecSource internal(JsonNode policy) {
    var verified = checked(policy);
    return () -> verified.deepCopy();
  }

  /** Caller-supplied property containing the full JSON PackSpec. Never logs secrets. */
  static PackSpecSource property(String json) {
    if(json == null || json.isBlank()) throw new IllegalArgumentException("PackSpec property absent");
    try {
      return internal(new ObjectMapper().readTree(json));
    } catch(IOException e) { throw new IllegalArgumentException("Invalid PackSpec property",e); }
  }

  /** External file: read each time, to avoid persisting a stale implicit fallback. */
  static PackSpecSource file(Path path) {
    Objects.requireNonNull(path,"path");
    return () -> {
      try {
        if(Files.size(path) > 262_144) throw new IllegalStateException("Policy file too large");
        return checked(new ObjectMapper().readTree(Files.readString(path)));
      } catch(IOException e) {throw new IllegalStateException("Policy file unavailable",e);}
    };
  }

  /** Local development registry client; shared operator token is NOT production service authentication. */
  static PackSpecSource studio(URI registry, String token, String serviceId, String environment) {
    Objects.requireNonNull(registry,"registry");
    if(!"https".equalsIgnoreCase(registry.getScheme()) &&
       !("http".equalsIgnoreCase(registry.getScheme()) &&
         ("localhost".equalsIgnoreCase(registry.getHost()) || "127.0.0.1".equals(registry.getHost()))))
      throw new IllegalArgumentException("HTTPS required outside loopback");
    if(token == null || token.isBlank()) throw new IllegalArgumentException("Registry credential required");
    if(!validSegment(serviceId) || !validSegment(environment)) throw new IllegalArgumentException("Invalid service/environment");
    var http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    var mapper=new ObjectMapper();
    URI endpoint=registry.resolve("/v1/resolve/"+serviceId+"/"+environment);
    return () -> {
      try {
        var request=HttpRequest.newBuilder(endpoint).timeout(Duration.ofSeconds(5))
            .header("Authorization","Bearer "+token).header("Accept","application/json").GET().build();
        var response=http.send(request,HttpResponse.BodyHandlers.ofString());
        if(response.statusCode()!=200 || response.body().length()>262_144) throw new IllegalStateException("Registry resolution failed");
        var envelope=mapper.readTree(response.body());
        if(!"APPROVED".equals(envelope.path("status").asText()) ||
           !serviceId.equals(envelope.path("serviceId").asText()) ||
           !environment.equals(envelope.path("environment").asText()))
           throw new IllegalStateException("Registry binding mismatch");
        var policy=checked(envelope.path("policy"));
        var expected=envelope.path("sha256").asText();
        if(!expected.matches("[a-f0-9]{64}")) throw new IllegalStateException("Missing policy digest");
        var actual=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(mapper.writeValueAsBytes(policy)));
        if(!MessageDigest.isEqual(expected.getBytes(StandardCharsets.US_ASCII),actual.getBytes(StandardCharsets.US_ASCII)))
          throw new IllegalStateException("Policy digest mismatch");
        return policy;
      }catch(InterruptedException e) {Thread.currentThread().interrupt();throw new IllegalStateException("Policy resolution interrupted",e);}
      catch(Exception e) {throw new IllegalStateException("Policy resolution failed closed",e);}
    };
  }

  /** Exactly one mode is authoritative; missing or invalid configuration is an error. */
  static PackSpecSource fromProperties(java.util.Properties props, JsonNode internalPolicy) {
    Objects.requireNonNull(props);
    var mode=props.getProperty("qualityrag.packspec.source");
    if(mode==null) throw new IllegalArgumentException("Explicit qualityrag.packspec.source required");
    return switch(mode.trim().toLowerCase(java.util.Locale.ROOT)) {
      case "internal" -> internal(internalPolicy);
      case "property" -> property(props.getProperty("qualityrag.packspec.json"));
      case "file" -> file(Path.of(required(props,"qualityrag.packspec.path")));
      case "studio" -> studio(URI.create(required(props,"qualityrag.registry.url")),
          required(props,"qualityrag.registry.token"),required(props,"qualityrag.service-id"),
          required(props,"qualityrag.environment"));
      default -> throw new IllegalArgumentException("Unknown PackSpec source");
    };
  }

  private static String required(java.util.Properties p,String key) {
    String value=p.getProperty(key);
    if(value==null || value.isBlank()) throw new IllegalArgumentException("Missing "+key);
    return value;
  }
  private static boolean validSegment(String s) { return s!=null && s.matches("[A-Za-z0-9._-]+"); }
  private static JsonNode checked(JsonNode policy) {
    if(policy==null || !policy.isObject() || !nonempty(policy,"id") || !nonempty(policy,"version")
        || !policy.path("requirements").isArray() || policy.path("requirements").isEmpty())
      throw new IllegalArgumentException("Invalid PackSpec");
    var ids=new java.util.HashSet<String>();
    for(var r:policy.path("requirements")) {
      if(!nonempty(r,"id") || !ids.add(r.path("id").asText()))throw new IllegalArgumentException("Invalid requirement id");
      var min=r.get("min_independent_sources");
      var max=r.get("max_age_seconds");
      if(min!=null && (!min.isInt() || min.intValue()<1) ||
         max!=null && (!max.isIntegralNumber() || max.longValue()<0))
        throw new IllegalArgumentException("Invalid requirement threshold");
    }
    return policy.deepCopy();
  }
  private static boolean nonempty(JsonNode n,String key) {
    return n.path(key).isTextual() && !n.path(key).asText().isBlank();
  }
}
