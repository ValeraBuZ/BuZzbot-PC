package com.doomsdaybot.samsungmvp.vision

import android.content.Context

enum class VisualQuality(
    val label: String,
    val maxWidth: Int,
) {
    ECONOMY("Экономно 720", 720),
    BALANCED("Средне 1080", 1080),
    FULL("Полный размер", 0),
}

object VisualCaptureSettings {
    private const val PREFS_NAME = "visual_capture"
    private const val QUALITY_KEY = "quality"
    private const val FULL_DEFAULT_APPLIED_KEY = "full_default_applied"

    fun loadQuality(context: Context): VisualQuality {
        applyFullDefaultOnce(context)
        val value = context
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(QUALITY_KEY, VisualQuality.FULL.name)

        return VisualQuality.entries.firstOrNull { it.name == value } ?: VisualQuality.FULL
    }

    fun saveQuality(context: Context, quality: VisualQuality) {
        context
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(QUALITY_KEY, quality.name)
            .apply()
    }

    private fun applyFullDefaultOnce(context: Context) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (prefs.getBoolean(FULL_DEFAULT_APPLIED_KEY, false)) {
            return
        }

        prefs.edit()
            .putString(QUALITY_KEY, VisualQuality.FULL.name)
            .putBoolean(FULL_DEFAULT_APPLIED_KEY, true)
            .apply()
    }
}
