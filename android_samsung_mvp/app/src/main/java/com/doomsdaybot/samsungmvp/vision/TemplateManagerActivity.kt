package com.doomsdaybot.samsungmvp.vision

import android.app.Activity
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.doomsdaybot.samsungmvp.bot.BotEngine

class TemplateManagerActivity : Activity() {
    private lateinit var statusView: TextView
    private lateinit var groupsContainer: LinearLayout
    private lateinit var listContainer: LinearLayout
    private val rows = mutableListOf<TemplateRow>()
    private val groupRows = mutableListOf<GroupRow>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 32, 24, 24)
        }

        statusView = TextView(this).apply {
            textSize = 16f
            setPadding(0, 0, 0, 16)
        }

        val hintView = TextView(this).apply {
            text = "Группа включается одной галочкой. У шаблона можно написать группу вручную: например, Аккаунт 1, Бой, Сбор."
            textSize = 14f
            setPadding(0, 0, 0, 16)
        }

        val buttonRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }

        buttonRow.addView(
            Button(this).apply {
                text = "Новый"
                setOnClickListener {
                    startActivity(Intent(this@TemplateManagerActivity, TemplateEditorActivity::class.java))
                }
            }
        )
        buttonRow.addView(
            Button(this).apply {
                text = "Сохранить"
                setOnClickListener { saveFromRows(showStatus = true) }
            }
        )
        buttonRow.addView(
            Button(this).apply {
                text = "Закрыть"
                setOnClickListener { finish() }
            }
        )

        groupsContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        listContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        container.addView(statusView)
        container.addView(hintView)
        container.addView(buttonRow)
        container.addView(sectionTitle("Группы"))
        container.addView(groupsContainer)
        container.addView(sectionTitle("Шаблоны"))
        container.addView(listContainer)
        setContentView(ScrollView(this).apply { addView(container) })
        refreshList()
    }

    override fun onResume() {
        super.onResume()
        if (::listContainer.isInitialized) {
            refreshList()
        }
    }

    private fun refreshList() {
        rows.clear()
        groupRows.clear()
        groupsContainer.removeAllViews()
        listContainer.removeAllViews()

        val templates = VisualTemplateStore.listTemplates(this)
        val groups = VisualTemplateStore.listGroups(this)
        val enabledGroupNames = groups.filter { group -> group.enabled }.map { group -> group.name }.toSet()
        val enabledTemplates = templates.count { template ->
            template.enabled && template.group in enabledGroupNames
        }
        statusView.text = if (templates.isEmpty()) {
            "Шаблонов пока нет. Нажми «Новый», если уже сохранил образец кадра."
        } else {
            "Шаблонов: ${templates.size}, активно сейчас: $enabledTemplates"
        }

        groups.forEach { group ->
            groupsContainer.addView(groupRow(group, templates.count { template -> template.group == group.name }))
        }

        templates.forEachIndexed { index, template ->
            listContainer.addView(templateRow(index, template, templates.size))
        }
    }

    private fun groupRow(group: VisualTemplateGroup, templateCount: Int): LinearLayout {
        val enabledBox = CheckBox(this).apply {
            text = "${group.name} ($templateCount)"
            isChecked = group.enabled
            setOnClickListener {
                saveFromRows(showStatus = false)
                BotEngine.setStatus(
                    if (isChecked) "Группа включена: ${group.name}" else "Группа выключена: ${group.name}"
                )
            }
        }
        groupRows.add(GroupRow(group.name, enabledBox))
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(enabledBox)
        }
    }

    private fun templateRow(index: Int, template: VisualTemplateInfo, total: Int): LinearLayout {
        val enabledBox = CheckBox(this).apply {
            text = "Шаблон включён"
            isChecked = template.enabled
        }
        val nameInput = EditText(this).apply {
            setText(template.name)
            hint = "Название"
            setSingleLine(true)
        }
        val groupInput = EditText(this).apply {
            setText(template.group)
            hint = "Группа"
            setSingleLine(true)
        }
        val delayInput = EditText(this).apply {
            setText(template.delayMs.toString())
            hint = "Задержка после клика, мс"
            inputType = InputType.TYPE_CLASS_NUMBER
            setSingleLine(true)
        }

        rows.add(TemplateRow(template.id, enabledBox, nameInput, groupInput, delayInput))

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 18, 0, 18)
        }

        val preview = loadPreview(template)
        if (preview != null) {
            card.addView(
                ImageView(this).apply {
                    setImageBitmap(preview)
                    adjustViewBounds = true
                    maxWidth = 260
                    maxHeight = 140
                    scaleType = ImageView.ScaleType.FIT_START
                    setPadding(0, 0, 0, 8)
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                    )
                }
            )
        }

        card.addView(
            TextView(this).apply {
                val sizeKb = template.file.length() / 1024
                text = "${index + 1}. ${template.file.name} (${sizeKb} KB)"
                textSize = 13f
            }
        )
        card.addView(enabledBox)
        card.addView(nameInput)
        card.addView(groupInput)
        card.addView(delayInput)

        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        actionRow.addView(
            Button(this).apply {
                text = "Вверх"
                isEnabled = index > 0
                setOnClickListener { moveTemplate(index, index - 1) }
            }
        )
        actionRow.addView(
            Button(this).apply {
                text = "Вниз"
                isEnabled = index < total - 1
                setOnClickListener { moveTemplate(index, index + 1) }
            }
        )
        actionRow.addView(
            Button(this).apply {
                text = "Удалить"
                setOnClickListener {
                    saveFromRows(showStatus = false)
                    val deleted = VisualTemplateStore.deleteTemplate(this@TemplateManagerActivity, template.id)
                    BotEngine.setStatus(if (deleted) "Шаблон удалён." else "Не удалось удалить шаблон.")
                    refreshList()
                }
            }
        )
        card.addView(actionRow)
        return card
    }

    private fun moveTemplate(fromIndex: Int, toIndex: Int) {
        saveFromRows(showStatus = false)
        val templates = VisualTemplateStore.listTemplates(this).toMutableList()
        if (fromIndex !in templates.indices || toIndex !in templates.indices) {
            return
        }
        val item = templates.removeAt(fromIndex)
        templates.add(toIndex, item)
        VisualTemplateStore.saveTemplates(this, templates)
        refreshList()
    }

    private fun saveFromRows(showStatus: Boolean) {
        val current = VisualTemplateStore.listTemplates(this)
        val byId = current.associateBy { template -> template.id }
        val updatedTemplates = rows.mapNotNull { row ->
            val template = byId[row.id] ?: return@mapNotNull null
            template.copy(
                name = row.nameInput.text?.toString()?.trim()?.ifBlank { template.name } ?: template.name,
                group = row.groupInput.text?.toString()?.trim()?.ifBlank { VisualTemplateStore.DEFAULT_GROUP }
                    ?: VisualTemplateStore.DEFAULT_GROUP,
                delayMs = row.delayInput.text?.toString()?.toLongOrNull()?.coerceAtLeast(100L) ?: template.delayMs,
                enabled = row.enabledBox.isChecked,
            )
        }

        VisualTemplateStore.saveTemplates(this, updatedTemplates)
        VisualTemplateStore.saveGroups(this, collectGroups(updatedTemplates))

        if (showStatus) {
            BotEngine.setStatus("Настройки шаблонов и групп сохранены.")
            refreshList()
        }
    }

    private fun collectGroups(templates: List<VisualTemplateInfo>): List<VisualTemplateGroup> {
        val groups = linkedMapOf<String, VisualTemplateGroup>()
        groupRows.forEach { row ->
            groups[row.name] = VisualTemplateGroup(row.name, row.enabledBox.isChecked)
        }
        templates.forEach { template ->
            val name = template.group.trim().ifBlank { VisualTemplateStore.DEFAULT_GROUP }
            if (name !in groups) {
                groups[name] = VisualTemplateGroup(name, true)
            }
        }
        return groups.values.toList()
    }

    private fun sectionTitle(textValue: String): TextView {
        return TextView(this).apply {
            text = textValue
            textSize = 18f
            setPadding(0, 18, 0, 8)
        }
    }

    private fun loadPreview(template: VisualTemplateInfo) =
        try {
            val bounds = BitmapFactory.Options().apply {
                inJustDecodeBounds = true
            }
            BitmapFactory.decodeFile(template.file.absolutePath, bounds)

            val maxSize = 260
            var sampleSize = 1
            while (bounds.outWidth / sampleSize > maxSize || bounds.outHeight / sampleSize > maxSize) {
                sampleSize *= 2
            }

            BitmapFactory.decodeFile(
                template.file.absolutePath,
                BitmapFactory.Options().apply {
                    inSampleSize = sampleSize.coerceAtLeast(1)
                },
            )
        } catch (_: Exception) {
            null
        }

    private data class TemplateRow(
        val id: String,
        val enabledBox: CheckBox,
        val nameInput: EditText,
        val groupInput: EditText,
        val delayInput: EditText,
    )

    private data class GroupRow(
        val name: String,
        val enabledBox: CheckBox,
    )
}
