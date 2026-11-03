package io.qualityrag

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.time.Duration

/** Explicit PackSpec authority. Never fall back to a weaker policy on an error. */
object PackSpecSources {
    private val json=ObjectMapper()
    private fun checked(root: JsonNode): Pack {
        require(root.isObject && root.path("id").isTextual && root.path("id").asText().isNotBlank() &&
            root.path("version").isTextual && root.path("version").asText().isNotBlank())
        val req=root.path("requirements")
        require(req.isArray && req.size()>0)
        val ids=mutableSetOf<String>()
        val obligations=req.map { r ->
            val id=r.path("id").asText("")
            require(id.isNotBlank() && ids.add(id))
            val minimum=r.path("min_independent_sources").let {if(it.isMissingNode) 1 else {require(it.isInt);it.asInt()} }
            val age=r.path("max_age_seconds").let {if(it.isMissingNode) null else {require(it.isIntegralNumber);it.asLong()} }
            require(minimum>0 && (age==null || age>=0))
            Requirement(id,minimum,age)
        }
        return Pack(root.path("id").asText(),root.path("version").asText(),obligations)
    }
    private fun parse(text:String):Pack=checked(json.readTree(text))
    fun internal(pack:Pack):()->Pack {
        require(pack.id.isNotBlank() && pack.version.isNotBlank() && pack.requirements.isNotEmpty())
        require(pack.requirements.map { it.id }.distinct().size==pack.requirements.size)
        require(pack.requirements.all { it.id.isNotBlank() && it.minIndependentSources>0 &&
            (it.maxAgeSeconds==null || it.maxAgeSeconds>=0) })
        val snapshot=pack.copy(requirements=pack.requirements.toList())
        return { snapshot.copy(requirements=snapshot.requirements.toList()) }
    }
    fun property(text:String):()->Pack = internal(parse(text))
    fun file(path:Path):()->Pack = {
        require(Files.size(path)<=262144) {"Policy file too large"}
        parse(Files.readString(path))
    }
    fun studio(base:URI,token:String,service:String,environment:String,
               client:HttpClient=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build()):()->Pack {
        require((base.scheme=="https" || (base.scheme=="http" && base.host in listOf("localhost","127.0.0.1"))) &&
            base.userInfo==null && base.query==null && base.fragment==null) {"HTTPS required outside loopback"}
        require(token.isNotBlank() && service.matches(Regex("[A-Za-z0-9._-]+")) &&
            environment.matches(Regex("[A-Za-z0-9._-]+")))
        val endpoint=base.resolve("/v1/resolve/$service/$environment")
        return {
            val request=HttpRequest.newBuilder(endpoint).timeout(Duration.ofSeconds(5))
                .header("Authorization","Bearer $token").GET().build()
            val response=client.send(request,HttpResponse.BodyHandlers.ofString())
            check(response.statusCode()==200 && response.body().toByteArray().size<=262144) {"Studio unavailable"}
            val envelope=json.readTree(response.body())
            check(envelope.path("status").asText()=="APPROVED" &&
                envelope.path("serviceId").asText()==service && envelope.path("environment").asText()==environment) {"Studio binding mismatch"}
            val policy=envelope.path("policy")
            val expected=envelope.path("sha256").asText()
            val digest=MessageDigest.getInstance("SHA-256").digest(json.writeValueAsBytes(policy))
                .joinToString("") { "%02x".format(it) }
            check(expected.matches(Regex("[a-f0-9]{64}")) &&
                MessageDigest.isEqual(expected.toByteArray(StandardCharsets.US_ASCII),
                    digest.toByteArray(StandardCharsets.US_ASCII))) {"Studio digest mismatch"}
            checked(policy)
        }
    }
    fun fromProperties(props:Map<String,String>,embedded:Pack?=null):()->Pack {
        fun required(key:String):String=props[key]?.takeIf { it.isNotBlank() }
            ?: error("Missing $key")
        return when(required("qualityrag.packspec.source")) {
            "internal" -> internal(embedded ?: error("Missing embedded policy"))
            "property" -> property(required("qualityrag.packspec.json"))
            "file" -> file(Path.of(required("qualityrag.packspec.path")))
            "studio" -> studio(URI.create(required("qualityrag.registry.url")),
                required("qualityrag.registry.token"),required("qualityrag.service-id"),
                required("qualityrag.environment"))
            else -> error("Unknown PackSpec source")
        }
    }
}
