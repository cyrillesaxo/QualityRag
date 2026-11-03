package io.qualityrag.spring;

import com.fasterxml.jackson.databind.JsonNode;
import io.qualityrag.PackSpecSource;
import java.util.Properties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

/**
 * Opt-in Spring Boot config. User must set qualityrag.packspec.source explicitly.
 * No implicit policy fallback.
 */
@AutoConfiguration
public class QualityRagConfiguration {
 @Bean
 @ConditionalOnMissingBean(PackSpecSource.class)
 PackSpecSource qualityRagPackSpecSource(Environment environment) {
  Properties props=new Properties();
  for(String key: new String[]{
      "qualityrag.packspec.source","qualityrag.packspec.json","qualityrag.packspec.path",
      "qualityrag.registry.url","qualityrag.registry.token",
      "qualityrag.service-id","qualityrag.environment"}) {
    var value=environment.getProperty(key);
    if(value!=null)props.setProperty(key,value);
  }
  // Embedded policy mode can be supplied explicitly as a user-defined PackSpecSource bean.
  if("internal".equalsIgnoreCase(props.getProperty("qualityrag.packspec.source","")))
    throw new IllegalArgumentException("For internal PackSpecs, define a PackSpecSource bean");
  return PackSpecSource.fromProperties(props,null);
 }
 @Bean
 @ConditionalOnMissingBean(ConfiguredAnswerGate.class)
 ConfiguredAnswerGate qualityRagConfiguredAnswerGate(PackSpecSource source) {
  return new ConfiguredAnswerGate(source);
 }
}
