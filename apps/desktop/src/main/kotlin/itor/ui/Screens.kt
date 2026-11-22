package itor.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.border
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import itor.Config
import itor.Model
import itor.OfflineAi
import itor.OfflineAiPhase

/** Modal over the window: flat card on a plain dim layer (no blur, no glass). */
@Composable
fun Overlay(content: @Composable ColumnScope.() -> Unit) {
    Box(
        Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.45f))
            .clickable(MutableInteractionSource(), indication = null) {},
        contentAlignment = Alignment.Center,
    ) {
        Card(Modifier.widthIn(max = 440.dp).padding(16.dp), content = content)
    }
}

@Composable
fun AskIt(model: Model, diagnosis: String?, onClose: () -> Unit) {
    val ticket by model.ticket.collectAsState()
    val error by model.ticketError.collectAsState()
    val sending by model.sendingTicket.collectAsState()
    var message by remember { mutableStateOf("") }
    Overlay {
        Row2(left = { T("Ask IT", 15, FontWeight.SemiBold) }, right = { Box(Modifier.clickable(onClick = onClose)) { Ico("x", 16, colors.muted) } })
        val sent = ticket
        if (sent != null) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Ico(if (sent.sent) "send" else "wifi-off", 16, if (sent.sent) colors.ok else colors.warn)
                T(if (sent.sent) "Sent to IT" else "Saved. It will be sent when you are back online.", 14, FontWeight.Medium)
            }
            M("ticket ${sent.id.take(8)} · ${localTime(sent.createdAt)}", 12, colors.muted)
            Btn("Close", onClose, primary = true)
        } else {
            Label("what is wrong")
            Field(message, { message = it }, "e.g. since this morning, websites do not load", lines = 4)
            T(
                "itor adds automatically: your PC status, the connection checks" +
                    (diagnosis?.let { ", what it found (\"$it\")" } ?: "") + " and the fixes already tried.",
                12, color = colors.muted,
            )
            error?.let { M(it, 12, colors.warn) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn("Cancel", onClose)
                Btn("Send to IT", { model.sendTicket(message, diagnosis) }, primary = true, enabled = message.isNotBlank(), busy = sending, icon = "send")
            }
        }
    }
}

@Composable
fun MyDay(model: Model) {
    val day by model.worktime.collectAsState()
    val company by model.company.collectAsState()
    val d = day
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card {
            Row2(
                left = { T("Today", 15, FontWeight.SemiBold) },
                right = {
                    val (text, color) = when (d?.state) {
                        "active" -> "active" to colors.ok
                        "lost" -> "losing time" to colors.warn
                        "idle" -> "idle" to colors.muted
                        else -> "starting" to colors.muted
                    }
                    M(text, 12, color)
                },
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Stat("active", d?.activeSeconds, Modifier.weight(1f))
                Stat("lost", d?.lostSeconds, Modifier.weight(1f), colors.warn)
                Stat("idle", d?.idleSeconds, Modifier.weight(1f))
                Stat("to pay", d?.paidSecondsTotal, Modifier.weight(1f))
            }
            Bar(d?.activeSeconds ?: 0.0, d?.lostSeconds ?: 0.0, d?.idleSeconds ?: 0.0)
            d?.lostByCause?.filterValues { it >= 30 }?.entries?.sortedByDescending { it.value }?.forEach { (cause, seconds) ->
                Row2(left = { T(causeLabels[cause] ?: cause, 13, color = colors.muted) }, right = { M(duration(seconds), 12) })
            }
            d?.frozenApps?.filterValues { it >= 30 }?.forEach { (app, seconds) ->
                Row2(left = { M("frozen: $app", 12, colors.muted) }, right = { M(duration(seconds), 12) })
            }
            val cam = model.presence.collectAsState().value
            if (cam?.enabled == true) Row2(
                left = { T("Webcam presence", 13, color = colors.muted) },
                right = { M(when (cam.state) { "present" -> "at desk"; "away" -> "away"; "no_camera" -> "no webcam"; "error" -> "stopped"; else -> "starting" }, 12,
                    if (cam.state == "present") colors.ok else if (cam.state == "away") colors.warn else colors.muted) },
            )
            T(
                if (cam?.enabled == true) "Active: at your desk (webcam) or mouse/keyboard used in the last 2 min. Lost: you were working but a tool got in the way."
                else "Active: mouse or keyboard used in the last 2 min. Lost: you were working but a tool got in the way.",
                12, color = colors.muted,
            )
            Btn(if (d?.blocked == true) "I am not blocked anymore" else "I am blocked", { model.setBlocked(d?.blocked != true) }, icon = "hand")
        }
        Card {
            T("What your manager sees", 14, FontWeight.SemiBold)
            Row2(left = { T("Name", 13, color = colors.muted) }, right = { M(company?.employee ?: d?.employee ?: "--", 12) })
            Row2(left = { T("Active / lost / idle", 13, color = colors.muted) }, right = {
                M("${duration(d?.activeSeconds)} / ${duration(d?.lostSeconds)} / ${duration(d?.idleSeconds)}", 12)
            })
            Row2(left = { T("Hours to pay", 13, color = colors.muted) }, right = { M(duration(d?.paidSecondsTotal), 12) })
            Row2(left = { T("Sent to", 13, color = colors.muted) }, right = {
                M(when {
                    company == null -> "--"
                    (company?.pending ?: 0) > 0 -> "${company?.pending} waiting (offline)"
                    company?.lastSentAt != null -> "company · ${localTime(company?.lastSentAt)}"
                    else -> "company · soon"
                }, 12)
            })
            T("Only your company sees this, never Nexthink. Never collected: what you type, screenshots, websites, app usage.", 12, color = colors.muted)
        }
    }
}

