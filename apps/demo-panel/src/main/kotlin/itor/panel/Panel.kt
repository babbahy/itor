package itor.panel

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.WindowPosition
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import itor.Api
import itor.ConfigStore
import itor.DemoAccess
import itor.DemoAccessInfo
import itor.Model
import itor.TrayIcon
import itor.ui.DemoPanel
import itor.ui.ItorTheme
import itor.ui.Spinner
import itor.ui.T
import itor.ui.colors
import kotlinx.coroutines.delay

/**
 * itor demo panel: a separate app for the presenter. Small window, always on top.
 * It finds the running itor through %LOCALAPPDATA%\itor-data\demo-access.json
 * (written by itor only while Settings > Show demo tools is on).
 */
fun main() = application {
    val scope = rememberCoroutineScope()
    var access by remember { mutableStateOf<DemoAccessInfo?>(null) }
    var model by remember { mutableStateOf<Model?>(null) }

    // Find itor, and follow it if it restarts (new address and key).
    LaunchedEffect(Unit) {
        while (true) {
            val found = DemoAccess.read()
            if (found != access) {
                model?.stop()
                access = found
                model = found?.let { Model(Api(it.baseUrl, it.key), scope).also { m -> m.start() } }
            }
            delay(2_000)
        }
    }
    DisposableEffect(Unit) { onDispose { model?.stop() } }

    Window(
        onCloseRequest = ::exitApplication,
        title = "itor demo panel",
        icon = TrayIcon,
        alwaysOnTop = true,
        resizable = false,
        state = rememberWindowState(size = DpSize(280.dp, 480.dp), position = WindowPosition.PlatformDefault),
    ) {
        ItorTheme(dark = ConfigStore.load().theme != "light") {
            val m = model
            if (m != null) {
                DemoPanel(m)
            } else {
                Column(
                    Modifier.fillMaxSize().background(colors.bg).padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    T("Waiting for itor", 14, FontWeight.SemiBold)
                    Spinner()
                    T("Start itor, then turn on Settings > Show demo tools and click Save.", 12, color = colors.muted)
                }
            }
        }
    }
}
