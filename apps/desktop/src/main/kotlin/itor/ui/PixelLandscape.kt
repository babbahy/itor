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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.random.Random

/** What the landscape shows. Always driven by real state (PC status, a check or a fix running). */
enum class Mood { CALM, WARN, OFFLINE, WORKING }

// Low-resolution 1-bit canvas, scaled up: crisp retro pixels.
private const val COLS = 160
private const val ROWS = 50
private const val HORIZON = 31

/** 4x4 ordered (Bayer) dither: a pixel is lit when its threshold is below the wanted density. */
private val BAYER = intArrayOf(0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)
private fun dither(x: Int, y: Int, density: Float) = BAYER[(y and 3) * 4 + (x and 3)] < density * 16f

/** Scattered (non-grid) pixels for sparse textures: a fixed hash per pixel, so they don't flicker. */
private fun speck(x: Int, y: Int, density: Float): Boolean {
    var h = x * 374761393 + y * 668265263
    h = (h xor (h ushr 13)) * 1274126177
    return ((h xor (h ushr 16)) and 0xFFFF) / 65536f < density
}

private class Scene(val mountain: Array<BooleanArray>, val ridge: IntArray)

/** Mountains are fixed (seeded) so the composition is always the same. */
private fun buildScene(night: Boolean): Scene {
    val peaks = listOf(18 to 10, 31 to 14, 54 to 16, 72 to 21, 95 to 15, 118 to 19, 142 to 13, 152 to 18)
    val random = Random(11)
    val ridge = IntArray(COLS) { x ->
        val top = peaks.minOf { (px, py) -> py + abs(x - px) * (0.55f + (px % 7) * 0.05f) }
        (top + random.nextInt(0, 2)).toInt().coerceIn(6, HORIZON)
    }
    val mountain = Array(ROWS) { BooleanArray(COLS) }
    for (x in 0 until COLS) for (y in ridge[x] until HORIZON) {
        val depth = (y - ridge[x]).toFloat() / max(1, HORIZON - ridge[x])
        mountain[y][x] = if (night) {
            // night: fine white ridge line, faint texture just below it
            y - ridge[x] <= 0 || (y - ridge[x] == 1 && speck(x, y, 0.45f)) || speck(x, y, 0.035f * (1 - depth))
        } else {
            // day: dense black near the ridge, lighter toward the horizon haze
            dither(x, y, 0.95f - 0.6f * depth)
        }
    }
    return Scene(mountain, ridge)
}

@Composable
fun PixelLandscape(mood: Mood, modifier: Modifier = Modifier) {
    val night = colors.bg == Dark.bg
    val scene = remember(night) { buildScene(night) }
    val stars = remember { Random(5).let { r -> List(46) { r.nextInt(COLS) to r.nextInt(2, HORIZON - 12) } } }
    val currentMood by rememberUpdatedState(mood)
    var frame by remember { mutableIntStateOf(0) }
    // Retro low frame rate: ~10 fps normally, faster ripples when something is wrong.
    LaunchedEffect(Unit) {
        while (true) {
            delay(if (currentMood == Mood.CALM) 100 else 70)
            frame++
        }
    }

    val ink = if (night) Color(0xFFF2F2F2) else Color(0xFF111111)
    val bg = if (night) Color(0xFF0E1013) else Color(0xFFF7F7F7)
    val trouble = mood == Mood.WARN || mood == Mood.OFFLINE
    val tint = if (trouble) colors.warn else ink
    // Sun (day, right) or moon (night, left): fixed anchors.
    val orbX = if (night) 36 else 118
    val orbY = if (night) 9 else 10
    val orbR = if (night) 4.5f else 5f

    Box(modifier.fillMaxWidth().height(150.dp)) {
        Canvas(Modifier.fillMaxSize()) {
            drawRect(bg)
            val px = size.width / COLS
            val py = size.height / ROWS
            val dot = Size(px * 0.92f, py * 0.92f)
            fun put(x: Int, y: Int, color: Color) {
                if (x in 0 until COLS && y in 0 until ROWS) drawRect(color, Offset(x * px, y * py), dot)
            }
            val f = frame

            // Sky: night stars (a few twinkle and drift), day haze near the horizon.
            if (night) {
                stars.forEachIndexed { i, (sx, sy) ->
                    val drift = if (i % 9 == 0) (f / 18 + i) % COLS else sx
                    if ((f + i * 7) % 37 != 0) put(drift, sy, ink.copy(alpha = if (i % 4 == 0) 0.9f else 0.45f))
                }
            } else {
                for (y in HORIZON - 6 until HORIZON) for (x in 0 until COLS) if (dither(x + f / 40, y, 0.06f)) put(x, y, ink.copy(alpha = 0.35f))
            }

            // Sun / moon with a slow dithered halo pulse.
            val pulse = 0.5f + 0.5f * sin(f * 0.15f)
            for (y in 0 until HORIZON) for (x in 0 until COLS) {
                val d = sqrt(((x - orbX) * (x - orbX) * 0.85f + (y - orbY) * (y - orbY)).toFloat())
                when {
                    d <= orbR -> put(x, y, if (night) ink else SunRed)
                    night && d <= orbR + 4 && dither(x, y, (0.55f - (d - orbR) * 0.12f) * (0.75f + 0.25f * pulse)) -> put(x, y, ink.copy(alpha = 0.8f))
                    !night && d <= orbR + 2.5f && dither(x, y, 0.18f * pulse) -> put(x, y, SunRed.copy(alpha = 0.6f))
                }
            }

            // Mountains (anchored).
            for (y in 0 until HORIZON) for (x in 0 until COLS) if (scene.mountain[y][x]) put(x, y, ink)

            // Horizon line: tinted amber/red near the edges when there is a problem.
            for (x in 0 until COLS) {
                val lit = if (night) speck(x, HORIZON, 0.35f) else x % 3 != 2
                if (lit) put(x, HORIZON, if (trouble && (x < 40 || x > COLS - 40)) lerp(ink, tint, 0.8f) else ink)
            }

            // Water: mirrored mountains, broken into rows that shimmer sideways.
            val speed = if (trouble) 0.9f else 0.45f
            for (y in HORIZON + 1 until ROWS) {
                val row = y - HORIZON
                if (row % 2 == 0) continue // gaps between ripple rows
                val mirror = HORIZON - row
                val shift = (sin(f * speed * 0.5f + row * 1.7f) * (1 + row / 8)).toInt()
                for (x in 0 until COLS) {
                    val sx = (x + shift).coerceIn(0, COLS - 1)
                    val reflected = mirror in 0 until HORIZON && scene.mountain[mirror][sx]
                    val fade = 1f - row.toFloat() / (ROWS - HORIZON)
                    val density = if (night) 0.32f * fade else 0.55f * fade
                    if (reflected && speck(x, y, density)) put(x, y, ink.copy(alpha = if (night) 0.6f else 0.75f))
                    else if (night && speck(x + f / 3, y, 0.012f)) put(x, y, ink.copy(alpha = 0.35f)) // sparse ripples
                }
                // Orb reflection: short dashes under the sun/moon that shimmer.
                val half = (6 - row / 3).coerceAtLeast(1)
                val wobble = (sin(f * 0.6f + row) * 2).toInt()
                for (dx in -half..half) {
                    if ((dx + row + f / 2) % 4 == 0) continue
                    put(orbX + dx + wobble, y, if (night) ink.copy(alpha = 0.85f) else SunRed)
                }
            }
        }
        M(
            "state: ${mood.name.lowercase()}", 11, colors.muted,
            modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp),
        )
    }
}
