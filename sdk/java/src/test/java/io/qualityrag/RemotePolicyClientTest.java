package io.qualityrag;
import com.sun.net.httpserver.HttpServer;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class RemotePolicyClientTest {
 private static final ObjectMapper M=new ObjectMapper();
 @Test void approvedPolicyAcceptedAndTamperingRejected() throws Exception {
  String policy="{\"id\":\"demo\",\"version\":\"1\",\"requirements\":[{\"id\":\"r\"}]}";
  String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(policy.getBytes(StandardCharsets.UTF_8)));
  var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
  final boolean[] tamper={false};
  server.createContext("/v1/resolve/app/dev",ex->{
   var reply="{\"serviceId\":\"app\",\"environment\":\"dev\",\"status\":\"APPROVED\",\"sha256\":\""+hash+"\",\"policy\":"+(tamper[0]?policy.replace("demo","evil"):policy)+"}";
   byte[] body=reply.getBytes(StandardCharsets.UTF_8);
   ex.sendResponseHeaders(200,body.length);try(var out=ex.getResponseBody()){out.write(body);}
  });
  server.start();
  try {
   var client=new RemotePolicyClient(URI.create("http://127.0.0.1:"+server.getAddress().getPort()),"local-secret");
   assertEquals("demo",client.resolve("app","dev").policy().path("id").asText());
   tamper[0]=true;
   assertThrows(IllegalStateException.class,()->client.resolve("app","dev"));
  }finally{server.stop(0);}
 }
 @Test void rejectsNonTlsRemoteEndpoint(){assertThrows(IllegalArgumentException.class,()->new RemotePolicyClient(URI.create("http://example.com"),"secret"));}
}
