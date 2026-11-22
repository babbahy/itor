package itor.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import itor.Approval
import itor.Diagnosis
import itor.FixState
import itor.HomeStatus
import itor.Model
import itor.Step
import itor.Tone

@Composable
fun Home(model: Model, onAskIT: (String?) -> Unit, onMyDay: () -> Unit, noticeSeen: Boolean, onNoticeSeen: () -> Unit) {
    val status by model.status.collectAsState()
    val readiness by model.readiness.collectAsState()
    val down by model.down.collectAsState()
    val fix by model.fix.collectAsState()
    val day by model.worktime.collectAsState()
    val home = model.homeStatus(status, readiness, down)
    val approval by model.approval.collectAsState()
    val mood = when {
        fix is FixState.Checking || (approval as? Approval.QuickFix)?.running == true ||
            (approval as? Approval.StopTask)?.running == true -> Mood.WORKING
        home.offline -> Mood.OFFLINE
        home.tone == Tone.WARN -> Mood.WARN
        else -> Mood.CALM
    }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (!noticeSeen) Notice(onNoticeSeen)
        PixelField(mood)
        StatusCard(home)
        when (val state = fix) {
            FixState.Idle -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn("Fix my problem", model::describe, Modifier.fillMaxWidth(), primary = true, enabled = !down, icon = "wrench", big = true)
                Btn("Ask IT", { onAskIT(null) }, Modifier.fillMaxWidth(), enabled = !down, icon = "message-square", big = true)
            }
            FixState.Describing -> Describe(model, down)
            is FixState.Checking -> StepList(state.steps, state.startedAt)
            is FixState.Answer -> Answer(model, state, onAskIT)
            is FixState.Failed -> Card(borderColor = colors.warn) {
                T(state.message, 13)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Btn("Try again", model::describe)
                    Btn("Ask IT", { onAskIT(null) }, icon = "message-square")
                }
            }
        }
        Row2(
            left = {
                Label("today")
                Spacer(Modifier.width(8.dp))
                M(duration(day?.paidSecondsTotal), 12)
                M(" worked", 12, colors.muted)
            },
            right = { LinkText("Details", onMyDay); Ico("chevron-right", 14, colors.muted) },
        )
    }
    ApprovalDialog(model)
}

@Composable
private fun StatusCard(home: HomeStatus) {
    val accent = home.tone.color(colors)
    Card(borderColor = if (home.tone == Tone.WARN) accent else colors.border) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Ico(
                when {
                    home.offline -> "wifi-off"
                    home.tone == Tone.OK -> "circle-check"
                    home.tone == Tone.WARN -> "triangle-alert"
                    else -> "loader-circle"
                },
                22, accent,
            )
            Column {
                T(home.title, 18, FontWeight.SemiBold)
                T(home.detail, 13, color = colors.muted)
            }
        }
    }
}

@Composable
private fun Notice(onSeen: () -> Unit) = Card {
    T("itor counts your working time", 14, FontWeight.SemiBold)
    T(
        "Measured: whether the mouse or keyboard was used (active / idle) and time lost because of tools " +
            "(internet down, PC overloaded, frozen app). Never measured: what you type, screenshots, websites. " +
            "Your manager sees the same numbers as you, inside the company only.",
        13, color = colors.muted,
    )
    Btn("OK", onSeen)
}

@Composable
private fun Describe(model: Model, down: Boolean) {
    var question by remember { mutableStateOf("") }
    Card {
        Label("what is not working (optional)")
        Field(question, { question = it }, "e.g. websites do not load, Teams is frozen", onDone = { model.check(question) })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Btn("Check and fix", { model.check(question) }, primary = true, enabled = !down, icon = "wrench")
            Btn("Cancel", model::closeFix)
        }
    }
}

private fun source(d: Diagnosis) = when (d.provider) {
    "gemini" -> "source: gemini · ${d.model ?: "online"}"
    "ollama" -> "source: local-ai · ${d.model ?: "qwen"}"
    else -> "source: rules"
}

