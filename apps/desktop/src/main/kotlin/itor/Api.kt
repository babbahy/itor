@file:OptIn(ExperimentalSerializationApi::class)

package itor

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

// Models: only the fields the app uses. Field names follow the helper's JSON (snake_case).

@Serializable data class Service(val state: String = "unknown", val explanation: String = "")

@Serializable
data class Connectivity(
    val offlineRescue: Boolean = false,
    val simulatedCloudOutage: Boolean = false,
    val internet: Service = Service(),
    val networkInterface: Service = Service(),
    val ollama: Service = Service(),
)

@Serializable data class Workload(val active: Boolean = false, val app: String? = null, val story: String? = null)

@Serializable data class Status(val connectivity: Connectivity = Connectivity(), val demo: Workload = Workload(), val model: String? = null)

@Serializable
data class Finding(val id: String, val title: String, val category: String = "", val recommendedActionIds: List<String> = emptyList())

@Serializable data class Readiness(val readiness: String = "unknown", val findings: List<Finding> = emptyList())

@Serializable data class Snapshot(val cpuPercent: Double? = null, val memoryPercent: Double? = null, val diskPercent: Double? = null)

@Serializable
data class Preflight(val id: String, val readiness: String, val findings: List<Finding> = emptyList(), val snapshot: Snapshot = Snapshot())

@Serializable
data class Diagnosis(
    val provider: String,
    val model: String? = null,
    val headline: String,
    val explanation: String,
    val safeSteps: List<String> = emptyList(),
    val recommendedActionId: String? = null,
)

@Serializable
data class WorkDay(
    val employee: String = "",
    val activeSeconds: Double = 0.0,
    val idleSeconds: Double = 0.0,
    val lostSeconds: Double = 0.0,
    val paidSecondsTotal: Double = 0.0,
    val lostByCause: Map<String, Double> = emptyMap(),
    val frozenApps: Map<String, Double> = emptyMap(),
    val firstSeen: String? = null,
    val state: String = "unknown",
    val blocked: Boolean = false,
)

@Serializable
data class Fix(val id: String, val title: String, val whatItDoes: String, val command: String, val needsAdmin: Boolean, val supported: Boolean)

@Serializable
data class FixRun(
    val id: String,
    val title: String,
    val status: String,
    val approvalToken: String? = null,
    val internetBefore: String? = null,
    val internetAfter: String? = null,
    val message: String? = null,
)

@Serializable data class Verification(val processExited: Boolean = false, val improved: Boolean = false)

@Serializable
data class Action(
    val id: String,
    val status: String,
    val title: String,
    val scope: String = "",
    val sideEffects: String = "",
    val approvalToken: String? = null,
    val message: String? = null,
    val verification: Verification? = null,
)

@Serializable data class Ticket(val id: String, val sent: Boolean, val createdAt: String)

@Serializable
data class CompanyStatus(val configured: Boolean = false, val employee: String = "", val pending: Int = 0, val lastSentAt: String? = null)

@Serializable
data class TeamRow(
    val rank: Int,
    val employee: String,
    val activeSeconds: Double = 0.0,
    val lostSeconds: Double = 0.0,
    val idleSeconds: Double = 0.0,
    val paidSecondsTotal: Double = 0.0,
    val activeShare: Double = 0.0,
    val example: Boolean = false,
)

@Serializable
data class TeamTicket(
    val id: String,
    val employee: String,
    val message: String,
    val createdAt: String,
    val connection: List<String> = emptyList(),
    val diagnosis: String? = null,
)

@Serializable
data class Team(
    val rows: List<TeamRow> = emptyList(),
    val lostByCause: Map<String, Double> = emptyMap(),
    val totalLostSeconds: Double = 0.0,
    val tickets: List<TeamTicket> = emptyList(),
)

class ApiError(message: String) : Exception(message)

/** Talks to the local helper on 127.0.0.1. */
class Api(private val baseUrl: String, private val key: String) {
    private val client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build()
    val json = Json { ignoreUnknownKeys = true; namingStrategy = JsonNamingStrategy.SnakeCase; explicitNulls = false }

