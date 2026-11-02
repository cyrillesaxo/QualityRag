package io.qualityrag.springai;

import com.fasterxml.jackson.databind.JsonNode;
import io.qualityrag.spring.AnswerGate;
import org.springframework.ai.chat.client.ChatClient;
import java.time.Instant;
import java.util.Objects;

/** Enforces evidence admission BEFORE invoking Spring AI. The policy and witness metadata must come from trusted server-side code. */
public final class GuardedChatClient {
 private final ChatClient client;
 private final AnswerGate gate;
 public GuardedChatClient(ChatClient client,AnswerGate gate){
  this.client=Objects.requireNonNull(client);this.gate=Objects.requireNonNull(gate);
 }
 public AnswerGate.Outcome<String> answer(String question,JsonNode policy,JsonNode evidence,Instant asOf){
  Objects.requireNonNull(question,"question");
  return gate.generate(policy,evidence,asOf,()->client.prompt().user(question).call().content());
 }
}
