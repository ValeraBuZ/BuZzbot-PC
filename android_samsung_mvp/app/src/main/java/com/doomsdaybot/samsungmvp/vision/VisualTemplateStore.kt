package com.doomsdaybot.samsungmvp.vision

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import com.doomsdaybot.samsungmvp.scenario.BotFeature
import com.doomsdaybot.samsungmvp.scenario.StepRequirementMode
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

data class VisualTemplateInfo(
    val id: String,
    val name: String,
    val file: File,
    val delayMs: Long = 700L,
    val enabled: Boolean = true,
    val group: String = VisualTemplateStore.DEFAULT_GROUP,
    val featureId: String = "",
    val action: String = "click",
    val stepId: String = "",
    val priority: Int = 100,
    val threshold: Float = 0.88f,
    val requiredSteps: Set<String> = emptySet(),
    val requirementMode: StepRequirementMode = StepRequirementMode.ALL,
    val repeatStep: Boolean = false,
    val allowRuntimeResume: Boolean = false,
    val requiredPrizeRepeat: Boolean? = null,
    val clickOffsetX: Int = 0,
    val clickOffsetY: Int = 0,
    val referenceWidth: Int = 0,
    val referenceHeight: Int = 0,
    val builtIn: Boolean = false,
) {
    val feature: BotFeature?
        get() = BotFeature.fromId(featureId) ?: BotFeature.fromGroup(group)
}

data class VisualTemplateGroup(
    val name: String,
    val enabled: Boolean = true,
)

object VisualTemplateStore {
    const val DEFAULT_GROUP = "Основная"

    private const val VISUAL_DIR = "visual"
    private const val SAMPLE_NAME = "latest_visual.png"
    private const val TEMPLATE_DIR = "visual_templates"
    private const val TEMPLATE_NAME = "latest_template.png"
    private const val METADATA_NAME = "templates.json"
    private const val DEFAULT_DELAY_MS = 700L

    fun latestSampleFile(context: Context): File =
        File(File(context.cacheDir, VISUAL_DIR), SAMPLE_NAME)

    fun latestTemplateFile(context: Context): File {
        return listTemplates(context).lastOrNull()?.file
            ?: File(templateDirectory(context), TEMPLATE_NAME)
    }

    fun loadLatestSample(context: Context): Bitmap? {
        val file = latestSampleFile(context)
        if (!file.exists()) {
            return null
        }
        return BitmapFactory.decodeFile(file.absolutePath)
    }

    fun listTemplates(context: Context): List<VisualTemplateInfo> {
        val stored = readStoredData(context)
        return stored.templates
    }

    fun listEnabledTemplates(
        context: Context,
        enabledFeatures: Set<BotFeature>? = null,
    ): List<VisualTemplateInfo> {
        val stored = readStoredData(context)
        val enabledGroups = stored.groups
            .filter { group -> group.enabled }
            .map { group -> group.name }
            .toSet()
        return stored.templates.filter { template ->
            template.enabled &&
                cleanGroup(template.group) in enabledGroups &&
                (enabledFeatures == null || template.feature in enabledFeatures)
        }.sortedWith(compareBy(VisualTemplateInfo::priority, VisualTemplateInfo::name))
    }

    fun listGroups(context: Context): List<VisualTemplateGroup> {
        return readStoredData(context).groups
    }

    fun loadTemplate(template: VisualTemplateInfo): Bitmap? {
        if (!template.file.exists()) {
            return null
        }
        return BitmapFactory.decodeFile(template.file.absolutePath)
    }

    fun loadLatestTemplate(context: Context): Bitmap? {
        val template = listTemplates(context).lastOrNull() ?: return null
        return loadTemplate(template)
    }

    fun saveNewTemplate(context: Context, bitmap: Bitmap): VisualTemplateInfo {
        val directory = templateDirectory(context)
        directory.mkdirs()

        val stored = readStoredData(context)
        val id = UUID.randomUUID().toString()
        val file = File(directory, "template_${System.currentTimeMillis()}_${id.take(8)}.png")
        file.outputStream().use { stream ->
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
        }

        val info = VisualTemplateInfo(
            id = id,
            name = nextTemplateName(stored.templates),
            file = file,
            delayMs = DEFAULT_DELAY_MS,
            enabled = true,
            group = stored.groups.firstOrNull()?.name ?: DEFAULT_GROUP,
        )
        saveStoredData(context, stored.templates + info, stored.groups)
        return info
    }

    fun saveLatestTemplate(context: Context, bitmap: Bitmap): File =
        saveNewTemplate(context, bitmap).file

