package itor

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.net.InetSocketAddress
import java.net.URI
import java.nio.file.Files
import java.security.MessageDigest
import java.util.HexFormat
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutionException
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OllamaRuntimeTest {
    @Test
    fun interruptsStalledDownloadAndResumesSavedData() {
        val bundle = zip("ollama.exe" to "fixture executable")
        val offset = bundle.bytes.size / 2
        val release = CountDownLatch(1)
        withRuntime(bundle, { exchange ->
            if (exchange.requestHeaders.getFirst("Range") == null) {
                exchange.sendResponseHeaders(200, bundle.bytes.size.toLong())
                exchange.responseBody.write(bundle.bytes, 0, offset)
                exchange.responseBody.flush()
                release.await(10, TimeUnit.SECONDS)
            } else {
                exchange.responseHeaders.set("Content-Range", "bytes $offset-${bundle.bytes.lastIndex}/${bundle.bytes.size}")
                exchange.reply(206, bundle.bytes.copyOfRange(offset, bundle.bytes.size))
            }
        }) { runtime, root, archive, requests ->
            val part = partial(root, archive)
            val transfer = FutureTask { runtime.install {} }
            val worker = Thread(transfer).apply { isDaemon = true; start() }
            try {
                val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
                while (part.length() < offset && System.nanoTime() < deadline) Thread.sleep(10)
                assertEquals(offset.toLong(), part.length())
                worker.interrupt()
                val failure = assertFailsWith<ExecutionException> { transfer.get(5, TimeUnit.SECONDS) }
                assertTrue(failure.cause is InterruptedException)
                assertTrue(bundle.bytes.copyOf(offset).contentEquals(part.readBytes()))
                assertNull(runtime.executable())
            } finally {
                worker.interrupt()
                release.countDown()
            }
            assertEquals("fixture executable", runtime.install {}.readText())
            assertEquals(listOf(null, "bytes=$offset-"), requests.toList())
        }
    }

    @Test
    fun resumesMatchingRangeAndReusesCompleteCache() {
        val bundle = zip("ollama.exe" to "fixture executable", "lib/runner.dll" to "fixture library")
        val offset = bundle.bytes.size / 2
        withRuntime(bundle, { exchange ->
            exchange.responseHeaders.set("Content-Range", "bytes $offset-${bundle.bytes.lastIndex}/${bundle.bytes.size}")
            exchange.reply(206, bundle.bytes.copyOfRange(offset, bundle.bytes.size))
        }) { runtime, root, archive, requests ->
            val part = partial(root, archive).apply { writeBytes(bundle.bytes.copyOfRange(0, offset)) }
            val progress = mutableListOf<RuntimeProgress>()

            val executable = runtime.install { progress.add(it) }
            assertEquals(listOf("bytes=$offset-"), requests.toList())
            assertEquals("fixture executable", executable.readText())
            assertEquals("fixture library", executable.parentFile.resolve("lib/runner.dll").readText())
            assertEquals(offset.toLong(), progress.first().completed)
            assertTrue(progress.last().extracting)
            assertFalse(part.exists())

            assertEquals(executable, runtime.executable())
            assertEquals(executable, runtime.install { error("A valid cache should skip installation") })
            assertEquals(1, requests.size)
            executable.writeText("changed executable")
            assertNull(runtime.executable())
        }
    }

    @Test
    fun replacesPartialWhenServerIgnoresRange() {
        val bundle = zip("ollama.exe" to "fixture executable")
        withRuntime(bundle, { it.reply(200, bundle.bytes) }) { runtime, root, archive, requests ->
            partial(root, archive).writeBytes(byteArrayOf(1, 2, 3))
            assertEquals("fixture executable", runtime.install {}.readText())
            assertEquals(listOf("bytes=3-"), requests.toList())
        }
    }

    @Test
    fun rejectsMismatchedRangeWithoutChangingSavedBytes() {
        val bundle = zip("ollama.exe" to "fixture executable")
        withRuntime(bundle, { exchange ->
            exchange.responseHeaders.set("Content-Range", "bytes 4-${bundle.bytes.lastIndex}/${bundle.bytes.size}")
            exchange.reply(206, bundle.bytes.copyOfRange(4, bundle.bytes.size))
        }) { runtime, root, archive, requests ->
            val part = partial(root, archive).apply { writeBytes(byteArrayOf(1, 2, 3)) }
            assertFailsWith<IOException> { runtime.install {} }
            assertEquals(listOf("bytes=3-"), requests.toList())
            assertEquals(listOf<Byte>(1, 2, 3), part.readBytes().toList())
            assertNull(runtime.executable())
        }
    }

    @Test
    fun deletesArchiveWithWrongHashWithoutExtractingIt() {
        val bundle = zip("ollama.exe" to "fixture executable")
        withRuntime(bundle, { it.reply(200, bundle.bytes) }, digest = "0".repeat(64)) { runtime, root, archive, _ ->
            val error = assertFailsWith<IOException> { runtime.install {} }
            assertTrue("checksum" in error.message.orEmpty())
            assertFalse(partial(root, archive).exists())
            assertNull(runtime.executable())
        }
    }

    @Test
    fun refusesWindowsAndUnixTraversalBeforePublishingCache() {
        for (unsafe in listOf("../escaped.txt", "..\\escaped.txt", "C:/escaped.txt")) {
            val bundle = zip("ollama.exe" to "fixture executable", unsafe to "unexpected")
            withRuntime(bundle, { it.reply(200, bundle.bytes) }) { runtime, root, archive, _ ->
                val error = assertFailsWith<IOException> { runtime.install {} }
                assertTrue("unsafe file path" in error.message.orEmpty())
                assertNull(runtime.executable())
                assertFalse(root.resolve("escaped.txt").exists())
                assertFalse(root.parentFile.resolve("escaped.txt").exists())
                assertFalse(root.listFiles().orEmpty().any { it.name.startsWith(".ollama-extract-") })
                assertTrue(partial(root, archive).isFile)
            }
        }
    }

    private data class ZipFixture(val bytes: ByteArray, val expandedBytes: Long)

    private fun zip(vararg files: Pair<String, String>): ZipFixture {
        val target = ByteArrayOutputStream()
        var expanded = 0L
        ZipOutputStream(target).use { stream ->
            for ((name, content) in files) {
                val bytes = content.toByteArray()
                stream.putNextEntry(ZipEntry(name))
                stream.write(bytes)
                stream.closeEntry()
                expanded += bytes.size
            }
        }
        return ZipFixture(target.toByteArray(), expanded)
    }

    private fun partial(root: File, archive: RuntimeArchive): File = root.resolve("ollama-${archive.sha256.take(16)}.zip.part")

    private fun HttpExchange.reply(status: Int, content: ByteArray) {
        sendResponseHeaders(status, content.size.toLong())
        responseBody.use { it.write(content) }
    }

    private fun withRuntime(
        bundle: ZipFixture,
        respond: (HttpExchange) -> Unit,
        digest: String = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bundle.bytes)),
        test: (OllamaRuntime, File, RuntimeArchive, List<String?>) -> Unit,
    ) {
        val directory = Files.createTempDirectory("itor-runtime-test-").toFile()
        val root = directory.resolve("cache").apply { mkdir() }
        val requests = CopyOnWriteArrayList<String?>()
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        try {
            server.createContext("/runtime.zip") { exchange ->
                try {
                    requests += exchange.requestHeaders.getFirst("Range")
                    respond(exchange)
                } finally {
                    exchange.close()
                }
            }
            server.start()
            val archive = RuntimeArchive(
                URI("http://127.0.0.1:${server.address.port}/runtime.zip"),
                bundle.bytes.size.toLong(), bundle.expandedBytes, digest,
            )
            test(OllamaRuntime(root, archive), root, archive, requests)
        } finally {
            server.stop(0)
            directory.deleteRecursively()
        }
    }
}
