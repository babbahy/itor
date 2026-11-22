package itor.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.toComposeImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import itor.Model
import itor.PresenceFrame
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.Base64

/** MediaPipe pose connections drawn as the skeleton (head, shoulders, arms, torso). */
private val BONES = listOf(
    11 to 12, 11 to 13, 13 to 15, 12 to 14, 14 to 16, 11 to 23, 12 to 24, 23 to 24,
    0 to 1, 1 to 2, 2 to 3, 3 to 7, 0 to 4, 4 to 5, 5 to 6, 6 to 8, 9 to 10,
)

/** Camera tab: live webcam preview with the posture skeleton (like Birdy). Frames come from the local helper only. */
@Composable
fun Camera(model: Model) {
    var frame by remember { mutableStateOf<PresenceFrame?>(null) }
    var image by remember { mutableStateOf<ImageBitmap?>(null) }
    var calibrating by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    // Poll while the tab is open; the helper only produces preview frames while it is asked for them.
    LaunchedEffect(Unit) {
        while (true) {
            val next = model.presenceFrame()
            if (next != null) {
                frame = next
                next.jpegBase64?.let { encoded ->
                    image = runCatching {
                        org.jetbrains.skia.Image.makeFromEncoded(Base64.getDecoder().decode(encoded)).toComposeImageBitmap()
                    }.getOrNull() ?: image
                }
            }
            delay(150)
        }
    }

    val f = frame
    val posture = f?.posture
    val accent = when {
        posture == null || posture.label == "Unknown" -> colors.muted
        posture.ok -> colors.ok
        else -> colors.warn
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card {
            Row2(
                left = { T("Camera", 15, FontWeight.SemiBold) },
                right = {
                    Box(Modifier.size(6.dp).background(if (f?.state == "present") colors.ok else colors.warn, SmallCorner))
                    M(" ${f?.state ?: "starting"}", 11, colors.muted)
                },
            )
            Box(
                Modifier.fillMaxWidth().aspectRatio(4f / 3f).clip(SmallCorner).background(colors.bg).border(1.dp, colors.border, SmallCorner),
                contentAlignment = Alignment.Center,
            ) {
                val bitmap = image
                if (bitmap == null) {
                    Spinner()
                } else {
                    Image(bitmap, contentDescription = "Webcam preview", modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
                    Canvas(Modifier.fillMaxSize()) {
                        val points = f?.landmarks.orEmpty()
                        fun at(i: Int) = points.getOrNull(i)?.takeIf { it.v >= 0.5 }?.let { Offset(it.x.toFloat() * size.width, it.y.toFloat() * size.height) }
                        for ((a, b) in BONES) {
                            val pa = at(a) ?: continue
                            val pb = at(b) ?: continue
                            drawLine(accent, pa, pb, strokeWidth = 2f)
                        }
                        points.forEachIndexed { i, _ -> at(i)?.let { drawRect(accent, Offset(it.x - 2.5f, it.y - 2.5f), Size(5f, 5f)) } }
                        f?.face?.takeIf { it.size == 4 }?.let { (x, y, w, h) ->
                            drawRect(accent.copy(alpha = 0.7f), Offset(x.toFloat() * size.width, y.toFloat() * size.height),
                                Size(w.toFloat() * size.width, h.toFloat() * size.height), style = Stroke(1.5f))
                        }
                    }
                }
            }
            Row2(
                left = {
                    Box(Modifier.size(6.dp).background(accent, SmallCorner))
                    M("  posture: ${posture?.label?.lowercase() ?: "--"}", 12, accent)
                },
                right = { M(if (posture?.calibrated == true) "calibrated" else "not calibrated", 11, colors.muted) },
            )
            val nobody = f == null || f.state != "present"
            val down = !nobody && f?.lookingDown == true
            val lookColor = when { nobody -> colors.muted; down -> colors.warn; else -> colors.ok }
            Row2(
                left = {
                    Box(Modifier.size(6.dp).background(lookColor, SmallCorner))
                    M("  looking: ${when { nobody -> "nobody here"; down -> "away from screen"; else -> "at screen" }}", 12,
                        if (down) colors.warn else colors.muted)
                },
                right = {
                    fun n(v: Double?) = v?.let { String.format("%.2f", it) } ?: "--"
                    M("head ${n(f?.head)} · usual ${n(f?.usual)}", 11, colors.muted)
                },
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Btn("Calibrate", {
                    calibrating = true
                    scope.launch { model.calibratePosture(); calibrating = false }
                }, busy = calibrating, icon = "check")
                T("Sit up straight and look at the screen, then calibrate.", 12, color = colors.muted)
            }
        }
        T(
            "The image stays on this PC: it is shown here and dropped, never saved or sent. " +
                "The skeleton and posture come from MediaPipe, running locally.",
            12, color = colors.muted,
        )
    }
}
