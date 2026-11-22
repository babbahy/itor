package itor

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File

/** User settings, saved in %APPDATA%\itor\config.json. */
@Serializable
data class Config(
    val employeeName: String = "",
    val geminiKey: String = "",
    val companyUrl: String = "",
    val companyKey: String = "",
    val autostart: Boolean = true,
    val noticeSeen: Boolean = false,
    val showTeam: Boolean = false,
    /** Demo buttons in Settings (simulated problems). */
    val showDemo: Boolean = false,
    /** "dark" (default) or "light". */
    val theme: String = "dark",
    /** Opt-in: use the webcam (on this PC only) to know if the employee is at the desk. */
    val webcamPresence: Boolean = false,
)

object Paths {
    private fun dir(env: String, fallback: String, name: String): File =
        File(System.getenv(env) ?: (System.getProperty("user.home") + fallback), name).apply { mkdirs() }

    /** Roaming settings. */
    val config: File get() = File(dir("APPDATA", "\\AppData\\Roaming", "itor"), "config.json")

    /** Local data: database, logs, lock. Kept out of %LOCALAPPDATA%\itor, where the app is installed. */
    val data: File get() = dir("LOCALAPPDATA", "\\AppData\\Local", "itor-data")
}

object ConfigStore {
    private val json = Json { prettyPrint = true; ignoreUnknownKeys = true; encodeDefaults = true }

    fun load(): Config = runCatching { json.decodeFromString<Config>(Paths.config.readText()) }.getOrDefault(Config())

    fun save(config: Config) {
        Paths.config.writeText(json.encodeToString(Config.serializer(), config))
    }
}
