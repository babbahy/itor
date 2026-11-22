package itor

import java.io.File
import java.net.ServerSocket
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.security.SecureRandom
import java.time.Duration
import java.util.Base64

/**
 * Starts and stops the itor helper (the Python program that measures the PC, counts time and runs fixes).
 * - Installed app: runs <app>/resources/itor-helper/itor-helper.exe (built by scripts/build-helper.ps1).
 * - Development: runs `python -m services.agent.serve` from the repository's .venv.
 */
class Helper(private val config: Config) {
    // ITOR_DEV_PORT / ITOR_DEV_KEY: fixed values for testing; normally a free port and a random key.
    val port: Int = System.getenv("ITOR_DEV_PORT")?.toIntOrNull() ?: freePort()
    val key: String = System.getenv("ITOR_DEV_KEY")?.takeIf { it.length >= 16 } ?: randomKey()
    val baseUrl = "http://127.0.0.1:$port"
    private var process: Process? = null

    fun start() {
        val command: List<String>
        val workDir: File
        val packed = packedHelper()
        if (packed != null) {
            command = listOf(packed.absolutePath)
            workDir = packed.parentFile
        } else {
            val repo = findRepo() ?: error("itor helper not found. Run scripts/build-helper.ps1 or start from the repository.")
            command = listOf(File(repo, ".venv\\Scripts\\python.exe").absolutePath, "-m", "services.agent.serve")
            workDir = repo
        }
        val builder = ProcessBuilder(command).directory(workDir)
            .redirectErrorStream(true)
            .redirectOutput(ProcessBuilder.Redirect.appendTo(File(Paths.data, "helper.log")))
        val env = builder.environment()
        env["ITOR_AGENT_KEY"] = key
        env["ITOR_AGENT_PORT"] = port.toString()
        env["ITOR_DB_PATH"] = File(Paths.data, "itor.sqlite3").absolutePath
        // Real internet test so a Wi-Fi cut is seen even when a virtual adapter stays up.
        // An empty request to Google's connectivity page (the one Android/Chrome use); no data is sent.
        env.putIfAbsent("ITOR_INTERNET_PROBE_URL", "https://www.gstatic.com/generate_204")
        env.putIfAbsent("ITOR_INTERNET_EXPECTED_STATUS", "204")
        env.putIfAbsent("ITOR_CONNECTIVITY_INTERVAL_SECONDS", "10")
        if (config.employeeName.isNotBlank()) env["ITOR_EMPLOYEE_NAME"] = config.employeeName.trim()
        if (config.geminiKey.isNotBlank()) env["GEMINI_API_KEY"] = config.geminiKey.trim()
        // No company server configured: this PC plays the company server (demo).
        env["ITOR_COMPANY_URL"] = config.companyUrl.ifBlank { baseUrl }
        env["ITOR_COMPANY_KEY"] = config.companyKey.ifBlank { randomKey() }
        process = builder.start()
    }

    /** Waits until the helper answers /api/health. */
    fun waitReady(timeout: Duration = Duration.ofSeconds(40)): Boolean {
        val client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build()
        val deadline = System.nanoTime() + timeout.toNanos()
        while (System.nanoTime() < deadline) {
            if (process?.isAlive == false) return false
            val ok = runCatching {
                client.send(
                    HttpRequest.newBuilder(URI("$baseUrl/api/health")).timeout(Duration.ofSeconds(2)).build(),
                    HttpResponse.BodyHandlers.discarding(),
                ).statusCode() == 200
            }.getOrDefault(false)
            if (ok) return true
            Thread.sleep(300)
        }
        return false
    }

    fun stop() {
        process?.let { running ->
            running.descendants().forEach { it.destroy() }
            running.destroy()
            if (!running.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)) running.destroyForcibly()
        }
        process = null
    }

    companion object {
        fun packedHelper(): File? {
            val dir = System.getProperty("compose.application.resources.dir") ?: return null
            return File(dir, "itor-helper\\itor-helper.exe").takeIf { it.isFile }
        }

        /** Looks for the repository (services/agent/serve.py) from the current folder upwards. */
        fun findRepo(): File? {
            var dir: File? = File(System.getProperty("user.dir")).absoluteFile
            while (dir != null) {
                if (File(dir, "services/agent/serve.py").isFile && File(dir, ".venv").isDirectory) return dir
                dir = dir.parentFile
            }
            return null
        }

        private fun freePort(): Int = ServerSocket(0).use { it.localPort }

        private fun randomKey(): String =
            Base64.getUrlEncoder().withoutPadding().encodeToString(ByteArray(32).also { SecureRandom().nextBytes(it) })
    }
}
