package itor

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.runtime.collectAsState
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.window.Notification
import androidx.compose.ui.window.rememberTrayState
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import itor.ui.AskIt
import itor.ui.Camera
import itor.ui.Home
import itor.ui.ItorTheme
import itor.ui.M
import itor.ui.MyDay
import itor.ui.OfflineAiSetup
import itor.ui.Settings
import itor.ui.Team
import itor.ui.Spinner
import itor.ui.T
import itor.ui.colors
import java.io.File
import java.io.RandomAccessFile
import java.nio.channels.FileLock
import kotlin.system.exitProcess

enum class Screen { HOME, DAY, TEAM, CAMERA, SETTINGS }

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
    // Only the installed app (itor.exe) registers itself, never a development run (java.exe).
    val exe = ProcessHandle.current().info().command().orElse(null) ?: return
    if (!exe.endsWith("itor.exe", ignoreCase = true)) return
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
        // --screen=day|team|settings opens that tab first (handy for the demo and for testing).
        var screen by remember { mutableStateOf(args.firstOrNull { it.startsWith("--screen=") }
            ?.substringAfter('=')?.uppercase()?.let { name -> Screen.entries.firstOrNull { it.name == name } } ?: Screen.HOME) }
        var askIt by remember { mutableStateOf<String?>(null) }
        var askItOpen by remember { mutableStateOf(false) }
        var cfg by remember { mutableStateOf(config) }
        val scope = rememberCoroutineScope()
        val offlineAi = remember {
            val installedOnWindows = System.getProperty("os.name").startsWith("Windows", ignoreCase = true) &&
                System.getProperty("os.arch") in setOf("amd64", "x86_64") &&
                Helper.packedHelper() != null
            OfflineAi(File(Paths.data, "offline-ai"), installedOnWindows, scope)
        }
        var offlineAiOpened by remember { mutableStateOf(false) }

        fun startHelper(c: Config) {
            DemoAccess.clear()
            model?.stop(); helper?.stop()
            model = null; startError = null
            Thread {
                var candidate: Helper? = null
                try {
                    val endpoint = runCatching { offlineAi.endpoint() }.getOrNull()
                    val h = Helper(c, endpoint)
                    candidate = h
                    h.start()
                    if (!h.waitReady()) error("The helper did not start. See ${File(Paths.data, "helper.log")}")
                    helper = h
                    DemoAccess.update(h, demo || c.showDemo)
                    model = Model(Api(h.baseUrl, h.key), scope, hasGemini = c.geminiKey.isNotBlank()).also { it.start() }
                } catch (e: Exception) {
                    candidate?.stop(); startError = e.message
                }
            }.apply { isDaemon = true }.start()
        }

        DisposableEffect(offlineAi) {
            startHelper(cfg)
            onDispose {
                DemoAccess.clear()
                model?.stop()
                helper?.stop()
                offlineAi.close()
            }
        }
        LaunchedEffect(visible) {
            if (visible && !offlineAiOpened) {
                offlineAiOpened = true
                offlineAi.start()
            }
        }

        fun open(target: Screen = Screen.HOME) { screen = target; visible = true }

        // Focus reminders: decided here on the PC, shown as a Windows notification, never stored or sent.
        val trayState = rememberTrayState()
        fun phoneReminder() = trayState.sendNotification(Notification("Phone break?", "You've been looking away from the screen for a bit. Back to it when you're ready.", Notification.Type.Info))
        LaunchedEffect(model, cfg.focusReminders) {
            val m = model ?: return@LaunchedEffect
            if (!cfg.focusReminders) return@LaunchedEffect
            var lastPhone = 0L
            var lastPause = 0L
            var idleSince: Long? = null
            while (true) {
                val now = System.currentTimeMillis()
                val down = m.presence.value?.lookingDownSeconds ?: 0.0
                if (down >= FocusRules.PHONE_SECONDS && now - lastPhone > FocusRules.PHONE_COOLDOWN_MS) {
                    lastPhone = now
                    phoneReminder()
                }
                val idle = m.worktime.value?.state == "idle"
                idleSince = if (idle) idleSince ?: now else null
                val since = idleSince
                if (since != null && now - since >= FocusRules.PAUSE_MS && now - lastPause > FocusRules.PAUSE_COOLDOWN_MS) {
                    lastPause = now
                    trayState.sendNotification(Notification("Still working?", "No activity for a while, so your active time is paused. It starts again as soon as you are back.", Notification.Type.Info))
                }
                kotlinx.coroutines.delay(1_000)
            }
        }

        Tray(
            state = trayState,
            icon = TrayIcon,
            tooltip = "itor",
            onAction = { open() },
            menu = {
                Item("Open itor", onClick = { open() })
                Item("Fix my problem", onClick = { open(); model?.describe() })
                Item("Ask IT", onClick = { open(); askIt = null; model?.resetTicket(); askItOpen = true })
                // Presenter controls, only with Show demo tools (or --demo).
                if (demo || cfg.showDemo) {
                    Separator()
                    Menu("Demo") {
                        Item("Stuck video export", onClick = { model?.demoScenario("video_export") })
                        Item("Memory leak", onClick = { model?.demoScenario("memory_leak") })
                        Item("Sync loop", onClick = { model?.demoScenario("sync_loop") })
                        Item("Stop the demo process", onClick = { model?.demoStop() })
                        Separator()
                        Item("Simulate outage", onClick = { model?.demoOutage(true) })
                        Item("End outage", onClick = { model?.demoOutage(false) })
                        Item("Add a demo morning", onClick = { model?.demoMorning() })
                        Item("Test phone reminder", onClick = { phoneReminder() })
                    }
                }
                Separator()
                Item("Quit", onClick = { exitApplication() })
            },
        )

        Window(
            onCloseRequest = { visible = false }, // closing hides to the tray; Quit is in the tray menu
            visible = visible,
            title = "itor",
            icon = TrayIcon,
            state = rememberWindowState(size = DpSize(460.dp, 680.dp)),
        ) {
            ItorTheme(dark = cfg.theme != "light") {
                Column(Modifier.fillMaxSize().background(colors.bg)) {
                    TopBar(screen, cfg.showTeam, showCamera = cfg.webcamPresence, dark = cfg.theme != "light", camera = model?.presence?.collectAsState()?.value,
                        onTheme = { cfg = cfg.copy(theme = if (cfg.theme == "light") "dark" else "light"); ConfigStore.save(cfg) },
                    ) { screen = it }
                    Box(Modifier.fillMaxSize()) {
                        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                            val m = model
                            when {
                                m == null -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                    val error = startError
                                    if (error != null) {
                                        T(error, 13, color = colors.warn)
                                    } else {
                                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Spinner()
                                            T("Starting itor", 13, color = colors.muted)
                                        }
                                    }
                                    OfflineAiSetup(offlineAi, showReady = false)
                                }
                                // Tab switch: quick fade + 6 dp rise, 180 ms ease-out.
                                else -> AnimatedContent(
                                    screen,
                                    transitionSpec = {
                                        (fadeIn(tween(180, easing = LinearOutSlowInEasing)) +
                                            slideInVertically(tween(180, easing = LinearOutSlowInEasing)) { 12 }) togetherWith
                                            fadeOut(tween(120))
                                    },
                                ) { tab ->
                                    when (tab) {
                                        Screen.HOME -> Home(
                                            m,
                                            offlineAi = offlineAi,
                                            onAskIT = { diagnosis -> askIt = diagnosis; m.resetTicket(); askItOpen = true },
                                            onMyDay = { screen = Screen.DAY },
                                            noticeSeen = cfg.noticeSeen,
                                            onNoticeSeen = { cfg = cfg.copy(noticeSeen = true); ConfigStore.save(cfg) },
                                        )
                                        Screen.DAY -> MyDay(m)
                                        Screen.TEAM -> Team(m)
                                        Screen.CAMERA -> Camera(m)
                                        Screen.SETTINGS -> Settings(cfg, demo, m, offlineAi) { updated ->
                                            cfg = updated; config = updated
                                            ConfigStore.save(updated); applyAutostart(updated.autostart)
                                            startHelper(updated); screen = Screen.HOME
                                        }
                                    }
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
private fun TopBar(screen: Screen, showTeam: Boolean, showCamera: Boolean = false, dark: Boolean, camera: Presence? = null, onTheme: () -> Unit, onSelect: (Screen) -> Unit) {
    val tabs = remember { mutableStateMapOf<Screen, Pair<Float, Float>>() } // x and width in px, in window coordinates
    Column(Modifier.fillMaxWidth().background(colors.surface)) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            M("itor", 14, weight = FontWeight.Medium)
            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(14.dp, Alignment.End), verticalAlignment = Alignment.CenterVertically) {
                listOfNotNull(Screen.HOME to "Home", Screen.DAY to "My day", if (showTeam) Screen.TEAM to "Team" else null,
                    if (showCamera) Screen.CAMERA to "Camera" else null,
                    Screen.SETTINGS to "Settings").forEach { (target, label) ->
                    T(label, 13, if (target == screen) FontWeight.SemiBold else FontWeight.Normal,
                        if (target == screen) colors.text else colors.muted,
                        Modifier.clickable { onSelect(target) }.onGloballyPositioned {
                            tabs[target] = it.positionInRoot().x to it.size.width.toFloat()
                        })
                }
                // Camera indicator: always visible while the webcam is in use (transparency).
                if (camera != null && camera.state in setOf("starting", "present", "away")) {
                    Box(Modifier.size(7.dp).background(if (camera.state == "present") colors.ok else colors.warn, itor.ui.SmallCorner))
                }
                // Light / dark toggle: shows the mode you switch to.
                Box(Modifier.clickable(onClick = onTheme)) {
                    itor.ui.Ico(if (dark) "sun" else "moon", 15, colors.muted)
                }
            }
        }
        // Bottom border with the active-tab indicator sliding under the label (180 ms ease-out).
        val (x, w) = tabs[screen] ?: (0f to 0f)
        val ix by animateFloatAsState(x, tween(180, easing = LinearOutSlowInEasing))
        val iw by animateFloatAsState(w, tween(180, easing = LinearOutSlowInEasing))
        val density = LocalDensity.current
        Box(Modifier.fillMaxWidth().height(1.dp).background(colors.border)) {
            if (w > 0f) Box(
                Modifier.offset { IntOffset(ix.toInt(), 0) }.width(with(density) { iw.toDp() }).height(1.dp).background(colors.text),
            )
        }
    }
}
