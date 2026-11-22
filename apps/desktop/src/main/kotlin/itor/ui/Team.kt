package itor.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import itor.Model
import itor.TeamRow
import kotlinx.coroutines.delay

/** Manager view (demo): same numbers the employees see, ranked, plus tickets for IT. */
@Composable
fun Team(model: Model) {
    val team by model.team.collectAsState()
    val me by model.company.collectAsState()
    LaunchedEffect(Unit) { while (true) { model.loadTeam(); delay(5_000) } }
    val t = team
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card {
            Row2(left = { T("Team · today", 15, FontWeight.SemiBold) }, right = { M("ranked by active time", 11, colors.muted) })
            Row(Modifier.fillMaxWidth()) {
                M("#", 11, colors.muted, modifier = Modifier.width(20.dp))
                M("name", 11, colors.muted, modifier = Modifier.weight(1f))
                M("active", 11, colors.muted, modifier = Modifier.width(52.dp))
                M("lost", 11, colors.muted, modifier = Modifier.width(44.dp))
                M("to pay", 11, colors.muted, modifier = Modifier.width(52.dp))
            }
            Divider()
            if (t == null) M("loading", 12, colors.muted)
            val maxActive = t?.rows?.maxOfOrNull { it.activeSeconds }?.takeIf { it > 0 } ?: 1.0
            t?.rows?.forEachIndexed { index, row -> RankRow(row, index, maxActive, row.employee == me?.employee) }
        }
        Card {
            Row2(left = { T("Time lost to tools", 14, FontWeight.SemiBold) }, right = { M(duration(t?.totalLostSeconds), 12, colors.warn) })
            t?.lostByCause?.entries?.sortedByDescending { it.value }?.forEach { (cause, seconds) ->
                Row2(left = { T(causeLabels[cause] ?: cause, 13, color = colors.muted) }, right = { M(duration(seconds), 12) })
            }
            T("This is what IT should fix first.", 12, color = colors.muted)
        }
        Card {
            Row2(left = { T("Tickets for IT", 14, FontWeight.SemiBold) }, right = { M("${t?.tickets?.size ?: 0}", 12, colors.muted) })
            if (t?.tickets.isNullOrEmpty()) M("no tickets yet", 12, colors.muted)
            t?.tickets?.take(6)?.forEach { ticket ->
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row2(left = { T("${ticket.employee} · ${ticket.message}", 13) }, right = { M(localTime(ticket.createdAt), 12, colors.muted) })
                    M(listOfNotNull(ticket.diagnosis, ticket.connection.joinToString(", ").ifBlank { null }).joinToString(" · "), 11, colors.muted)
                }
                Divider()
            }
        }
    }
}

@Composable
private fun RankRow(row: TeamRow, index: Int, maxActive: Double, isMe: Boolean) {
    // The bar grows from 0 when the tab opens, one row after the other.
    val grow = remember(row.employee) { Animatable(0f) }
    LaunchedEffect(row.employee) {
        delay(40L * index)
        grow.animateTo(1f, tween(500, easing = FastOutSlowInEasing))
    }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            M("${row.rank}", 12, colors.muted, modifier = Modifier.width(20.dp))
            Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
                T(row.employee, 13, if (isMe) FontWeight.SemiBold else FontWeight.Normal, if (row.example) colors.muted else colors.text)
                if (isMe) { Spacer(Modifier.width(6.dp)); M("you", 11, colors.ok) }
            }
            M(duration(row.activeSeconds), 12, modifier = Modifier.width(52.dp))
            M(duration(row.lostSeconds), 12, if (row.lostSeconds > 1800) colors.warn else colors.text, modifier = Modifier.width(44.dp))
            M(duration(row.paidSecondsTotal), 12, modifier = Modifier.width(52.dp))
        }
        Box(Modifier.fillMaxWidth().height(3.dp).background(colors.border, SmallCorner)) {
            Box(Modifier.fillMaxWidth((row.activeSeconds / maxActive).toFloat() * grow.value).fillMaxHeight().background(colors.ok, SmallCorner))
        }
    }
}
