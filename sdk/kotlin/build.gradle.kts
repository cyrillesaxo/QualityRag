plugins { kotlin("jvm") version "2.0.21" }
repositories { mavenCentral() }
kotlin { jvmToolchain(17) }
dependencies { implementation("com.fasterxml.jackson.core:jackson-databind:2.18.2"); testImplementation(kotlin("test")); testImplementation("org.apache.groovy:groovy-json:4.0.24") }
tasks.test { useJUnitPlatform() }
