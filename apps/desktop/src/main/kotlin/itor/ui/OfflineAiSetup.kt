package itor.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.progressSemantics
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import itor.OfflineAi
import itor.OfflineAiPhase
import java.util.Locale
import kotlin.math.roundToInt

@Composable
internal fun OfflineAiSetup(offlineAi: OfflineAi, showReady: Boolean) {
    val state by offlineAi.state.collectAsState()
    val phase = state.phase
    if (phase == OfflineAiPhase.EXTERNAL || (phase == OfflineAiPhase.READY && !showReady)) return

    val title = when (phase) {
        OfflineAiPhase.STARTING -> "Preparing offline AI"
        OfflineAiPhase.DOWNLOADING_RUNTIME -> "Downloading the offline AI runtime"
        OfflineAiPhase.INSTALLING_RUNTIME -> "Installing the offline AI runtime"
        OfflineAiPhase.DOWNLOADING_MODEL -> "Downloading the offline AI model"
        OfflineAiPhase.READY -> "Offline AI ready"
        OfflineAiPhase.PAUSED -> "Offline AI setup paused"
        OfflineAiPhase.FAILED -> "Offline AI setup needs attention"
        OfflineAiPhase.EXTERNAL -> return
    }
    val working = when (phase) {
        OfflineAiPhase.STARTING, OfflineAiPhase.DOWNLOADING_RUNTIME,
        OfflineAiPhase.INSTALLING_RUNTIME, OfflineAiPhase.DOWNLOADING_MODEL -> true
        else -> false
    }

    Card(borderColor = if (phase == OfflineAiPhase.FAILED) colors.warn else colors.border) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when (phase) {
                OfflineAiPhase.READY -> Ico("circle-check", tint = colors.ok)
                OfflineAiPhase.FAILED -> Ico("triangle-alert", tint = colors.warn)
                else -> if (working) Spinner()
            }
            T(title, 14, FontWeight.SemiBold)
        }

        state.detail?.takeIf { it.isNotBlank() }?.let { T(it, 12, color = colors.muted) }
        if (phase == OfflineAiPhase.READY) {
            T("The model is available on this PC even without internet.", 12, color = colors.muted)
        } else {
            T("First setup downloads about 4.3 GB. You can still use itor’s basic checks.", 12, color = colors.muted)
        }

        val completed = state.completed
        if ((working || phase == OfflineAiPhase.PAUSED) && completed != null) {
            DownloadProgress(completed, state.total)
        }

        when (phase) {
            OfflineAiPhase.PAUSED -> Btn("Resume", offlineAi::start)
            OfflineAiPhase.FAILED -> Btn("Retry", offlineAi::start)
            else -> if (working) Btn("Pause", offlineAi::pause)
        }
    }
}

@Composable
private fun DownloadProgress(completed: Long, total: Long?) {
    if (total == null || total <= 0) {
        M("${downloadSize(completed)} downloaded", 12, colors.muted)
        return
    }
    val progress = (completed.toDouble() / total).coerceIn(0.0, 1.0).toFloat()
    Box(Modifier.fillMaxWidth().height(5.dp).background(colors.border, SmallCorner).progressSemantics(progress)) {
        Box(Modifier.fillMaxWidth(progress).height(5.dp).background(colors.text, SmallCorner))
    }
    M("${downloadSize(completed)} of ${downloadSize(total)} · ${(progress * 100).roundToInt()}%", 12, colors.muted)
}

private fun downloadSize(bytes: Long): String {
    val size = bytes.coerceAtLeast(0)
    val (divisor, unit) = when {
        size >= 1_000_000_000 -> 1_000_000_000.0 to "GB"
        size >= 1_000_000 -> 1_000_000.0 to "MB"
        size >= 1_000 -> 1_000.0 to "KB"
        else -> 1.0 to "B"
    }
    return String.format(Locale.ROOT, "%.1f %s", size / divisor, unit)
}
