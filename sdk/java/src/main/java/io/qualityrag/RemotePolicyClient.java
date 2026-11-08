package io.qualityrag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Objects;

/** Resolves approved, versioned PackSpecs from a registry. Never defaults to an unrestricted policy. */
public final class RemotePolicyClient {
  private final HttpClient http;
  private final ObjectMapper mapper = new ObjectMapper();
  private final URI base;
  private final String token;
  public record ResolvedPolicy(JsonNode policy, String sha256, String serviceId, String environment) {}
  public RemotePolicyClient(URI base, String token) {
    this(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build(),base,token);
  }
  public RemotePolicyClient(HttpClient http, URI base, String token) {
    this.http=Objects.requireNonNull(http);
    this.base=Objects.requireNonNull(base);
    if(!"https".equalsIgnoreCase(base.getScheme()) && !("http".equalsIgnoreCase(base.getScheme()) &&
      ("localhost".equalsIgnoreCase(base.getHost()) || "127.0.0.1".equals(base.getHost()))))
      throw new IllegalArgumentException("HTTPS required except loopback development");
    if(token==null || token.isBlank()) throw new IllegalArgumentException("Registry credential required");
    this.token=token;
  }
  private static String segment(String value) {
    if(value==null || !value.matches("[A-Za-z0-9._-]+")) throw new IllegalArgumentException("Invalid registry identifier");
    return URLEncoder.encode(value, StandardCharsets.UTF_8);
  }
  public ResolvedPolicy resolve(String serviceId,String environment) {
    try {
      URI endpoint=base.resolve("/v1/resolve/"+segment(serviceId)+"/"+segment(environment));
      var request=HttpRequest.newBuilder(endpoint).timeout(Duration.ofSeconds(5))
         .header("Authorization","Bearer "+token).header("Accept","application/json").GET().build();
      var response=http.send(request,HttpResponse.BodyHandlers.ofString());
      if(response.statusCode()!=200)throw new IllegalStateException("Registry refused policy resolution: HTTP "+response.statusCode());
      JsonNode root=mapper.readTree(response.body());
      JsonNode policy=root.path("policy");
      String hash=root.path("sha256").asText();
      if(!"APPROVED".equals(root.path("status").asText()) ||
          !serviceId.equals(root.path("serviceId").asText()) ||
          !environment.equals(root.path("environment").asText()) ||
          !hash.matches("[a-f0-9]{64}"))throw new IllegalStateException("Invalid registry policy envelope");
      if(!policy.isObject()||!policy.path("requirements").isArray()||policy.path("requirements").isEmpty())
        throw new IllegalStateException("Invalid policy");
      // Registry currently hashes JSON.stringify(policy), which is compact insertion-order JSON.
      // Jackson serialization matches for ordinary object-valued PackSpecs; this is provisional, not JCS.
      byte[] bytes=mapper.writeValueAsBytes(policy);
      String actual=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
      if(!MessageDigest.isEqual(actual.getBytes(StandardCharsets.US_ASCII),hash.getBytes(StandardCharsets.US_ASCII)))
        throw new IllegalStateException("Policy digest mismatch");
      return new ResolvedPolicy(policy.deepCopy(),hash,serviceId,environment);
    }catch(InterruptedException e){Thread.currentThread().interrupt();throw new IllegalStateException("Policy resolution interrupted",e);}
    catch(Exception e){throw new IllegalStateException("Policy resolution failed closed",e);}
  }
}