    fun clearTemplates(context: Context): Int {
        val directory = templateDirectory(context)
        val files = directory
            .listFiles { file -> file.isFile && file.extension.equals("png", ignoreCase = true) }
            .orEmpty()

        var deleted = 0
        files.forEach { file ->
            if (file.delete()) {
                deleted += 1
            }
        }
        metadataFile(context).delete()
        return deleted
    }

    fun saveTemplates(context: Context, templates: List<VisualTemplateInfo>) {
        val stored = readStoredData(context)
        saveStoredData(context, templates, stored.groups)
    }

    fun saveGroups(context: Context, groups: List<VisualTemplateGroup>) {
        val stored = readStoredData(context)
        saveStoredData(context, stored.templates, groups)
    }

    fun deleteTemplate(context: Context, templateId: String): Boolean {
        val stored = readStoredData(context)
        val template = stored.templates.firstOrNull { item -> item.id == templateId } ?: return false
        val deleted = !template.file.exists() || template.file.delete()
        if (deleted) {
            saveStoredData(context, stored.templates.filterNot { item -> item.id == templateId }, stored.groups)
        }
        return deleted
    }

    private fun templateDirectory(context: Context): File =
        File(context.filesDir, TEMPLATE_DIR)

    private fun metadataFile(context: Context): File =
        File(templateDirectory(context), METADATA_NAME)

    private fun readStoredData(context: Context): StoredTemplateData {
        val directory = templateDirectory(context)
        directory.mkdirs()
        val metadataTemplates = readMetadataFile(context, directory)
        val knownFiles = metadataTemplates.templates.map { template -> template.file.name }.toMutableSet()
        val orphanTemplates = directory
            .listFiles { file -> file.isFile && file.extension.equals("png", ignoreCase = true) }
            .orEmpty()
            .filter { file -> file.name !in knownFiles }
            .sortedBy { file -> file.lastModified() }
            .mapIndexed { index, file ->
                VisualTemplateInfo(
                    id = file.nameWithoutExtension,
                    name = "Шаблон ${metadataTemplates.templates.size + index + 1}",
                    file = file,
                    delayMs = DEFAULT_DELAY_MS,
                    enabled = true,
                    group = DEFAULT_GROUP,
                )
            }

        val templates = (metadataTemplates.templates + orphanTemplates)
            .filter { template -> template.file.exists() }
            .map { template -> template.copy(group = cleanGroup(template.group)) }
        val groups = mergeGroups(metadataTemplates.groups, templates)
        val stored = StoredTemplateData(templates, groups)

        if (orphanTemplates.isNotEmpty()) {
            saveStoredData(context, stored.templates, stored.groups)
        }
        return stored
    }

    private fun readMetadataFile(context: Context, directory: File): StoredTemplateData {
        val file = metadataFile(context)
        if (!file.exists()) {
            return StoredTemplateData(emptyList(), listOf(VisualTemplateGroup(DEFAULT_GROUP, true)))
        }

        return try {
            val text = file.readText()
            val trimmed = text.trimStart()
            if (trimmed.startsWith("[")) {
                val templates = parseTemplatesArray(JSONArray(text), directory)
                StoredTemplateData(templates, mergeGroups(emptyList(), templates))
            } else {
                val root = JSONObject(text)
                val templates = parseTemplatesArray(root.optJSONArray("templates") ?: JSONArray(), directory)
                val groups = parseGroupsArray(root.optJSONArray("groups") ?: JSONArray())
                StoredTemplateData(templates, mergeGroups(groups, templates))
            }
        } catch (_: Exception) {
            StoredTemplateData(emptyList(), listOf(VisualTemplateGroup(DEFAULT_GROUP, true)))
        }
    }

