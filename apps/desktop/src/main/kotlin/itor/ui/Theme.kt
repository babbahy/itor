package itor.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.platform.Font
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import itor.Tone

/** Monochrome base + one functional accent (emerald = OK, amber = warning). No gradients, no shadows. */
@Immutable
data class Palette(
    val bg: Color,
    val surface: Color,
    val border: Color,
    val text: Color,
    val muted: Color,
    val ok: Color,
    val warn: Color,
    val inverse: Color,
    val onInverse: Color,
)

val Light = Palette(
    bg = Color(0xFFF7F7F7), surface = Color(0xFFFFFFFF), border = Color(0xFFE2E2E2), text = Color(0xFF111111),
    muted = Color(0xFF6B6B6B), ok = Color(0xFF059669), warn = Color(0xFFB45309), inverse = Color(0xFF111111), onInverse = Color(0xFFF7F7F7),
)
val Dark = Palette(
    bg = Color(0xFF0E1013), surface = Color(0xFF14161A), border = Color(0xFF262A30), text = Color(0xFFF2F2F2),
    muted = Color(0xFF9CA0A6), ok = Color(0xFF34D399), warn = Color(0xFFFBBF24), inverse = Color(0xFFF2F2F2), onInverse = Color(0xFF0E1013),
)

/** Pixel landscape only: the red sun of the day scene. */
val SunRed = Color(0xFFD93829)

val LocalPalette = staticCompositionLocalOf { Light }
val colors: Palette @Composable get() = LocalPalette.current

val Inter = FontFamily(
    Font("fonts/Inter-Regular.ttf", FontWeight.Normal),
    Font("fonts/Inter-Medium.ttf", FontWeight.Medium),
    Font("fonts/Inter-SemiBold.ttf", FontWeight.SemiBold),
)
val Mono = FontFamily(
    Font("fonts/JetBrainsMono-Regular.ttf", FontWeight.Normal),
    Font("fonts/JetBrainsMono-Medium.ttf", FontWeight.Medium),
)

val Corner = RoundedCornerShape(6.dp)
val SmallCorner = RoundedCornerShape(4.dp)

@Composable
fun ItorTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val palette = if (dark) Dark else Light
    val scheme = (if (palette == Dark) darkColorScheme() else lightColorScheme()).copy(
        background = palette.bg, surface = palette.surface, onSurface = palette.text, onBackground = palette.text,
        primary = palette.inverse, onPrimary = palette.onInverse, outline = palette.border,
    )
    CompositionLocalProvider(LocalPalette provides palette, LocalContentColor provides palette.text) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}

fun Tone.color(p: Palette) = when (this) { Tone.OK -> p.ok; Tone.WARN -> p.warn; Tone.NEUTRAL -> p.muted }

// Text

@Composable
fun T(text: String, size: Int = 14, weight: FontWeight = FontWeight.Normal, color: Color = colors.text, modifier: Modifier = Modifier) =
    Text(text, modifier, color = color, style = TextStyle(fontFamily = Inter, fontSize = size.sp, fontWeight = weight, lineHeight = (size * 1.45).sp))

/** Monospace with tabular figures: times, durations, logs, codes, commands. */
@Composable
fun M(text: String, size: Int = 13, color: Color = colors.text, weight: FontWeight = FontWeight.Normal, modifier: Modifier = Modifier) =
    Text(text, modifier, color = color,
        style = TextStyle(fontFamily = Mono, fontSize = size.sp, fontWeight = weight, fontFeatureSettings = "tnum", lineHeight = (size * 1.5).sp))

@Composable
fun Label(text: String) = M(text.uppercase(), size = 11, color = colors.muted)

// Icons (Lucide, 1.5 px stroke)

@Composable
fun Ico(name: String, size: Int = 16, tint: Color = LocalContentColor.current) =
    Icon(painterResource("icons/$name.svg"), contentDescription = null, tint = tint, modifier = Modifier.size(size.dp))

// Surfaces

@Composable
fun Card(modifier: Modifier = Modifier, borderColor: Color = colors.border, content: @Composable ColumnScope.() -> Unit) =
    Column(
        modifier.fillMaxWidth().background(colors.surface, Corner).border(BorderStroke(1.dp, borderColor), Corner).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        content = content,
    )

@Composable
fun Divider() = Box(Modifier.fillMaxWidth().height(1.dp).background(colors.border))

// Buttons: flat, 4 px radius, no elevation

@Composable
fun Btn(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    primary: Boolean = false,
    enabled: Boolean = true,
    icon: String? = null,
    busy: Boolean = false,
    big: Boolean = false,
) {
    val p = colors
    val bg = if (primary) p.inverse else p.surface
    val fg = if (primary) p.onInverse else p.text
    Row(
        modifier
            .height(if (big) 44.dp else 32.dp)
            .background(if (enabled) bg else bg.copy(alpha = 0.5f), SmallCorner)
            .border(1.dp, if (primary) p.inverse else p.border, SmallCorner)
            .clickable(enabled = enabled && !busy, onClick = onClick)
            .padding(horizontal = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (busy) Spinner(fg) else if (icon != null) Ico(icon, if (big) 18 else 15, fg)
        T(text, if (big) 15 else 13, FontWeight.Medium, if (enabled) fg else fg.copy(alpha = 0.6f))
    }
}

@Composable
fun LinkText(text: String, onClick: () -> Unit) =
    Text(text, Modifier.clickable(onClick = onClick), color = colors.muted,
        style = TextStyle(fontFamily = Inter, fontSize = 13.sp, fontWeight = FontWeight.Medium))

@Composable
fun Spinner(color: Color = colors.muted) = CircularProgressIndicator(Modifier.size(14.dp), color = color, strokeWidth = 1.5.dp)

@Composable
fun Field(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    secret: Boolean = false,
    lines: Int = 1,
    onDone: (() -> Unit)? = null,
) {
    val p = colors
    Box(
        modifier.fillMaxWidth().background(p.bg, SmallCorner).border(1.dp, p.border, SmallCorner)
            .padding(PaddingValues(horizontal = 10.dp, vertical = 8.dp)),
    ) {
        if (value.isEmpty()) T(placeholder, 13, color = p.muted)
        BasicTextField(
            value, onChange,
            singleLine = lines == 1, minLines = lines,
            textStyle = TextStyle(fontFamily = Inter, fontSize = 13.sp, color = p.text),
            cursorBrush = SolidColor(p.text),
            visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(imeAction = if (onDone != null) ImeAction.Done else ImeAction.Default),
            keyboardActions = KeyboardActions(onDone = { onDone?.invoke() }),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
fun Row2(left: @Composable RowScope.() -> Unit, right: @Composable RowScope.() -> Unit) =
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, content = left)
        Row(verticalAlignment = Alignment.CenterVertically, content = right)
    }

fun duration(seconds: Double?): String {
    if (seconds == null) return "--"
    val minutes = Math.round(seconds / 60).toInt()
    return if (minutes < 60) "${minutes}m" else "${minutes / 60}h${(minutes % 60).toString().padStart(2, '0')}"
}

val causeLabels = mapOf(
    "blocked" to "Said I'm blocked",
    "offline" to "Internet or cloud down",
    "pc_overloaded" to "PC overloaded",
    "frozen_app" to "App not responding",
)
