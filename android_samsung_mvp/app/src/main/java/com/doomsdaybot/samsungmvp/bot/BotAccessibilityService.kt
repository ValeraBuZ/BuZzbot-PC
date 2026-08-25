package com.doomsdaybot.samsungmvp.bot

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class BotAccessibilityService : AccessibilityService() {
    private var overlayController: FloatingOverlayController? = null

    override fun onServiceConnected() {
        instance = this
        showOverlay()
        BotEngine.setStatus("Accessibility service connected.")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit

    override fun onInterrupt() {
        BotEngine.setStatus("Accessibility service interrupted.")
    }

    override fun onDestroy() {
        overlayController?.destroy()
        overlayController = null
        if (instance === this) {
            instance = null
        }
        super.onDestroy()
    }

    fun activeRoot(): AccessibilityNodeInfo? = rootInActiveWindow

    fun showOverlay() {
        if (overlayController == null) {
            overlayController = FloatingOverlayController(this)
        }
        overlayController?.show()
    }

    fun hideOverlay() {
        overlayController?.hide()
    }

    fun tapCenter(bounds: Rect): Boolean {
        return tap(bounds.centerX().toFloat(), bounds.centerY().toFloat())
    }

    fun tap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, 80L))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    companion object {
        @Volatile
        var instance: BotAccessibilityService? = null
            private set
    }
}
