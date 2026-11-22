package itor

/** When focus reminders fire. Kept small and gentle: at most one phone reminder every 2 minutes. */
object FocusRules {
    const val PHONE_SECONDS = 5.0
    const val PHONE_COOLDOWN_MS = 2 * 60_000L
    const val PAUSE_MS = 10 * 60_000L
    const val PAUSE_COOLDOWN_MS = 30 * 60_000L
}
