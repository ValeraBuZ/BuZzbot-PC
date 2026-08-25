package com.doomsdaybot.samsungmvp.bot

import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.doomsdaybot.samsungmvp.MainActivity
import com.doomsdaybot.samsungmvp.vision.ScreenCaptureService
import com.doomsdaybot.samsungmvp.vision.TemplateManagerActivity
import kotlin.math.abs

class FloatingOverlayController(
    private val service: BotAccessibilityService,
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val windowManager = service.getSystemService(WindowManager::class.java)
    private var overlayView: View? = null
    private var rootPanel: LinearLayout? = null
    private var statusView: TextView? = null
    private var removeStatusListener: (() -> Unit)? = null
    private var overlayMode = OverlayMode.COMPACT

    private val layoutParams = WindowManager.LayoutParams(
        WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
        PixelFormat.TRANSLUCENT,
    ).apply {
        gravity = Gravity.TOP or Gravity.START
        x = 24
        y = 220
    }

    fun show() {
        if (overlayView != null) {
            return
        }

        val view = buildView()
        overlayView = view
        windowManager.addView(view, layoutParams)
        removeStatusListener = BotEngine.addStatusListener { status ->
            mainHandler.post {
                statusView?.text = status.take(220)
            }
        }
    }

    fun hide() {
        val view = overlayView ?: return
        removeStatusListener?.invoke()
        removeStatusListener = null
        statusView = null
        rootPanel = null
        overlayView = null
        windowManager.removeView(view)
    }

    fun destroy() {
        hide()
    }

    private fun buildView(): View {
        return LinearLayout(service).apply {
            orientation = LinearLayout.VERTICAL
            rootPanel = this
            renderOverlay(this)
        }
    }

    private fun renderOverlay(panel: LinearLayout) {
        panel.removeAllViews()
        statusView = null

        when (overlayMode) {
            OverlayMode.DOT -> renderDot(panel)
            OverlayMode.COMPACT -> renderCompact(panel)
            OverlayMode.EXPANDED -> renderExpanded(panel)
        }
    }

    private fun renderDot(panel: LinearLayout) {
        panel.setPadding(0, 0, 0, 0)
        panel.setBackgroundColor(Color.TRANSPARENT)
        panel.addView(
            TextView(service).apply {
                text = "D"
                gravity = Gravity.CENTER
                setTextColor(Color.WHITE)
                textSize = 18f
                background = ovalBackground(Color.argb(155, 12, 16, 24))
                setOnTouchListener(DragOrClickTouchListener { setMode(OverlayMode.COMPACT) })
                layoutParams = LinearLayout.LayoutParams(58, 58)
            }
        )
    }

    private fun renderCompact(panel: LinearLayout) {
        panel.setPadding(10, 10, 10, 10)
        panel.setBackgroundColor(Color.argb(145, 12, 16, 24))

        panel.addView(headerRow())
        panel.addView(statusBlock())
        val moreButtonText = if (overlayMode == OverlayMode.EXPANDED) "Меньше" else "Еще"
        panel.addView(buttonRow("Цикл", "Стоп", moreButtonText) { action ->
            when (action) {
                "Цикл" -> ScreenCaptureService.startVisualLoop()
                "Стоп" -> stopEverything()
                "Еще" -> setMode(OverlayMode.EXPANDED)
                "Меньше" -> setMode(OverlayMode.COMPACT)
            }
        })
    }

    private fun renderExpanded(panel: LinearLayout) {
        renderCompact(panel)
        panel.addView(buttonRow("Образец", "Шаблоны", "Найти") { action ->
            when (action) {
                "Образец" -> ScreenCaptureService.saveSample()
                "Шаблоны" -> openTemplateManager()
                "Найти" -> ScreenCaptureService.findTemplateOnce()
            }
        })
        panel.addView(buttonRow("Нажать", "Кадр", "Меню") { action ->
            when (action) {
                "Нажать" -> ScreenCaptureService.tapTemplateOnce()
                "Кадр" -> ScreenCaptureService.captureOnce()
                "Меню" -> openEditor()
            }
        })
        panel.addView(buttonRow("Пауза", "Дальше", "Скрыть") { action ->
            when (action) {
                "Пауза" -> BotEngine.pause()
                "Дальше" -> BotEngine.resume()
                "Скрыть" -> hide()
            }
        })
    }

    private fun headerRow(): LinearLayout {
        return LinearLayout(service).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(
                TextView(service).apply {
                    text = "Doomsday"
                    setTextColor(Color.WHITE)
                    textSize = 14f
                    setPadding(8, 4, 12, 6)
                    setOnTouchListener(DragTouchListener())
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                }
            )
            addView(
                Button(service).apply {
                    text = "o"
                    textSize = 11f
                    minHeight = 0
                    minWidth = 0
                    setPadding(8, 2, 8, 2)
                    setOnClickListener { setMode(OverlayMode.DOT) }
                }
            )
        }
    }

    private fun statusBlock(): TextView {
        return TextView(service).apply {
            text = BotEngine.status.take(220)
            setTextColor(Color.rgb(10, 20, 30))
            textSize = 13f
            setPadding(10, 8, 10, 8)
            maxWidth = 560
            minLines = 1
            maxLines = 3
            setBackgroundColor(Color.argb(185, 235, 248, 255))
            statusView = this
        }
    }

    private fun setMode(mode: OverlayMode) {
        overlayMode = mode
        val panel = rootPanel ?: return
        renderOverlay(panel)
        overlayView?.let { view ->
            windowManager.updateViewLayout(view, layoutParams)
        }
    }

    private fun stopEverything() {
        BotEngine.stop()
        ScreenCaptureService.stopVisualLoop()
    }

    private fun buttonRow(
        first: String,
        second: String,
        third: String,
        onClick: (String) -> Unit,
    ): LinearLayout {
        return LinearLayout(service).apply {
            orientation = LinearLayout.HORIZONTAL
            addOverlayButton(first, onClick)
            addOverlayButton(second, onClick)
            addOverlayButton(third, onClick)
        }
    }

    private fun LinearLayout.addOverlayButton(
        textValue: String,
        onClick: (String) -> Unit,
    ) {
        addView(
            Button(service).apply {
                text = textValue
                textSize = 11f
                minHeight = 0
                minWidth = 0
                setPadding(8, 4, 8, 4)
                setOnClickListener { onClick(textValue) }
            }
        )
    }

    private fun ovalBackground(color: Int): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(color)
            setStroke(2, Color.argb(155, 255, 255, 255))
        }
    }

    private fun openEditor() {
        val intent = Intent(service, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        }
        service.startActivity(intent)
    }

    private fun openTemplateManager() {
        val intent = Intent(service, TemplateManagerActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        }
        service.startActivity(intent)
    }

    private enum class OverlayMode {
        DOT,
        COMPACT,
        EXPANDED,
    }

    private inner class DragTouchListener : View.OnTouchListener {
        private var startX = 0
        private var startY = 0
        private var touchStartX = 0f
        private var touchStartY = 0f

        override fun onTouch(view: View, event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = layoutParams.x
                    startY = layoutParams.y
                    touchStartX = event.rawX
                    touchStartY = event.rawY
                    return true
                }

                MotionEvent.ACTION_MOVE -> {
                    moveOverlay(startX, startY, touchStartX, touchStartY, event)
                    return true
                }
            }
            return false
        }
    }

    private inner class DragOrClickTouchListener(
        private val onClick: () -> Unit,
    ) : View.OnTouchListener {
        private var startX = 0
        private var startY = 0
        private var touchStartX = 0f
        private var touchStartY = 0f
        private var moved = false

        override fun onTouch(view: View, event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = layoutParams.x
                    startY = layoutParams.y
                    touchStartX = event.rawX
                    touchStartY = event.rawY
                    moved = false
                    return true
                }

                MotionEvent.ACTION_MOVE -> {
                    if (abs(event.rawX - touchStartX) > 8 || abs(event.rawY - touchStartY) > 8) {
                        moved = true
                    }
                    moveOverlay(startX, startY, touchStartX, touchStartY, event)
                    return true
                }

                MotionEvent.ACTION_UP -> {
                    if (!moved) {
                        onClick()
                    }
                    return true
                }
            }
            return false
        }
    }

    private fun moveOverlay(
        startX: Int,
        startY: Int,
        touchStartX: Float,
        touchStartY: Float,
        event: MotionEvent,
    ) {
        layoutParams.x = startX + (event.rawX - touchStartX).toInt()
        layoutParams.y = startY + (event.rawY - touchStartY).toInt()
        overlayView?.let { currentView ->
            windowManager.updateViewLayout(currentView, layoutParams)
        }
    }
}