@Composable
private fun Stat(label: String, seconds: Double?, modifier: Modifier, color: Color = colors.text) =
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Label(label)
        M(duration(seconds), 18, color, FontWeight.Medium)
    }

@Composable
private fun Bar(active: Double, lost: Double, idle: Double) {
    val total = (active + lost + idle).takeIf { it > 0 } ?: 1.0
    Row(Modifier.fillMaxWidth().height(6.dp).background(colors.border, SmallCorner)) {
        if (active > 0) Box(Modifier.weight((active / total).toFloat()).fillMaxHeight().background(colors.ok))
        if (lost > 0) Box(Modifier.weight((lost / total).toFloat()).fillMaxHeight().background(colors.warn))
        if (idle > 0) Box(Modifier.weight((idle / total).toFloat()).fillMaxHeight().background(colors.border))
    }
}

@Composable
internal fun Settings(config: Config, demo: Boolean, model: Model, offlineAi: OfflineAi, onSave: (Config) -> Unit) {
    var name by remember { mutableStateOf(config.employeeName) }
    var gemini by remember { mutableStateOf(config.geminiKey) }
    var url by remember { mutableStateOf(config.companyUrl) }
    var key by remember { mutableStateOf(config.companyKey) }
    var autostart by remember { mutableStateOf(config.autostart) }
    var showTeam by remember { mutableStateOf(config.showTeam) }
    var showDemo by remember { mutableStateOf(config.showDemo) }
    var webcam by remember { mutableStateOf(config.webcamPresence) }
    var reminders by remember { mutableStateOf(config.focusReminders) }
    val setup by offlineAi.state.collectAsState()
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OfflineAiSetup(offlineAi, showReady = true)
        Card {
            T("Settings", 15, FontWeight.SemiBold)
            if (setup.phase == OfflineAiPhase.EXTERNAL) {
                val engine by model.status.collectAsState()
                val ready = engine?.connectivity?.ollama?.state == "connected"
                Row(
                    Modifier.fillMaxWidth().border(1.dp, colors.border, SmallCorner).padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Box(Modifier.size(6.dp).background(if (ready) colors.ok else colors.warn, SmallCorner))
                    T("Offline engine", 13, FontWeight.Medium)
                    val status = when {
                        ready -> "${engine?.model ?: "Qwen"} · ready"
                        engine == null -> "Checking local AI"
                        else -> "Local AI unavailable"
                    }
                    M(status, 11, colors.muted)
                }
            }
            Label("your name (shown to your manager)")
            Field(name, { name = it }, "default: Windows user name")
            Label("cloud ai fallback (optional)")
            Field(gemini, { gemini = it }, "aistudio.google.com/apikey", secret = true)
            Label("company server")
            Field(url, { url = it }, "empty: this PC acts as the server")
            Field(key, { key = it }, "company key", secret = true)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(autostart, { autostart = it }, colors = CheckboxDefaults.colors(checkedColor = colors.inverse, checkmarkColor = colors.onInverse))
                T("Start itor with Windows", 13)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(showTeam, { showTeam = it }, colors = CheckboxDefaults.colors(checkedColor = colors.inverse, checkmarkColor = colors.onInverse))
                T("Show manager view", 13)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(showDemo, { showDemo = it }, colors = CheckboxDefaults.colors(checkedColor = colors.inverse, checkmarkColor = colors.onInverse))
                T("Show demo tools", 13)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(webcam, { webcam = it }, colors = CheckboxDefaults.colors(checkedColor = colors.inverse, checkmarkColor = colors.onInverse))
                Column {
                    T("Use my webcam to know if I'm at my desk", 13)
                    T("On this PC only. No image is saved or sent: only present / away. Off by default.", 11, color = colors.muted)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(reminders, { reminders = it }, colors = CheckboxDefaults.colors(checkedColor = colors.inverse, checkmarkColor = colors.onInverse))
                Column {
                    T("Focus reminders", 13)
                    T("A gentle notification when you look at your phone for a while (needs the webcam) or after a long pause. " +
                        "Only on this PC: never saved, never sent, your manager never sees it.", 11, color = colors.muted)
                }
            }
            Btn("Save and restart helper", {
                onSave(config.copy(employeeName = name, geminiKey = gemini, companyUrl = url, companyKey = key, autostart = autostart, showTeam = showTeam, showDemo = showDemo, webcamPresence = webcam, focusReminders = reminders))
            }, primary = true)
        }
        if (demo || showDemo) Card {
            T("Demo", 15, FontWeight.SemiBold)
            Btn("Add a demo morning", model::demoMorning)
            Label("simulate a problem (a real process that slows the pc)")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn("Stuck video export", { model.demoScenario("video_export") })
                Btn("Memory leak", { model.demoScenario("memory_leak") })
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn("Sync loop", { model.demoScenario("sync_loop") })
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn("Simulate outage", { model.demoOutage(true) })
                Btn("End outage", { model.demoOutage(false) })
            }
        }
    }
}

/** ISO time from the helper (UTC) shown in the PC's local time, e.g. 01:23. */
fun localTime(iso: String?): String = runCatching {
    java.time.OffsetDateTime.parse(iso).atZoneSameInstant(java.time.ZoneId.systemDefault())
        .format(java.time.format.DateTimeFormatter.ofPattern("HH:mm"))
}.getOrDefault("--")
