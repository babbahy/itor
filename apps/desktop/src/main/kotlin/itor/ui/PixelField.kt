package itor.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

/** What the pixel cloud shows. Always driven by real state (PC status, a check or a fix running). */
enum class Mood { CALM, WARN, OFFLINE, WORKING }

private class Dot(
    val clusterX: Float, val clusterY: Float, // home position (0..1), grouped in a few soft clusters
    val spreadX: Float, val spreadY: Float,   // scattered position used when offline (0..1)
    val radius: Float, val angle: Float,      // orbit when working
    val speed: Float, val phase: Float,
    val size: Float, val alpha: Float,
)

private fun makeDots(count: Int): List<Dot> {
    val random = Random(7) // fixed seed: the same cloud on every run
    val clusters = listOf(0.22f to 0.38f, 0.48f to 0.55f, 0.74f to 0.32f, 0.86f to 0.7f, 0.34f to 0.76f)
    return List(count) { index ->
        val (cx, cy) = clusters[index % clusters.size]
        val near = random.nextFloat() < 0.72f
        val spread = if (near) 0.07f else 0.32f
        Dot(
            clusterX = (cx + (random.nextFloat() - 0.5f) * spread * 2).coerceIn(0.02f, 0.98f),
            clusterY = (cy + (random.nextFloat() - 0.5f) * spread * 2.4f).coerceIn(0.05f, 0.95f),
            spreadX = random.nextFloat() * 0.96f + 0.02f,
            spreadY = random.nextFloat() * 0.9f + 0.05f,
            radius = 0.04f + random.nextFloat() * 0.28f,
            angle = random.nextFloat() * (2 * PI).toFloat(),
            speed = 0.25f + random.nextFloat() * 0.9f,
            phase = random.nextFloat() * 6.28f,
            size = if (random.nextFloat() < 0.12f) 2.6f else 1.8f,
            alpha = 0.45f + random.nextFloat() * 0.55f,
        )
    }
}

@Composable
fun PixelField(mood: Mood, modifier: Modifier = Modifier) {
    val dots = remember { makeDots(220) }
    var time by remember { mutableLongStateOf(0L) }
    val currentMood by rememberUpdatedState(mood)
    // Blend weights per mood, eased toward the current mood (~600 ms), so changes are smooth but quick.
    val weights = remember { FloatArray(4).also { it[0] = 1f } }
    LaunchedEffect(Unit) {
        var last = 0L
        while (true) {
            withFrameNanos { now ->
                val dt = if (last == 0L) 0f else ((now - last) / 1e9f).coerceAtMost(0.05f)
                last = now
                for (i in weights.indices) {
                    val target = if (i == currentMood.ordinal) 1f else 0f
                    weights[i] += (target - weights[i]) * min(1f, dt * 5f)
                }
                time = now
            }
        }
    }
    val p = colors
    val calmColor = p.text
    val warnColor = p.warn
    Box(modifier.fillMaxWidth().height(150.dp)) {
        Canvas(Modifier.fillMaxSize()) {
            val t = time / 1e9f
            val calm = weights[Mood.CALM.ordinal]
            val warn = weights[Mood.WARN.ordinal]
            val offline = weights[Mood.OFFLINE.ordinal]
            val working = weights[Mood.WORKING.ordinal]
            val color = lerp(calmColor, warnColor, (warn + offline).coerceIn(0f, 1f))
            val w = size.width
            val h = size.height
            for (dot in dots) {
                // calm / warn: slow drift around the cluster position
                val drift = 0.012f
                val jitter = if (warn > 0.01f) warn * 0.006f * sin(t * 9f + dot.phase * 3) else 0f
                val homeX = dot.clusterX + drift * sin(t * 0.35f * dot.speed + dot.phase) + jitter
                val homeY = dot.clusterY + drift * cos(t * 0.3f * dot.speed + dot.phase)
                // offline: scattered, drifting a bit more
                val outX = dot.spreadX + 0.02f * sin(t * 0.2f + dot.phase)
                val outY = dot.spreadY + 0.02f * cos(t * 0.25f + dot.phase)
                // working: pulled to the centre, slow orbit
                val a = dot.angle + t * 0.6f * dot.speed
                val inX = 0.5f + dot.radius * 0.55f * cos(a)
                val inY = 0.5f + dot.radius * sin(a)
                val x = (homeX * (calm + warn) + outX * offline + inX * working) * w
                val y = (homeY * (calm + warn) + outY * offline + inY * working) * h
                val alpha = dot.alpha * (1f - 0.45f * offline)
                drawRect(color.copy(alpha = alpha), topLeft = Offset(x, y), size = Size(dot.size, dot.size))
            }
        }
        M(
            "state: ${mood.name.lowercase()}", 11, colors.muted,
            modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp),
        )
    }
}
