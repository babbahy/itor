package itor

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

enum class Tone { OK, WARN, NEUTRAL }

data class HomeStatus(val tone: Tone, val title: String, val detail: String, val offline: Boolean)

/** What the "Fix my problem" panel is doing. */
sealed interface FixState {
    data object Idle : FixState
    data object Describing : FixState
    data object Checking : FixState
    data class Answer(val session: Preflight, val diagnosis: Diagnosis) : FixState
    data class Failed(val message: String) : FixState
}

/** An approval waiting for the employee: a quick fix or stopping the demo workload. */
sealed interface Approval {
    data class QuickFix(val fix: Fix, val run: FixRun, val running: Boolean = false, val error: String? = null) : Approval
    data class StopTask(val action: Action, val running: Boolean = false, val error: String? = null) : Approval
}

class Model(private val api: Api, private val scope: CoroutineScope) {
    val status = MutableStateFlow<Status?>(null)
    val readiness = MutableStateFlow<Readiness?>(null)
    val worktime = MutableStateFlow<WorkDay?>(null)
    val company = MutableStateFlow<CompanyStatus?>(null)
    val fixes = MutableStateFlow<List<Fix>>(emptyList())
    val down = MutableStateFlow(false)

    val fix = MutableStateFlow<FixState>(FixState.Idle)
    val approval = MutableStateFlow<Approval?>(null)
    val lastResult = MutableStateFlow<String?>(null)
    val ticket = MutableStateFlow<Ticket?>(null)
    val ticketError = MutableStateFlow<String?>(null)
    val sendingTicket = MutableStateFlow(false)

    private val jobs = mutableListOf<Job>()

    fun start() {
        jobs += poll(3_000) {
            status.value = api.status()
            readiness.value = api.readiness()
        }
        jobs += poll(5_000) {
            worktime.value = api.worktime()
            company.value = api.company()
        }
        scope.launch { runCatching { fixes.value = api.fixes() } }
    }

    private fun poll(everyMs: Long, block: suspend () -> Unit) = scope.launch {
        while (isActive) {
            down.value = runCatching { block() }.isFailure
            delay(everyMs)
        }
    }

    fun homeStatus(status: Status?, readiness: Readiness?, down: Boolean): HomeStatus {
        val net = status?.connectivity
        val offline = net != null && (net.offlineRescue || net.simulatedCloudOutage ||
            net.internet.state in setOf("disconnected", "unreachable") || net.networkInterface.state == "disconnected")
        return when {
            down -> HomeStatus(Tone.NEUTRAL, "itor is not running", "Restart itor, or ask IT.", false)
            offline -> HomeStatus(Tone.WARN, "You are offline", "itor still works without internet and can help you get back online.", true)
            readiness != null && readiness.readiness in setOf("attention", "not_ready") ->
                HomeStatus(Tone.WARN, "Something is slowing your PC", readiness.findings.firstOrNull()?.title ?: "itor found something to fix.", false)
            status == null -> HomeStatus(Tone.NEUTRAL, "Starting", "Checking your PC and connection.", false)
            else -> HomeStatus(Tone.OK, "Everything looks fine", "Your PC and connection look OK.", false)
        }
    }

    // Fix my problem

    fun describe() { fix.value = FixState.Describing; lastResult.value = null }

    fun check(question: String) {
        fix.value = FixState.Checking
        scope.launch {
            fix.value = try {
                val session = api.preflight()
                FixState.Answer(session, api.explain(session.id, question))
            } catch (error: Exception) {
                FixState.Failed(error.message ?: "The check failed.")
            }
        }
    }

    fun closeFix() { fix.value = FixState.Idle; lastResult.value = null }

    fun askQuickFix(item: Fix) = scope.launch {
        runCatching { api.planFix(item.id) }
            .onSuccess { approval.value = Approval.QuickFix(item, it) }
            .onFailure { lastResult.value = it.message }
    }

    fun askStopTask(session: Preflight) = scope.launch {
        runCatching { api.planStop(session.id) }
            .onSuccess { approval.value = Approval.StopTask(it) }
            .onFailure { lastResult.value = it.message }
    }

    fun approve() {
        when (val current = approval.value) {
            is Approval.QuickFix -> scope.launch {
                approval.value = current.copy(running = true)
                runCatching { api.approveFix(current.run) }
                    .onSuccess { run ->
                        approval.value = null
                        lastResult.value = "${run.title}: ${run.status}" +
                            (if (run.internetAfter != null && run.internetAfter != "not_configured") " · internet ${run.internetBefore} -> ${run.internetAfter}" else "") +
                            (run.message?.takeIf { run.status != "succeeded" }?.let { " · $it" } ?: "")
                    }
                    .onFailure { approval.value = current.copy(running = false, error = it.message) }
            }
            is Approval.StopTask -> scope.launch {
                approval.value = current.copy(running = true)
                try {
                    var action = api.approveStop(current.action)
                    while (action.status in setOf("approved", "executing", "verifying")) {
                        delay(600)
                        action = api.action(action.id)
                    }
                    approval.value = null
                    lastResult.value = if (action.status == "succeeded") "Background task stopped and checked." else
                        "Could not stop the task: ${action.message ?: action.status}"
                } catch (error: Exception) {
                    approval.value = current.copy(running = false, error = error.message)
                }
            }
            null -> Unit
        }
    }

    fun decline() {
        when (val current = approval.value) {
            is Approval.QuickFix -> scope.launch { runCatching { api.cancelFix(current.run) } }
            is Approval.StopTask -> scope.launch { runCatching { api.cancelStop(current.action) } }
            null -> Unit
        }
        approval.value = null
        lastResult.value = "Declined. Nothing was run."
    }

    // Ask IT

    fun resetTicket() { ticket.value = null; ticketError.value = null }

    fun sendTicket(message: String, diagnosis: String?) = scope.launch {
        sendingTicket.value = true
        ticketError.value = null
        runCatching { api.ticket(message, diagnosis) }
            .onSuccess { ticket.value = it }
            .onFailure { ticketError.value = it.message }
        sendingTicket.value = false
    }

    // My day

    fun setBlocked(blocked: Boolean) = scope.launch { runCatching { worktime.value = api.setBlocked(blocked) } }

    // Demo

    fun demoMorning() = scope.launch { runCatching { worktime.value = api.demoMorning() } }
    fun demoOutage(on: Boolean) = scope.launch { runCatching { api.demoCloud(on); status.value = api.status() } }
    fun demoCpu() = scope.launch { runCatching { api.demoStart() } }

    fun stop() = jobs.forEach { it.cancel() }
}