    private suspend fun <T> call(method: String, path: String, body: String?, serializer: KSerializer<T>, timeout: Long): T =
        withContext(Dispatchers.IO) {
            val request = HttpRequest.newBuilder(URI("$baseUrl/api/$path"))
                .timeout(Duration.ofSeconds(timeout))
                .header("X-Itor-Key", key)
                .header("Content-Type", "application/json")
                .method(method, if (body == null) HttpRequest.BodyPublishers.noBody() else HttpRequest.BodyPublishers.ofString(body))
                .build()
            val response = try {
                client.send(request, HttpResponse.BodyHandlers.ofString())
            } catch (error: java.io.IOException) {
                throw ApiError("itor's helper is not answering. Restart itor.")
            }
            if (response.statusCode() >= 400) {
                val detail = runCatching {
                    json.parseToJsonElement(response.body()).let { (it as JsonObject)["detail"]?.jsonPrimitive?.contentOrNull }
                }.getOrNull()
                throw ApiError(detail ?: "Request failed (${response.statusCode()}).")
            }
            json.decodeFromString(serializer, response.body())
        }

    private suspend fun <T> get(path: String, serializer: KSerializer<T>, timeout: Long = 10) = call("GET", path, null, serializer, timeout)

    private suspend fun <T> post(path: String, body: String, serializer: KSerializer<T>, timeout: Long = 30) =
        call("POST", path, body, serializer, timeout)

    private fun obj(vararg pairs: Pair<String, Any?>): String = buildString {
        append('{')
        pairs.forEachIndexed { index, (name, value) ->
            if (index > 0) append(',')
            append(Json.encodeToString(String.serializer(), name)).append(':')
            append(
                when (value) {
                    null -> "null"
                    is Boolean, is Number -> value.toString()
                    else -> Json.encodeToString(String.serializer(), value.toString())
                },
            )
        }
        append('}')
    }

    suspend fun status() = get("status", Status.serializer())
    suspend fun readiness() = get("device/readiness", Readiness.serializer())
    suspend fun worktime() = get("worktime/today", WorkDay.serializer())
    suspend fun company() = get("company/status", CompanyStatus.serializer())
    suspend fun fixes() = get("fixes", ListSerializer(Fix.serializer()))
    suspend fun team() = get("company/team", Team.serializer())

    suspend fun preflight() = post("preflight", "{}", Preflight.serializer())

    /** The local AI can take up to 2 minutes on a laptop without a graphics card. */
    suspend fun explain(sessionId: String, question: String): Diagnosis =
        if (question.isBlank()) post("diagnose", obj("session_id" to sessionId), Diagnosis.serializer(), 180)
        else post("diagnosis/chat", obj("question" to question.take(400), "session_id" to sessionId), Diagnosis.serializer(), 180)

    suspend fun planFix(id: String) = post("fixes/$id/plan", "{}", FixRun.serializer())
    suspend fun approveFix(run: FixRun) =
        post("fixes/runs/${run.id}/approve", obj("approval_token" to run.approvalToken, "approved" to true), FixRun.serializer(), 120)
    suspend fun cancelFix(run: FixRun) = post("fixes/runs/${run.id}/cancel", obj("approval_token" to run.approvalToken), FixRun.serializer())

    suspend fun planStop(sessionId: String) =
        post("actions/plan", obj("session_id" to sessionId, "action_id" to "stop_demo_workload"), Action.serializer())
    suspend fun approveStop(action: Action) =
        post("actions/${action.id}/approve", obj("approval_token" to action.approvalToken, "approved" to true), Action.serializer())
    suspend fun cancelStop(action: Action) = post("actions/${action.id}/cancel", obj("approval_token" to action.approvalToken), Action.serializer())
    suspend fun action(id: String) = get("actions/$id", Action.serializer())

    suspend fun ticket(message: String, diagnosis: String?) =
        post("support/ticket", obj("message" to message.take(1000), "diagnosis" to diagnosis?.take(300)), Ticket.serializer())

    suspend fun setBlocked(blocked: Boolean) = post("worktime/blocked", obj("blocked" to blocked), WorkDay.serializer())

    // Demo
    suspend fun demoMorning() = post("demo/worktime", "{}", WorkDay.serializer())
    suspend fun demoCloud(enabled: Boolean) = post("demo/cloud", obj("enabled" to enabled), JsonObject.serializer())
    suspend fun demoStart(scenario: String) = post("demo/start", obj("scenario" to scenario), JsonObject.serializer())
}

