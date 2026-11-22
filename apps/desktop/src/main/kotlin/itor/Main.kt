package itor

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Tray
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import itor.ui.AskIt
import itor.ui.Home
import itor.ui.ItorTheme
import itor.ui.M
import itor.ui.MyDay
import itor.ui.Settings
import itor.ui.Spinner
import itor.ui.T
import itor.ui.colors
import java.io.File
import java.io.RandomAccessFile
import java.nio.channels.FileLock
import kotlin.system.exitProcess

enum class Screen { HOME, DAY, SETTINGS }

/** Tray icon: a plain dark square with an "i". No gradient. */
object TrayIcon : Painter() {
    override val intrinsicSize = Size(32f, 32f)
    override fun DrawScope.onDraw() {
        val s = size.minDimension
        drawRoundRect(Color(0xFF0A0A0A), size = Size(s, s), cornerRadius = androidx.compose.ui.geometry.CornerRadius(s * 0.18f))
        drawRect(Color(0xFFFAFAFA), topLeft = androidx.compose.ui.geometry.Offset(s * 0.44f, s * 0.20f), size = Size(s * 0.12f, s * 0.12f))
        drawRect(Color(0xFFFAFAFA), topLeft = androidx.compose.ui.geometry.Offset(s * 0.44f, s * 0.40f), size = Size(s * 0.12f, s * 0.40f))
    }
}

private var lock: FileLock? = null

/** Only one itor per user. */
private fun singleInstance(): Boolean {
    lock = runCatching { RandomAccessFile(File(Paths.data, "app.lock"), "rw").channel.tryLock() }.getOrNull()
    return lock != null
}

/** Start with Windows (installed app only): HKCU Run key, no admin needed. */
private fun applyAutostart(enabled: Boolean) {
    if (Helper.packedHelper() == null) return
    val exe = ProcessHandle.current().info().command().orElse(null) ?: return
    val key = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    val command = if (enabled) listOf("reg", "add", key, "/v", "itor", "/t", "REG_SZ", "/d", "\"$exe\" --background", "/f")
    else listOf("reg", "delete", key, "/v", "itor", "/f")
    runCatching { ProcessBuilder(command).redirectErrorStream(true).start().waitFor() }
}

fun main(args: Array<String>) {
    if (!singleInstance()) exitProcess(0)
    val demo = "--demo" in args
    val background = "--background" in args
    var config = ConfigStore.load()
    applyAutostart(config.autostart)

    application {
        var helper by remember { mutableStateOf<Helper?>(null) }
        var model by remember { mutableStateOf<Model?>(null) }
        var startError by remember { mutableStateOf<String?>(null) }
        var visible by remember { mutableStateOf(!background) }
        var screen by remember { mutableStateOf(Screen.HOME) }
        var askIt by remember { mutableStateOf<String?>(null) }
        var askItOpen by remember { mutableStateOf(false) }
        var cfg by remember { mutableStateOf(config) }
        val scope = rememberCoroutineScope()

        fun startHelper(c: Config) {
            model?.stop(); helper?.stop()
            model = null; startError = null
            Thread {
                val h = Helper(c)
                try {
                    h.start()
                    if (!h.waitReady()) error("The helper did not start. See ${File(Paths.data, "helper.log")}")
                    helper = h
                    model = Model(Api(h.baseUrl, h.key), scope).also { it.start() }
                } catch (e: Exception) {
                    h.stop(); startError = e.message
                }
            }.apply { isDaemon = true }.start()
        }

        DisposableEffect(Unit) {
            startHelper(cfg)
            onDispose { model?.stop(); helper?.stop() }
        }

        fun quit() { model?.stop(); helper?.stop(); exitApplication() }
        fun open(target: Screen = Screen.HOME) { screen = target; visible = true }

        Tray(
            icon = TrayIcon,
            tooltip = "itor",
            onAction = { open() },
            menu = {
                Item("Open itor", onClick = { open() })
                Item("Fix my problem", onClick = { open(); model?.describe() })
                Item("Ask IT", onClick = { open(); askIt = null; model?.resetTicket(); askItOpen = true })
                Separator()
                Item("Quit", onClick = { quit() })
            },
        )

        Window(
            onCloseRequest = { visible = false }, // closing hides to the tray; Quit is in the tray menu
            visible = visible,
            title = "itor",
            icon = TrayIcon,
            state = rememberWindowState(size = DpSize(460.dp, 680.dp)),
        ) {
            ItorTheme {
                Column(Modifier.fillMaxSize().background(colors.bg)) {
                    TopBar(screen) { screen = it }
                    Box(Modifier.fillMaxSize()) {
                        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                            val m = model
                            when {
                                startError != null -> T(startError!!, 13, color = colors.warn)
                                m == null -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Spinner(); T("Starting itor", 13, color = colors.muted)
                                }
                                screen == Screen.HOME -> Home(
                                    m,
                                    onAskIT = { diagnosis -> askIt = diagnosis; m.resetTicket(); askItOpen = true },
                                    onMyDay = { screen = Screen.DAY },
                                    noticeSeen = cfg.noticeSeen,
                                    onNoticeSeen = { cfg = cfg.copy(noticeSeen = true); ConfigStore.save(cfg) },
                                )
                                screen == Screen.DAY -> MyDay(m)
                                else -> Settings(cfg, demo, m) { updated ->
                                    cfg = updated; config = updated
                                    ConfigStore.save(updated); applyAutostart(updated.autostart)
                                    startHelper(updated); screen = Screen.HOME
                                }
                            }
                        }
                        val m = model
                        if (askItOpen && m != null) AskIt(m, askIt) { askItOpen = false }
                    }
                }
            }
        }
    }
}

@Composable
private fun TopBar(screen: Screen, onSelect: (Screen) -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(colors.surface).border(width = 0.dp, color = colors.border).padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        M("itor", 14, weight = FontWeight.Medium)
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(14.dp, Alignment.End)) {
            listOf(Screen.HOME to "Home", Screen.DAY to "My day", Screen.SETTINGS to "Settings").forEach { (target, label) ->
                T(label, 13, if (target == screen) FontWeight.SemiBold else FontWeight.Normal,
                    if (target == screen) colors.text else colors.muted, Modifier.clickable { onSelect(target) })
            }
        }
    }
    androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(0.dp).background(colors.border).then(Modifier.padding(top = 1.dp)))
}
