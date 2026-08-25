package com.doomsdaybot.samsungmvp.scenario

import com.doomsdaybot.samsungmvp.vision.VisualTemplateInfo
import java.util.concurrent.ConcurrentHashMap

class ScenarioRuntime {
    private val completedSteps = ConcurrentHashMap<String, MutableSet<String>>()

    fun reset() {
        completedSteps.clear()
    }

    fun isReady(template: VisualTemplateInfo, settings: BotFeatureSettings): Boolean {
        val feature = template.feature ?: return false
        if (feature !in settings.enabledFeatures) {
            return false
        }
        if (
            template.requiredPrizeRepeat != null &&
            template.requiredPrizeRepeat != settings.repeatPrizeHunt
        ) {
            return false
        }

        val completed = completedSteps[feature.id].orEmpty()
        if (
            template.stepId.isNotBlank() &&
            template.stepId in completed &&
            !template.repeatStep
        ) {
            return false
        }
        if (template.requiredSteps.isEmpty()) {
            return true
        }
        if (completed.isEmpty() && template.allowRuntimeResume) {
            return true
        }
        return when (template.requirementMode) {
            StepRequirementMode.ALL -> template.requiredSteps.all(completed::contains)
            StepRequirementMode.ANY -> template.requiredSteps.any(completed::contains)
        }
    }

    fun recordTap(template: VisualTemplateInfo) {
        val feature = template.feature ?: return
        if (template.stepId.isBlank()) {
            return
        }
        completedSteps
            .getOrPut(feature.id) { ConcurrentHashMap.newKeySet() }
            .add(template.stepId)
    }

    fun completedFor(feature: BotFeature): Set<String> =
        completedSteps[feature.id]?.toSet().orEmpty()
}
