package io.qualityrag.springai;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.qualityrag.spring.AnswerGate;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class GuardedChatClientTest {
 private static final ObjectMapper M=new ObjectMapper();
 private static final Instant NOW=Instant.parse("2026-11-02T10:05:00Z");
 private static final String POLICY="{\"id\":\"eligibility\",\"version\":\"1\",\"requirements\":[{\"id\":\"current-exception\",\"scope\":\"GA\",\"authority\":\"official\",\"min_independent_sources\":1}]}";
 @Test void missingExceptionNeverCallsModel() throws Exception {
  ChatClient client=mock(ChatClient.class);
  var result=new GuardedChatClient(client,new AnswerGate()).answer("Is this applicant eligible?",M.readTree(POLICY),M.readTree("[]"),NOW);
  assertEquals("INCONCLUSIVE",result.verdict());
  assertFalse(result.admitted());assertNull(result.answer());
  verifyNoInteractions(client);
  assertEquals("current-exception",result.receipt().path("wgap").get(0).path("requirement_id").asText());
 }
 @Test void malformedPackNeverCallsModel() throws Exception {
  ChatClient client=mock(ChatClient.class);
  assertThrows(IllegalArgumentException.class,()->new GuardedChatClient(client,new AnswerGate()).answer("q",M.readTree("{}"),M.readTree("[]"),NOW));
  verifyNoInteractions(client);
 }
}
