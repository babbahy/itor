package itor.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import itor.Model

/** Presenter panel: trigger the demo problems from a small window, without opening Settings. */
@Composable
fun DemoPanel(model: Model) {
    val status by model.status.collectAsState()
    val net = status?.connectivity
    val outage = net?.simulatedCloudOutage == true
    val running = status?.demo?.takeIf { it.active }?.app
    Column(
        Modifier.fillMaxSize().background(colors.bg).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.size(6.dp).background(if (running != null || outage) colors.warn else colors.ok, SmallCorner))
            M(
                when {
                    running != null && outage -> "running: $running · outage on"
                    running != null -> "running: $running"
                    outage -> "outage on"
                    else -> "all calm"
                },
                11, colors.muted,
            )
        }
        Label("slow the pc (real process)")
        Btn("Stuck video export", { model.demoScenario("video_export") }, Modifier.fillMaxWidth(), enabled = running == null, icon = "wrench")
        Btn("Memory leak", { model.demoScenario("memory_leak") }, Modifier.fillMaxWidth(), enabled = running == null, icon = "wrench")
        Btn("Sync loop", { model.demoScenario("sync_loop") }, Modifier.fillMaxWidth(), enabled = running == null, icon = "wrench")
        Btn("Stop the demo process", model::demoStop, Modifier.fillMaxWidth(), enabled = running != null, icon = "x")
        Label("network")
        Btn(if (outage) "End outage" else "Simulate outage", { model.demoOutage(!outage) }, Modifier.fillMaxWidth(), icon = "wifi-off")
        Label("time clock")
        Btn("Add a demo morning", model::demoMorning, Modifier.fillMaxWidth(), icon = "clock")
        T("Real Wi-Fi off works too. Only visible with Show demo tools.", 11, color = colors.muted)
    }
}