    private fun parseTemplatesArray(array: JSONArray, directory: File): List<VisualTemplateInfo> {
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                val fileName = item.optString("fileName")
                if (fileName.isBlank()) {
                    continue
                }
                add(
                    VisualTemplateInfo(
                        id = item.optString("id", fileName),
                        name = item.optString("name", "Шаблон ${index + 1}"),
                        file = File(directory, fileName),
                        delayMs = item.optLong("delayMs", DEFAULT_DELAY_MS).coerceAtLeast(100L),
                        enabled = item.optBoolean("enabled", true),
                        group = cleanGroup(item.optString("group", DEFAULT_GROUP)),
                        featureId = item.optString("featureId", ""),
                        action = item.optString("action", "click"),
                        stepId = item.optString("stepId", ""),
                        priority = item.optInt("priority", 100),
                        threshold = item.optDouble("threshold", 0.88).toFloat().coerceIn(0.1f, 1f),
                        requiredSteps = item.optJSONArray("requiredSteps").toStringSet(),
                        requirementMode = runCatching {
                            StepRequirementMode.valueOf(item.optString("requirementMode", "ALL"))
                        }.getOrDefault(StepRequirementMode.ALL),
                        repeatStep = item.optBoolean("repeatStep", false),
                        allowRuntimeResume = item.optBoolean("allowRuntimeResume", false),
                        requiredPrizeRepeat = if (item.has("requiredPrizeRepeat")) {
                            item.optBoolean("requiredPrizeRepeat")
                        } else {
                            null
                        },
                        clickOffsetX = item.optInt("clickOffsetX", 0),
                        clickOffsetY = item.optInt("clickOffsetY", 0),
                        referenceWidth = item.optInt("referenceWidth", 0).coerceAtLeast(0),
                        referenceHeight = item.optInt("referenceHeight", 0).coerceAtLeast(0),
                        builtIn = item.optBoolean("builtIn", false),
                    )
                )
            }
        }
    }

    private fun parseGroupsArray(array: JSONArray): List<VisualTemplateGroup> {
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                val name = cleanGroup(item.optString("name", DEFAULT_GROUP))
                if (none { group -> group.name == name }) {
                    add(VisualTemplateGroup(name, item.optBoolean("enabled", true)))
                }
            }
        }
    }

    private fun saveStoredData(
        context: Context,
        templates: List<VisualTemplateInfo>,
        groups: List<VisualTemplateGroup>,
    ) {
        val normalizedTemplates = templates
            .filter { template -> template.file.exists() }
            .map { template -> template.copy(group = cleanGroup(template.group)) }
        val normalizedGroups = mergeGroups(groups, normalizedTemplates)

        val root = JSONObject()
        root.put(
            "groups",
            JSONArray().apply {
                normalizedGroups.forEach { group ->
                    put(
                        JSONObject()
                            .put("name", group.name)
                            .put("enabled", group.enabled)
                    )
                }
            }
        )
        root.put(
            "templates",
            JSONArray().apply {
                normalizedTemplates.forEach { template ->
                    put(
                        JSONObject()
                            .put("id", template.id)
                            .put("name", template.name)
                            .put("fileName", template.file.name)
                            .put("delayMs", template.delayMs)
                            .put("enabled", template.enabled)
                            .put("group", cleanGroup(template.group))
                            .put("featureId", template.featureId)
                            .put("action", template.action)
                            .put("stepId", template.stepId)
                            .put("priority", template.priority)
                            .put("threshold", template.threshold.toDouble())
                            .put("requiredSteps", JSONArray(template.requiredSteps.toList()))
                            .put("requirementMode", template.requirementMode.name)
                            .put("repeatStep", template.repeatStep)
                            .put("allowRuntimeResume", template.allowRuntimeResume)
                            .put("clickOffsetX", template.clickOffsetX)
                            .put("clickOffsetY", template.clickOffsetY)
                            .put("referenceWidth", template.referenceWidth)
                            .put("referenceHeight", template.referenceHeight)
                            .put("builtIn", template.builtIn)
                            .apply {
                                template.requiredPrizeRepeat?.let { requiredValue ->
                                    put("requiredPrizeRepeat", requiredValue)
                                }
                            }
                    )
                }
            }
        )

        val file = metadataFile(context)
        file.parentFile?.mkdirs()
        file.writeText(root.toString(2))
    }

    private fun mergeGroups(
        existingGroups: List<VisualTemplateGroup>,
        templates: List<VisualTemplateInfo>,
    ): List<VisualTemplateGroup> {
        val byName = linkedMapOf<String, VisualTemplateGroup>()
        existingGroups.forEach { group ->
            val name = cleanGroup(group.name)
            byName[name] = group.copy(name = name)
        }
        templates.forEach { template ->
            val name = cleanGroup(template.group)
            if (name !in byName) {
                byName[name] = VisualTemplateGroup(name, true)
            }
        }
        if (byName.isEmpty()) {
            byName[DEFAULT_GROUP] = VisualTemplateGroup(DEFAULT_GROUP, true)
        }
        return byName.values.toList()
    }

    private fun nextTemplateName(existing: List<VisualTemplateInfo>): String {
        val used = existing.map { template -> template.name }.toSet()
        var index = existing.size + 1
        while ("Шаблон $index" in used) {
            index += 1
        }
        return "Шаблон $index"
    }

    private fun cleanGroup(value: String?): String {
        val group = value?.trim().orEmpty()
        return group.ifBlank { DEFAULT_GROUP }
    }

    private data class StoredTemplateData(
        val templates: List<VisualTemplateInfo>,
        val groups: List<VisualTemplateGroup>,
    )

    private fun JSONArray?.toStringSet(): Set<String> {
        if (this == null) {
            return emptySet()
        }
        return buildSet {
            for (index in 0 until length()) {
                optString(index).trim().takeIf(String::isNotEmpty)?.let(::add)
            }
        }
    }
}
