package itor

import java.io.File
import java.io.IOException
import java.io.InterruptedIOException
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.net.http.HttpTimeoutException
import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.nio.channels.OverlappingFileLockException
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.FileVisitResult
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.Path
import java.nio.file.SimpleFileVisitor
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardOpenOption.APPEND
import java.nio.file.StandardOpenOption.CREATE
import java.nio.file.StandardOpenOption.CREATE_NEW
import java.nio.file.StandardOpenOption.TRUNCATE_EXISTING
import java.nio.file.StandardOpenOption.WRITE
import java.nio.file.attribute.BasicFileAttributes
import java.security.MessageDigest
import java.time.Duration
import java.util.HexFormat
import java.util.Locale
import java.util.concurrent.CompletableFuture
import java.util.concurrent.Flow
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import java.util.zip.ZipFile

internal data class RuntimeProgress(val extracting: Boolean, val completed: Long?, val total: Long?)

/** Pinned release metadata. A separate manifest describes the resulting on-disk files. */
internal data class RuntimeArchive(val url: URI, val bytes: Long, val expandedBytes: Long, val sha256: String)

private val windowsAmd64Archive = RuntimeArchive(
    url = URI("https://github.com/ollama/ollama/releases/download/v0.40.17/ollama-windows-amd64.zip"),
    bytes = 1_618_522_644,
    expandedBytes = 2_267_742_223,
    sha256 = "3dd80f6e3a9699f2eadf4ac418f00529cee594df9557541806eda1f1f3f5588a",
)

