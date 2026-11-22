package itor

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.AclEntry
import java.nio.file.attribute.AclEntryPermission
import java.nio.file.attribute.AclEntryType
import java.nio.file.attribute.AclFileAttributeView

/** Address and key of the running helper, for the separate "itor demo panel" app. */
@Serializable
data class DemoAccessInfo(val baseUrl: String, val key: String)

/**
 * Written only while "Show demo tools" is on, in %LOCALAPPDATA%\itor-data (readable by this Windows user only),
 * and deleted when itor quits. The demo panel reads it to call the helper's demo actions.
 */
object DemoAccess {
    val file: File get() = File(Paths.data, "demo-access.json")

    internal fun update(helper: Helper, enabled: Boolean) {
        if (!enabled) { clear(); return }
        runCatching {
            file.writeText(Json.encodeToString(DemoAccessInfo.serializer(), DemoAccessInfo(helper.baseUrl, helper.key)))
            ownerOnly(file)
        }
    }

    fun clear() { runCatching { file.delete() } }

    fun read(): DemoAccessInfo? =
        runCatching { Json.decodeFromString(DemoAccessInfo.serializer(), file.readText()) }.getOrNull()

    /** Windows ACL: only the current user can read or write the file. */
    private fun ownerOnly(target: File) {
        val view = Files.getFileAttributeView(target.toPath(), AclFileAttributeView::class.java) ?: return
        val owner = view.owner
        val entry = AclEntry.newBuilder().setType(AclEntryType.ALLOW).setPrincipal(owner)
            .setPermissions(AclEntryPermission.values().toSet()).build()
        view.acl = listOf(entry)
    }
}
