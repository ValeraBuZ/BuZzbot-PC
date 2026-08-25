package com.doomsdaybot.samsungmvp.vision

import android.content.Context
import com.doomsdaybot.samsungmvp.scenario.BuiltInScenarioCatalog
import java.io.File

data class BuiltInTemplateInstallResult(
    val available: Int,
    val copied: Int,
    val failed: Int,
)

object BuiltInTemplateInstaller {
    private const val TEMPLATE_DIR = "visual_templates"

    fun install(context: Context): BuiltInTemplateInstallResult {
        val directory = File(context.filesDir, TEMPLATE_DIR).apply { mkdirs() }
        val storedTemplates = VisualTemplateStore.listTemplates(context)
        val existingBuiltIns = storedTemplates
            .filter(VisualTemplateInfo::builtIn)
            .associateBy(VisualTemplateInfo::id)
        val customTemplates = storedTemplates.filterNot(VisualTemplateInfo::builtIn)
        var copied = 0
        var failed = 0

        val builtIns = BuiltInScenarioCatalog.templates.mapNotNull { definition ->
            val file = File(directory, "builtin_${definition.templateId}.png")
            if (!file.exists()) {
                val installed = runCatching {
                    context.assets.open(definition.assetPath).use { input ->
                        file.outputStream().use(input::copyTo)
                    }
                }.isSuccess
                if (installed) {
                    copied += 1
                } else {
                    failed += 1
                    file.delete()
                    return@mapNotNull null
                }
            }

            val stableId = "builtin:${definition.templateId}"
            val previous = existingBuiltIns[stableId]
            VisualTemplateInfo(
                id = stableId,
                name = definition.name,
                file = file,
                delayMs = previous?.delayMs ?: definition.delayMs,
                enabled = previous?.enabled ?: true,
                group = definition.feature.templateGroup,
                featureId = definition.feature.id,
                action = definition.action,
                stepId = definition.stepId,
                priority = definition.priority,
                threshold = definition.threshold,
                requiredSteps = definition.requiredSteps,
                requirementMode = definition.requirementMode,
                repeatStep = definition.repeatStep,
                allowRuntimeResume = definition.allowRuntimeResume,
                requiredPrizeRepeat = definition.requiredPrizeRepeat,
                clickOffsetX = definition.clickOffsetX,
                clickOffsetY = definition.clickOffsetY,
                referenceWidth = definition.referenceWidth,
                referenceHeight = definition.referenceHeight,
                builtIn = true,
            )
        }

        VisualTemplateStore.saveTemplates(context, customTemplates + builtIns)
        return BuiltInTemplateInstallResult(
            available = builtIns.size,
            copied = copied,
            failed = failed,
        )
    }
}