internal class OllamaRuntime(
    root: File,
    private val archive: RuntimeArchive = windowsAmd64Archive,
) {
    private val directory = root.toPath().toAbsolutePath().normalize()
    private val installed = directory.resolve("ollama-${archive.sha256.take(16)}")
    private val partial = directory.resolve("ollama-${archive.sha256.take(16)}.zip.part")
    private val client by lazy {
        HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(15))
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build()
    }

    /** Accept only a published cache with its executable and support files intact. */
    fun executable(): File? = try {
        cachedExecutable(installed)?.toFile()
    } catch (_: IOException) {
        null
    }

    @Throws(IOException::class, InterruptedException::class)
    fun install(onProgress: (RuntimeProgress) -> Unit): File {
        Files.createDirectories(directory)
        val lockPath = directory.resolve(".ollama-install.lock")
        FileChannel.open(lockPath, CREATE, WRITE, NOFOLLOW_LINKS).use { channel ->
            val lock = try {
                channel.tryLock()
            } catch (_: OverlappingFileLockException) {
                null
            } ?: throw IOException("Offline AI setup is already running.")
            lock.use {
                checkInterrupted()
                executable()?.let { return it }
                checkInterrupted()
                if (Files.exists(partial, NOFOLLOW_LINKS) && !Files.isRegularFile(partial, NOFOLLOW_LINKS)) {
                    throw IOException("The Ollama download cache is not a regular file.")
                }
                if (Files.exists(partial) && Files.size(partial) > archive.bytes) Files.delete(partial)
                val saved = if (Files.exists(partial, NOFOLLOW_LINKS)) Files.size(partial) else 0L
                val required = archive.bytes - saved + archive.expandedBytes
                if (directory.toFile().usableSpace in 1 until required) {
                    throw IOException("Free up disk space for the Ollama runtime, then retry.")
                }
                download(onProgress)
                onProgress(RuntimeProgress(extracting = true, completed = null, total = null))
                if (sha256(partial) != archive.sha256) {
                    Files.delete(partial)
                    throw IOException("Ollama download failed checksum verification. Start setup again to retry.")
                }
                return publishExtracted()
            }
        }
    }

    private fun download(onProgress: (RuntimeProgress) -> Unit) {
        var downloaded = if (Files.isRegularFile(partial, NOFOLLOW_LINKS)) Files.size(partial) else 0L
        onProgress(RuntimeProgress(extracting = false, completed = downloaded, total = archive.bytes))
        var allowRange = true
        while (downloaded < archive.bytes) {
            checkInterrupted()
            val requestedOffset = if (allowRange) downloaded else 0L
            val builder = HttpRequest.newBuilder(archive.url).timeout(Duration.ofSeconds(45))
                .header("Accept-Encoding", "identity")
            if (requestedOffset > 0) builder.header("Range", "bytes=$requestedOffset-")
            val response = client.send(builder.GET().build(), HttpResponse.BodyHandlers.ofPublisher())
            DownloadChunks().use { chunks ->
                response.body().subscribe(chunks)
                if (response.statusCode() == 416 && requestedOffset > 0) {
                    // If the origin rejects a saved offset, try one plain request. Keep the saved
                    // bytes until that request has returned a valid full response.
                    allowRange = false
                } else {
                    val range = transferRange(response, requestedOffset)
                    downloaded = writeResponse(chunks, range, onProgress)
                    allowRange = true
                }
            }
        }
    }

    private fun transferRange(response: HttpResponse<*>, requestedOffset: Long): LongRange {
        val headers = response.headers()
        val encoding = headers.firstValue("Content-Encoding").orElse("identity")
        if (!encoding.equals("identity", ignoreCase = true)) {
            throw IOException("Ollama download returned an unexpected content encoding.")
        }
        val range = when (response.statusCode()) {
            200 -> 0L until archive.bytes
            206 -> {
                val received = rangeHeader.matchEntire(headers.firstValue("Content-Range").orElse(""))
                    ?: throw IOException("Ollama download returned an invalid byte range.")
                val start = received.groupValues[1].toLongOrNull()
                val end = received.groupValues[2].toLongOrNull()
                val total = received.groupValues[3].toLongOrNull()
                if (requestedOffset == 0L || start != requestedOffset || end == null ||
                    end < requestedOffset || end >= archive.bytes || total != archive.bytes
                ) {
                    throw IOException("Ollama download returned an unexpected byte range.")
                }
                requestedOffset..end
            }
            else -> throw IOException("Ollama download returned HTTP ${response.statusCode()}.")
        }
        val length = headers.firstValue("Content-Length").orElse(null)
        if (length != null && length.toLongOrNull() != range.last - range.first + 1) {
            throw IOException("Ollama download returned an unexpected content length.")
        }
        return range
    }

    private fun writeResponse(
        chunks: DownloadChunks,
        range: LongRange,
        onProgress: (RuntimeProgress) -> Unit,
    ): Long {
        var offset = range.first
        var lastUpdate = System.nanoTime()
        val mode = if (offset == 0L) TRUNCATE_EXISTING else APPEND
        onProgress(RuntimeProgress(extracting = false, completed = offset, total = archive.bytes))
        FileChannel.open(partial, CREATE, WRITE, mode, NOFOLLOW_LINKS).use { file ->
            while (true) {
                val batch = chunks.next() ?: break
                val batchBytes = batch.sumOf { it.remaining().toLong() }
                if (batchBytes > range.last + 1 - offset) {
                    throw IOException("Ollama download exceeded the expected size.")
                }
                for (buffer in batch) {
                    while (buffer.hasRemaining()) file.write(buffer)
                }
                offset += batchBytes
                val now = System.nanoTime()
                if (now - lastUpdate >= TimeUnit.MILLISECONDS.toNanos(200) || offset == range.last + 1) {
                    onProgress(RuntimeProgress(extracting = false, completed = offset, total = archive.bytes))
                    lastUpdate = now
                }
            }
        }
        if (offset != range.last + 1) throw IOException("Ollama download ended early. Resume setup to continue.")
        return offset
    }

    private fun publishExtracted(): File {
        val staging = Files.createTempDirectory(directory, ".ollama-extract-")
        try {
            extract(staging)
            val stagedExecutable = cachedExecutable(staging)
                ?: throw IOException("The Ollama archive did not contain a complete runtime.")
            checkInterrupted()
            if (Files.exists(installed, NOFOLLOW_LINKS)) removeDirectory(installed)
            try {
                Files.move(staging, installed, ATOMIC_MOVE)
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(staging, installed)
            }
            // A lingering archive is harmless if Windows temporarily has it open.
            runCatching { Files.deleteIfExists(partial) }
            return installed.resolve(stagedExecutable.fileName).toFile()
        } finally {
            if (Files.exists(staging, NOFOLLOW_LINKS)) runCatching { removeDirectory(staging) }
        }
    }

    private fun extract(staging: Path) {
        val files = mutableListOf<String>()
        val seen = mutableSetOf<String>()
        val buffer = ByteArray(128 * 1024)
        var expanded = 0L
        var entries = 0
        ZipFile(partial.toFile()).use { zip ->
            for (entry in zip.entries()) {
                checkInterrupted()
                if (++entries > MAX_ENTRIES) throw IOException("Ollama archive contains too many entries.")
                val name = if (entry.isDirectory) entry.name.removeSuffix("/") else entry.name
                val target = safePath(staging, name)
                if (!seen.add(name.lowercase(Locale.ROOT))) {
                    throw IOException("Ollama archive contains duplicate paths.")
                }
                if (entry.isDirectory) {
                    Files.createDirectories(target)
                    continue
                }
                if (entry.size !in 0..(archive.expandedBytes - expanded)) {
                    throw IOException("Ollama archive contains an unexpected file size.")
                }
                Files.createDirectories(target.parent)
                var written = 0L
                zip.getInputStream(entry).use { input ->
                    Files.newOutputStream(target, CREATE_NEW, WRITE).use { output ->
                        while (true) {
                            checkInterrupted()
                            val count = input.read(buffer)
                            if (count < 0) break
                            written += count
                            if (written > entry.size) throw IOException("An Ollama file exceeded its expected size.")
                            output.write(buffer, 0, count)
                        }
                    }
                }
                if (written != entry.size) throw IOException("An Ollama file was incomplete after extraction.")
                expanded += written
                files += "$written\t$name"
            }
        }
        val exe = staging.resolve(EXECUTABLE)
        if (expanded != archive.expandedBytes || !Files.isRegularFile(exe, NOFOLLOW_LINKS)) {
            throw IOException("The Ollama archive did not contain a complete runtime.")
        }
        // Keep all release files, including bundled library notices and licenses.
        Files.write(staging.resolve(MANIFEST), listOf(archive.sha256, sha256(exe)) + files, CREATE_NEW, WRITE)
    }

    private fun cachedExecutable(cache: Path): Path? {
        if (!Files.isDirectory(cache, NOFOLLOW_LINKS)) return null
        val cacheRealPath = cache.toRealPath()
        if (cacheRealPath != cache.parent.toRealPath().resolve(cache.fileName)) return null
        val marker = cache.resolve(MANIFEST)
        if (!Files.isRegularFile(marker, NOFOLLOW_LINKS) || Files.size(marker) > MAX_MANIFEST_BYTES) return null
        val lines = Files.readAllLines(marker)
        if (lines.size !in 3..(MAX_ENTRIES + 2) || lines[0] != archive.sha256) return null
        val seen = mutableSetOf<String>()
        var expanded = 0L
        for (line in lines.drop(2)) {
            val separator = line.indexOf('\t')
            if (separator < 1) return null
            val size = line.substring(0, separator).toLongOrNull() ?: return null
            if (size !in 0..(archive.expandedBytes - expanded)) return null
            val name = line.substring(separator + 1)
            if (!seen.add(name.lowercase(Locale.ROOT))) return null
            val path = safePath(cache, name)
            if (!Files.isRegularFile(path, NOFOLLOW_LINKS) || Files.size(path) != size ||
                !path.toRealPath().startsWith(cacheRealPath)
            ) return null
            expanded += size
        }
        val executable = cache.resolve(EXECUTABLE)
        return if (EXECUTABLE in seen && expanded == archive.expandedBytes && sha256(executable) == lines[1]) {
            executable
        } else {
            null
        }
    }

    private fun safePath(parent: Path, name: String): Path {
        val segments = name.split('/')
        for (segment in segments) {
            if (segment.isEmpty() || segment == "." || segment == ".." ||
                segment.endsWith(' ') || segment.endsWith('.') ||
                segment.any { it.code < 32 || it in "\\:<>|\"?*" } ||
                reservedName.matches(segment.substringBefore('.')) ||
                segment.equals(MANIFEST, ignoreCase = true)
            ) {
                throw IOException("Ollama archive contains an unsafe file path.")
            }
        }
        val path = parent.resolve(name).normalize()
        if (!path.startsWith(parent)) throw IOException("Ollama archive contains an unsafe file path.")
        return path
    }

    private fun removeDirectory(path: Path) {
        val expectedRoot = path.parent.toRealPath().resolve(path.fileName)
        Files.walkFileTree(path, object : SimpleFileVisitor<Path>() {
            override fun preVisitDirectory(dir: Path, attrs: BasicFileAttributes): FileVisitResult {
                // A Windows junction can look like a directory even without following symbolic links.
                if (!dir.toRealPath().startsWith(expectedRoot)) {
                    Files.delete(dir)
                    return FileVisitResult.SKIP_SUBTREE
                }
                return FileVisitResult.CONTINUE
            }

            override fun visitFile(file: Path, attrs: BasicFileAttributes): FileVisitResult {
                Files.delete(file)
                return FileVisitResult.CONTINUE
            }

            override fun postVisitDirectory(dir: Path, error: IOException?): FileVisitResult {
                if (error != null) throw error
                Files.delete(dir)
                return FileVisitResult.CONTINUE
            }
        })
    }

    private fun sha256(path: Path): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(128 * 1024)
        Files.newInputStream(path, NOFOLLOW_LINKS).use { input ->
            while (true) {
                checkInterrupted()
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return HexFormat.of().formatHex(digest.digest())
    }

    private companion object {
        const val EXECUTABLE = "ollama.exe"
        const val MANIFEST = ".itor-runtime-manifest"
        const val MAX_ENTRIES = 4096
        const val MAX_MANIFEST_BYTES = 1024 * 1024L
        val rangeHeader = Regex("bytes ([0-9]+)-([0-9]+)/([0-9]+)")
        val reservedName = Regex("CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]|CONIN\\$|CONOUT\\$", RegexOption.IGNORE_CASE)
    }
}

