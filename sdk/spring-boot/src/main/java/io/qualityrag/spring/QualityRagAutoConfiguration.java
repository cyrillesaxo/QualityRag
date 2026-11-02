package io.qualityrag.spring;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

/** Explicit Spring Boot 3 auto-configuration; policy and evidence are supplied per request. */
@AutoConfiguration
public class QualityRagAutoConfiguration {
 @Bean
 @ConditionalOnMissingBean(AnswerGate.class)
 public AnswerGate qualityRagAnswerGate(){return new AnswerGate();}
}
