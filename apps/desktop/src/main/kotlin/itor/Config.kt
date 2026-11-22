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
)

object Paths {
    private fun dir(env: String, fallback: String): File =
        File(System.getenv(env) ?: (System.getProperty("user.home") + fallback), "itor").apply { mkdirs() }

    /** Roaming settings. */
    val config: File get() = File(dir("APPDATA", "\\AppData\\Roaming"), "config.json")

    /** Local data: database, logs, lock. */
    val data: File get() = dir("LOCALAPPDATA", "\\AppData\\Local")
}

object ConfigStore {
    private val json = Json { prettyPrint = true; ignoreUnknownKeys = true; encodeDefaults = true }

    fun load(): Config = runCatching { json.decodeFromString<Config>(Paths.config.readText()) }.getOrDefault(Config())

    fun save(config: Config) {
        Paths.config.writeText(json.encodeToString(Config.serializer(), config))
    }
}