private fun checkInterrupted() {
    if (Thread.currentThread().isInterrupted) throw InterruptedIOException("Offline AI setup paused.")
}

/** Request one batch at a time so pause can interrupt a stalled network read. */
private class DownloadChunks : Flow.Subscriber<List<ByteBuffer>>, AutoCloseable {
    private sealed interface Event {
        data class Data(val buffers: List<ByteBuffer>) : Event
        data class Failed(val error: Throwable) : Event
        data object Done : Event
    }

    private val subscription = CompletableFuture<Flow.Subscription>()
    private val events = LinkedBlockingQueue<Event>()

    override fun onSubscribe(value: Flow.Subscription) {
        if (!subscription.complete(value)) value.cancel()
    }

    override fun onNext(buffers: List<ByteBuffer>) {
        events.add(Event.Data(buffers))
    }

    override fun onError(error: Throwable) {
        events.add(Event.Failed(error))
    }

    override fun onComplete() {
        events.add(Event.Done)
    }

    fun next(): List<ByteBuffer>? {
        try {
            subscription.get(30, TimeUnit.SECONDS).request(1)
        } catch (_: TimeoutException) {
            throw HttpTimeoutException("Ollama download could not start.")
        }
        return when (val event = events.poll(30, TimeUnit.SECONDS)) {
            is Event.Data -> event.buffers
            is Event.Failed -> throw IOException("Ollama download was interrupted. Resume setup to continue.", event.error)
            Event.Done -> null
            null -> throw HttpTimeoutException("Ollama download stopped responding. Resume setup to continue.")
        }
    }

    override fun close() {
        subscription.thenAccept { it.cancel() }
    }
}