@Composable
private fun Answer(model: Model, state: FixState.Answer, onAskIT: (String?) -> Unit) {
    val fixes by model.fixes.collectAsState()
    val result by model.lastResult.collectAsState()
    val d = state.diagnosis
    Card {
        M(source(d), 11, colors.muted)
        T(d.headline, 15, FontWeight.SemiBold)
        T(d.explanation, 13, color = colors.muted)
        d.safeSteps.forEach { step -> T("- $step", 13, color = colors.muted) }
        Divider()
        Label("what itor can try")
        if (d.recommendedActionId == "stop_demo_workload") {
            FixRow("Stop the background task slowing your PC") { model.askStopTask(state.session) }
        }
        fixes.filter { it.supported }.forEach { item -> FixRow(item.title) { model.askQuickFix(item) } }
        if (fixes.none { it.supported } && d.recommendedActionId == null) M("no safe fix available on this PC", 12, colors.muted)
        result?.let { M(it, 12, if (it.contains("succeeded") || it.startsWith("Background")) colors.ok else colors.muted) }
        Divider()
        Row2(
            left = { T("Still not working?", 13, color = colors.muted) },
            right = {
                Btn("Ask IT", { onAskIT(d.headline) }, icon = "message-square")
                Spacer(Modifier.width(8.dp))
                Btn("Done", model::closeFix)
            },
        )
    }
}

@Composable
private fun FixRow(title: String, onRun: () -> Unit) = Row2(
    left = { T(title, 13) },
    right = { Btn("Run", onRun, icon = "wrench") },
)

/** Approval: shows exactly what will run. Nothing runs before "Approve and run". */
@Composable
fun ApprovalDialog(model: Model) {
    val approval by model.approval.collectAsState()
    val current = approval ?: return
    val (title, what, command, admin, running, error) = when (current) {
        is Approval.QuickFix -> Sextet(current.fix.title, current.fix.whatItDoes, current.fix.command, current.fix.needsAdmin, current.running, current.error)
        is Approval.StopTask -> Sextet(current.action.title, current.action.scope, "stop itor demo workload (owned process only)", false, current.running, current.error)
    }
    Overlay {
        T("Approve this fix", 15, FontWeight.SemiBold)
        T(title, 14, FontWeight.Medium)
        T(what, 13, color = colors.muted)
        Label("exact command")
        Column(Modifier.fillMaxWidth().background(colors.bg, SmallCorner).border(1.dp, colors.border, SmallCorner).padding(10.dp)) {
            M(command, 12)
        }
        if (admin) M("windows will ask for admin rights", 12, colors.warn)
        error?.let { M(it, 12, colors.warn) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Btn("Decline", model::decline, enabled = !running)
            Btn(if (running) "Running" else "Approve and run", model::approve, primary = true, busy = running, icon = "check")
        }
    }
}

private data class Sextet(val a: String, val b: String, val c: String, val d: Boolean, val e: Boolean, val f: String?)

/** Live check progress: one line per real step, typed in, empty box while running, filled when done. */
@Composable
private fun StepList(steps: List<Step>, startedAt: Long) {
    Card {
        Label("checking your pc and connection")
        steps.forEachIndexed { index, step ->
            val running = !step.done && index == steps.lastIndex
            StepLine(step, running, startedAt)
        }
    }
}

@Composable
private fun StepLine(step: Step, running: Boolean, startedAt: Long) {
    val text = step.detail
    var shown by remember(step.label) { mutableIntStateOf(0) }
    LaunchedEffect(text) {
        if (shown > text.length) shown = 0
        while (shown < text.length) { delay(22); shown++ }
    }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    if (running) LaunchedEffect(Unit) { while (true) { now = System.currentTimeMillis(); delay(250) } }
    val color = when { step.failed -> colors.warn; step.done -> colors.text; else -> colors.muted }
    Row(verticalAlignment = Alignment.CenterVertically) {
        M(if (step.done) "\u25A0" else "\u25A1", 12, color)
        Spacer(Modifier.width(10.dp))
        M(step.label.padEnd(9), 12, colors.text)
        M(text.take(shown), 12, color, modifier = Modifier.weight(1f))
        if (running) M("${(now - startedAt) / 1000}s", 12, colors.muted)
    }
}
