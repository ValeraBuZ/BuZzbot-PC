package com.doomsdaybot.samsungmvp.vision

import android.app.Activity
import android.graphics.Bitmap
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.doomsdaybot.samsungmvp.bot.BotEngine

class TemplateEditorActivity : Activity() {
    private var sourceBitmap: Bitmap? = null
    private var selectionView: TemplateSelectionView? = null
    private lateinit var statusView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val bitmap = VisualTemplateStore.loadLatestSample(this)
        if (bitmap == null) {
            showMessage("Нет сохранённого кадра. В игре нажми «Образец», потом открой редактор шаблона.")
            return
        }

        sourceBitmap = bitmap
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(12, 12, 12, 12)
        }

        statusView = TextView(this).apply {
            val count = VisualTemplateStore.listTemplates(this@TemplateEditorActivity).size
            text = "Кадр: ${bitmap.width}x${bitmap.height}. Шаблонов: $count. Выбери область и сохрани новый шаблон."
            textSize = 15f
            setPadding(0, 0, 0, 8)
        }

        selectionView = TemplateSelectionView(this, bitmap)

        val verticalScroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f,
            )
            isFillViewport = false
            addView(
                HorizontalScrollView(this@TemplateEditorActivity).apply {
                    addView(selectionView)
                }
            )
        }

        val zoomRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(zoomButton("-") { adjustZoom(0.75f) })
            addView(zoomButton("100%") { setZoom(1f) })
            addView(zoomButton("200%") { setZoom(2f) })
            addView(zoomButton("400%") { setZoom(4f) })
            addView(zoomButton("+") { adjustZoom(1.25f) })
        }

        val saveButton = Button(this).apply {
            text = "Сохранить новый шаблон"
            setOnClickListener { saveTemplate() }
        }

        val closeButton = Button(this).apply {
            text = "Закрыть"
            setOnClickListener { finish() }
        }

        container.addView(statusView)
        container.addView(zoomRow)
        container.addView(verticalScroll)
        container.addView(saveButton)
        container.addView(closeButton)
        setContentView(container)
    }

    override fun onDestroy() {
        sourceBitmap?.recycle()
        sourceBitmap = null
        super.onDestroy()
    }

    private fun saveTemplate() {
        val bitmap = sourceBitmap ?: return
        val selectedRect = selectionView?.selectedImageRect()
        if (selectedRect == null) {
            statusView.text = "Выделение слишком маленькое. Выдели кнопку, иконку или надпись."
            return
        }

        val cropped = Bitmap.createBitmap(
            bitmap,
            selectedRect.left,
            selectedRect.top,
            selectedRect.width(),
            selectedRect.height(),
        )
        val template = VisualTemplateStore.saveNewTemplate(this, cropped)
        val sizeKb = template.file.length() / 1024
        val count = VisualTemplateStore.listTemplates(this).size
        statusView.text = "${template.name} сохранён: ${cropped.width}x${cropped.height}, ${sizeKb} KB. Всего шаблонов: $count."
        BotEngine.setStatus("${template.name} сохранён: ${cropped.width}x${cropped.height}. Всего шаблонов: $count.")
        cropped.recycle()
    }

    private fun zoomButton(textValue: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = textValue
            textSize = 12f
            minWidth = 0
            minHeight = 0
            setPadding(8, 4, 8, 4)
            setOnClickListener { onClick() }
        }
    }

    private fun setZoom(scale: Float) {
        selectionView?.setImageScale(scale)
        statusView.text = "Масштаб: ${(scale * 100).toInt()}%. Прокрути кадр и выдели область."
    }

    private fun adjustZoom(multiplier: Float) {
        val view = selectionView ?: return
        setZoom(view.imageScale() * multiplier)
    }

    private fun showMessage(message: String) {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(32, 32, 32, 32)
        }
        container.addView(
            TextView(this).apply {
                text = message
                textSize = 18f
                gravity = Gravity.CENTER
            }
        )
        container.addView(
            Button(this).apply {
                text = "Закрыть"
                setOnClickListener { finish() }
            }
        )
        setContentView(container)
    }
}
