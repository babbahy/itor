package itor

import com.sun.net.httpserver.HttpServer
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import java.net.InetSocketAddress
import java.net.URI
import java.util.concurrent.atomic.AtomicInteger
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OfflineAiTest {
    @Test
    fun reusesAnInstalledKnownModelWithoutWritingManagedFiles() = runBlocking {
        val requests = AtomicInteger()
        withTags("""{"models":[{"name":"qwen3.5:4b"},{"name":"qwen3.5:2b"}]}""", requests) { external ->
            val root = createTempDirectory().toFile()
            val ai = OfflineAi(root, true, this, { null }, external)
            try {
                assertEquals(OllamaEndpoint(external, "qwen3.5:2b"), ai.endpoint())
                ai.start()
                withTimeout(3_000) { ai.state.first { it.phase == OfflineAiPhase.EXTERNAL } }
                ai.pause()
                assertEquals(OfflineAiPhase.EXTERNAL, ai.state.value.phase)
                assertEquals(1, requests.get())
                assertTrue(root.list().orEmpty().isEmpty())
            } finally {
                ai.close()
                root.deleteRecursively()
            }
        }
    }

    @Test
    fun respectsAnExplicitEndpointAndModelWithoutProbingTheDefault() = runBlocking {
        val requests = AtomicInteger()
        withTags("""{"models":[]}""", requests) { external ->
            val root = createTempDirectory().toFile()
            val env = mapOf("ITOR_OLLAMA_URL" to "http://127.0.0.1:9912", "ITOR_OLLAMA_MODEL" to "qwen3.5:4b")
            val ai = OfflineAi(root, true, this, env::get, external)
            try {
                assertEquals(OllamaEndpoint("http://127.0.0.1:9912", "qwen3.5:4b"), ai.endpoint())
                ai.start()
                withTimeout(3_000) { ai.state.first { it.phase == OfflineAiPhase.EXTERNAL } }
                assertEquals(0, requests.get())
            } finally {
                ai.close()
                root.deleteRecursively()
            }
        }
    }

    @Test
    fun preservesTheLegacyModelWithOnlyAnExplicitUrl() = runBlocking {
        val root = createTempDirectory().toFile()
        val env = mapOf("ITOR_OLLAMA_URL" to "http://127.0.0.1:9912")
        val ai = OfflineAi(root, true, this, env::get)
        try {
            assertEquals(OllamaEndpoint("http://127.0.0.1:9912", "qwen3.5:4b"), ai.endpoint())
        } finally {
            ai.close()
            root.deleteRecursively()
        }
    }

    @Test
    fun selectsAStableManagedLoopbackEndpointWhenTheDefaultLacksQwen() = runBlocking {
        val requests = AtomicInteger()
        withTags("""{"models":[{"name":"llama3.2"},{"name":"qwen3.5:2b","remote_model":"cloud"}]}""", requests) { external ->
            val root = createTempDirectory().toFile()
            val ai = OfflineAi(root, true, this, { null }, external)
            try {
                val endpoint = requireNotNull(ai.endpoint())
                assertEquals("qwen3.5:2b", endpoint.model)
                assertEquals("127.0.0.1", URI(endpoint.url).host)
                assertNotEquals(external, endpoint.url)
                assertEquals(endpoint, ai.endpoint())
                assertEquals(1, requests.get())
            } finally {
                ai.close()
                root.deleteRecursively()
            }
        }
    }

    @Test
    fun leavesDevelopmentAndNonWindowsEndpointsAlone() = runBlocking {
        val root = createTempDirectory().toFile()
        val ai = OfflineAi(root, false, this, { error("Disabled setup must not resolve an endpoint") })
        try {
            assertNull(ai.endpoint())
            ai.start()
            ai.pause()
            assertEquals(OfflineAiPhase.EXTERNAL, ai.state.value.phase)
        } finally {
            ai.close()
            root.deleteRecursively()
        }
    }

    private suspend fun withTags(payload: String, requests: AtomicInteger, test: suspend (String) -> Unit) {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/api/tags") { exchange ->
            requests.incrementAndGet()
            val bytes = payload.toByteArray()
            exchange.use {
                it.responseHeaders.add("Content-Type", "application/json")
                it.sendResponseHeaders(200, bytes.size.toLong())
                it.responseBody.use { body -> body.write(bytes) }
            }
        }
        server.start()
        try {
            test("http://127.0.0.1:${server.address.port}")
        } finally {
            server.stop(0)
        }
    }
}
