package io.qualityrag;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PackSpecSourceTest {
 private static final ObjectMapper JSON=new ObjectMapper();
 private static final String POLICY="{\"id\":\"eu\",\"version\":\"1\",\"requirements\":[{\"id\":\"control\"}]}";
 @Test void internalAndPropertySources() throws Exception {
   var internal=JSON.readTree(POLICY);
   assertEquals("eu",PackSpecSource.internal(internal).load().path("id").asText());
   internal=(com.fasterxml.jackson.databind.node.ObjectNode)internal;
   ((com.fasterxml.jackson.databind.node.ObjectNode)internal).put("id","changed");
   assertEquals("eu",PackSpecSource.property(POLICY).load().path("id").asText());
   var p=new Properties();p.setProperty("qualityrag.packspec.source","property");
   p.setProperty("qualityrag.packspec.json",POLICY);
   assertEquals("eu",PackSpecSource.fromProperties(p,null).load().path("id").asText());
 }
 @Test void fileAndFailClosed() throws Exception {
   var file=Files.createTempFile("pack-", ".json");
   try {
     Files.writeString(file,POLICY);
     assertEquals("eu",PackSpecSource.file(file).load().path("id").asText());
     Files.writeString(file,"{}");
     assertThrows(IllegalArgumentException.class,()->PackSpecSource.file(file).load());
     Files.delete(file);
     assertThrows(IllegalStateException.class,()->PackSpecSource.file(file).load());
   }finally{Files.deleteIfExists(file);}
   assertThrows(IllegalArgumentException.class,()->PackSpecSource.fromProperties(new Properties(),null));
 }
 @Test void studioApprovedDigestAndTamper() throws Exception {
   var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
   var hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(POLICY.getBytes(StandardCharsets.UTF_8)));
   final boolean[] tamper={false};
   server.createContext("/v1/resolve/app/dev",ex->{
     String payload="{\"serviceId\":\"app\",\"environment\":\"dev\",\"status\":\"APPROVED\",\"sha256\":\""+hash+"\",\"policy\":"+(tamper[0]?POLICY.replace("eu","bad"):POLICY)+"}";
     byte[] bytes=payload.getBytes(StandardCharsets.UTF_8);
     ex.sendResponseHeaders(200,bytes.length);try(var out=ex.getResponseBody()){out.write(bytes);}
   });server.start();
   try {
     var source=PackSpecSource.studio(URI.create("http://127.0.0.1:"+server.getAddress().getPort()),"local","app","dev");
     assertEquals("eu",source.load().path("id").asText());
     tamper[0]=true;assertThrows(IllegalStateException.class,source::load);
   }finally{server.stop(0);}
   assertThrows(IllegalArgumentException.class,()->PackSpecSource.studio(URI.create("http://example.com"),"x","app","dev"));
 }
}
