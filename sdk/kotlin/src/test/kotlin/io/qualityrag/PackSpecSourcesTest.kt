package io.qualityrag

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import java.nio.file.Files

class PackSpecSourcesTest {
 private val pack=Pack("eu","1",listOf(Requirement("general"),Requirement("control")))
 @Test fun internalAndFile() {
   assertEquals("eu",PackSpecSources.internal(pack)().id)
   val p=Files.createTempFile("qualityrag", ".json")
   try {
     Files.writeString(p,"""{"id":"eu","version":"1","requirements":[{"id":"general"},{"id":"control"}]}""")
     val loader=PackSpecSources.file(p)
     assertEquals(2,loader().requirements.size)
     Files.writeString(p,"{}")
     assertFails {loader()}
   } finally {Files.deleteIfExists(p)}
 }
 @Test fun studioInsecureUrlRejected() {
   assertFails {PackSpecSources.studio(java.net.URI.create("http://example.com"),"t","app","dev")}
 }
}
