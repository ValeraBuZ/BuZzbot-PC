package com.doomsdaybot.samsungmvp.vision

import android.graphics.Rect

data class VisualMatch(
    val name: String,
    val bounds: Rect,
    val confidence: Float,
)

interface VisualAnalyzer {
    fun findMatches(region: Rect? = null): List<VisualMatch>
}

class DisabledVisualAnalyzer : VisualAnalyzer {
    override fun findMatches(region: Rect?): List<VisualMatch> = emptyList()
}
