package itor

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runInterruptible
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import java.io.File
import java.io.IOException
import java.net.InetSocketAddress
import java.net.ProxySelector
import java.net.ServerSocket
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutionException
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

internal data class OllamaEndpoint(val url: String, val model: String)

enum class OfflineAiPhase {
    EXTERNAL, STARTING, DOWNLOADING_RUNTIME, INSTALLING_RUNTIME, DOWNLOADING_MODEL, READY, PAUSED, FAILED,
}

data class OfflineAiState(
    val phase: OfflineAiPhase,
    val detail: String? = null,
    val completed: Long? = null,
    val total: Long? = null,
)

private const val HOST = "127.0.0.1"
private const val DEFAULT_URL = "http://127.0.0.1:11434"
private const val MODEL = "qwen3.5:2b"
private const val ALTERNATE_MODEL = "qwen3.5:4b"

internal class OfflineAi(
    private val root: File,
    private val enabled: Boolean,
    private val scope: CoroutineScope,
    private val environment: (String) -> String? = System::getenv,
    private val defaultUrl: String = DEFAULT_URL,
) {
    private data class Selection(val endpoint: OllamaEndpoint, val externalDetail: String? = null)

    private val runtime = OllamaRuntime(root)
    private val client by lazy {
        HttpClient.newBuilder().connectTimeout(Duration.ofMillis(500))
            .proxy(ProxySelector.of(null)).followRedirects(HttpClient.Redirect.NEVER).build()
    }
    private val selection by lazy { select() }
    private val lock = Any()
    private val provisioning = Mutex()
    private val updates = MutableStateFlow(
        if (enabled) OfflineAiState(OfflineAiPhase.STARTING)
        else OfflineAiState(OfflineAiPhase.EXTERNAL, "Managed setup is available in the installed Windows app."),
    )
    val state: StateFlow<OfflineAiState> = updates.asStateFlow()
    private var job: Job? = null
    private var generation = 0L
    private var closed = false
    private var owned: Process? = null
    private var stopping: Process? = null

    /** Called by the helper launcher on its worker thread. The selected port stays fixed. */
    fun endpoint(): OllamaEndpoint? = if (enabled) selection.endpoint else null

    fun start() {
        synchronized(lock) {
            if (!enabled || closed || job?.isActive == true ||
                updates.value.phase in setOf(OfflineAiPhase.READY, OfflineAiPhase.EXTERNAL)
            ) return
            val run = ++generation
            updates.value = OfflineAiState(OfflineAiPhase.STARTING, "Checking local AI")
            val next = scope.launch(Dispatchers.IO, start = CoroutineStart.LAZY) {
                provisioning.withLock { provision(run) }
            }
            job = next
            next.start()
        }
    }

    fun pause() {
        val process = synchronized(lock) {
            if (closed || job?.isActive != true || updates.value.phase in setOf(OfflineAiPhase.READY, OfflineAiPhase.EXTERNAL)) return
            ++generation
            job?.cancel()
            updates.value = updates.value.copy(phase = OfflineAiPhase.PAUSED, detail = "Setup paused. Downloaded data stays on this PC.")
            owned?.also {
                stopping = it
                owned = null
            }
        }
        // Closing the owned server stops the pull even if its HTTP stream has not noticed cancellation yet.
        if (process != null) stop(process)
    }

    fun close() {
        val processes = synchronized(lock) {
            if (closed) return
            closed = true
            ++generation
            job?.cancel()
            listOfNotNull(owned, stopping).also {
                owned = null
                stopping = null
            }
        }
        processes.forEach(::stop)
    }

    private fun select(): Selection {
        val url = environment("ITOR_OLLAMA_URL")?.trim()?.takeIf(String::isNotEmpty)
        val model = environment("ITOR_OLLAMA_MODEL")?.trim()?.takeIf(String::isNotEmpty)
        if (url != null || model != null) {
            return Selection(OllamaEndpoint(url ?: defaultUrl, model ?: ALTERNATE_MODEL), "Using your configured Ollama endpoint and model.")
        }
        val installed = try {
            tags(defaultUrl)
        } catch (_: IOException) {
            emptySet()
        } catch (_: IllegalArgumentException) {
            emptySet()
        }
        val reusable = listOf(MODEL, ALTERNATE_MODEL).firstOrNull { it in installed }
        if (reusable != null) return Selection(OllamaEndpoint(defaultUrl, reusable), "Using installed $reusable in Ollama.")
        val port = ServerSocket().use { socket ->
            socket.bind(InetSocketAddress(HOST, 0))
            socket.localPort
        }
        return Selection(OllamaEndpoint("http://$HOST:$port", MODEL))
    }

    private suspend fun provision(run: Long) {
        for (attempt in 1..2) {
            try {
                val (endpoint, external) = selection
                if (external != null) {
                    publish(run, OfflineAiState(OfflineAiPhase.EXTERNAL, external))
                    return
                }
                val executable = runtime.executable() ?: runInterruptible {
                    runtime.install { progress ->
                        val phase = if (progress.extracting) OfflineAiPhase.INSTALLING_RUNTIME else OfflineAiPhase.DOWNLOADING_RUNTIME
                        publish(run, OfflineAiState(phase, completed = progress.completed, total = progress.total))
                    }
                }
                publish(run, OfflineAiState(OfflineAiPhase.STARTING, "Starting local Ollama"))
                awaitPreviousStop()
                val process = startOllama(run, executable, endpoint)
                if (endpoint.model !in awaitServer(process, endpoint)) {
                    checkModelSpace()
                    pull(run, endpoint)
                    if (endpoint.model !in awaitServer(process, endpoint)) {
                        throw IOException("Ollama did not list the downloaded model.")
                    }
                }
                synchronized(lock) {
                    if (!process.isAlive || owned !== process) throw IOException("Local Ollama exited before setup finished.")
                    publish(run, OfflineAiState(OfflineAiPhase.READY, endpoint.model))
                }
                return
            } catch (canceled: CancellationException) {
                throw canceled
            } catch (error: Exception) {
                val process = synchronized(lock) {
                    if (closed || run != generation) null else owned?.also {
                        stopping = it
                        owned = null
                    }
                }
                if (process != null) stop(process)
                if (attempt == 2) {
                    val reason = error.message?.lineSequence()?.firstOrNull()?.take(170) ?: "Local AI setup did not finish."
                    publish(run, OfflineAiState(OfflineAiPhase.FAILED, reason))
                    return
                }
                publish(run, OfflineAiState(OfflineAiPhase.STARTING, "Retrying local AI setup"))
                delay(2_000)
            }
        }
    }

    private fun publish(run: Long, state: OfflineAiState) {
        synchronized(lock) {
            if (!closed && run == generation) updates.value = state
        }
    }

    private suspend fun awaitPreviousStop() {
        val process = synchronized(lock) { stopping } ?: return
        if (!runInterruptible { process.waitFor(4, TimeUnit.SECONDS) }) {
            throw IOException("The paused local Ollama server is still stopping. Retry in a moment.")
        }
        synchronized(lock) {
            if (stopping === process) stopping = null
        }
    }

    private fun checkModelSpace() {
        val models = File(root, "models")
        val hasCachedData = File(models, "blobs").list()?.isNotEmpty() == true
        if (!hasCachedData && models.usableSpace in 1L until 3_000_000_000L) {
            throw IOException("Free at least 3 GB for the local Qwen model, then retry.")
        }
    }

    private fun startOllama(run: Long, executable: File, endpoint: OllamaEndpoint): Process {
        synchronized(lock) {
            if (closed || run != generation) throw CancellationException("Local AI setup stopped.")
            owned?.takeIf(Process::isAlive)?.let { return it }
            val models = File(root, "models")
            if (!models.isDirectory && !models.mkdirs()) throw IOException("Cannot create the local model cache.")
            val port = URI(endpoint.url).port
            try {
                ServerSocket().use { it.bind(InetSocketAddress(HOST, port)) }
            } catch (error: IOException) {
                throw IOException("The local Ollama port is occupied. Restart itor to choose another port.", error)
            }
            val process = ProcessBuilder(executable.absolutePath, "serve").directory(executable.parentFile)
                .redirectErrorStream(true).redirectOutput(ProcessBuilder.Redirect.appendTo(File(root, "ollama.log")))
                .apply {
                    environment()["OLLAMA_HOST"] = "$HOST:$port"
                    environment()["OLLAMA_MODELS"] = models.absolutePath
                    environment()["OLLAMA_NO_CLOUD"] = "1"
                    // Completed layers can exist before the model manifest is saved.
                    environment()["OLLAMA_NOPRUNE"] = "1"
                    environment().remove("OLLAMA_ORIGINS")
                }.start()
            owned = process
            process.onExit().thenRun {
                synchronized(lock) {
                    if (owned === process) {
                        owned = null
                        if (!closed && updates.value.phase == OfflineAiPhase.READY) {
                            updates.value = OfflineAiState(OfflineAiPhase.FAILED, "Local Ollama exited. Retry to restart it.")
                        }
                    }
                }
            }
            return process
        }
    }

    private suspend fun awaitServer(process: Process, endpoint: OllamaEndpoint): Set<String> {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(25)
        while (System.nanoTime() < deadline) {
            if (!process.isAlive) throw IOException("Local Ollama stopped. See ollama.log in itor's local data.")
            val listed = try {
                timed(1_500, "Local Ollama is taking longer to respond.") { tags(endpoint.url) }
            } catch (_: IOException) {
                null
            } catch (_: IllegalArgumentException) {
                null
            }
            if (listed != null && process.isAlive) return listed
            delay(300)
        }
        throw IOException("Local Ollama did not start in time. See ollama.log in itor's local data.")
    }

    private fun tags(url: String): Set<String> {
        val request = HttpRequest.newBuilder(URI("$url/api/tags")).timeout(Duration.ofMillis(650)).GET().build()
        val pending = client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
        val response = try {
            pending.get(650, TimeUnit.MILLISECONDS)
        } catch (error: TimeoutException) {
            pending.cancel(true)
            throw IOException("Ollama model list took too long to respond.", error)
        } catch (error: InterruptedException) {
            pending.cancel(true)
            throw error
        } catch (error: ExecutionException) {
            throw IOException("Ollama model list is unavailable.", error.cause)
        }
        if (response.statusCode() != 200) throw IOException("Ollama model list is unavailable.")
        val models = (Json.parseToJsonElement(response.body()) as? JsonObject)?.get("models") as? JsonArray
            ?: throw IOException("Ollama returned an invalid model list.")
        return models.mapNotNull { model ->
            val item = model as? JsonObject ?: return@mapNotNull null
            if (!item.string("remote_model").isNullOrBlank() || !item.string("remote_host").isNullOrBlank()) {
                return@mapNotNull null
            }
            item.string("name") ?: item.string("model")
        }.toSet()
    }

    private suspend fun pull(run: Long, endpoint: OllamaEndpoint) {
        publish(run, OfflineAiState(OfflineAiPhase.DOWNLOADING_MODEL, "Connecting to the Ollama model registry"))
        val request = HttpRequest.newBuilder(URI("${endpoint.url}/api/pull"))
            .timeout(Duration.ofSeconds(45)).header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString("""{"model":"${endpoint.model}","stream":true}"""))
            .build()
        val response = timed(45_000, "Ollama timed out connecting to the model registry.") {
            client.send(request, HttpResponse.BodyHandlers.ofInputStream())
        }
        response.body().bufferedReader(Charsets.UTF_8).use { stream ->
            if (response.statusCode() != 200) throw IOException("Ollama could not start the model download (HTTP ${response.statusCode()}).")
            while (true) {
                val line = timed(60_000, "No model progress was received for a minute. Retry to resume.") { stream.readLine() }
                    ?: throw IOException("Ollama ended the download before reporting success. Retry to resume.")
                if (line.isBlank()) continue
                val event = Json.parseToJsonElement(line) as? JsonObject ?: continue
                event.string("error")?.let { throw IOException(it.take(170)) }
                val status = event.string("status")
                if (status == "success") return
                val total = (event["total"] as? JsonPrimitive)?.longOrNull?.takeIf { it > 0 }
                val completed = (event["completed"] as? JsonPrimitive)?.longOrNull?.takeIf { it >= 0 }
                val detail = when (status) {
                    "verifying sha256 digest", "writing manifest", "removing any unused layers" -> "Verifying and saving the model"
                    else -> if (total != null) "Downloading a model layer" else "Preparing the model download"
                }
                publish(run, OfflineAiState(OfflineAiPhase.DOWNLOADING_MODEL, detail, completed, total))
            }
        }
    }

    private fun JsonObject.string(key: String): String? = (get(key) as? JsonPrimitive)?.contentOrNull

    private suspend fun <T> timed(millis: Long, message: String, block: () -> T): T = try {
        withTimeout(millis) { runInterruptible(block = block) }
    } catch (error: TimeoutCancellationException) {
        currentCoroutineContext().ensureActive()
        throw IOException(message, error)
    }

    private fun stop(process: Process) {
        val children = process.descendants().use { it.toList() }
        for (child in children.asReversed()) child.destroy()
        process.destroy()
        CompletableFuture.delayedExecutor(2, TimeUnit.SECONDS).execute {
            for (child in children.asReversed()) if (child.isAlive) child.destroyForcibly()
            if (process.isAlive) process.destroyForcibly()
        }
    }
}
