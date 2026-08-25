package com.doomsdaybot.samsungmvp.scenario

enum class BotFeature(
    val id: String,
    val label: String,
    val templateGroup: String,
) {
    HEAL("heal", "Лечение войск", "Лечение войск"),
    ZOMBIE_HUNT("zombie_hunt", "Убийство зомби", "Убийство зомби"),
    PRIZE_HUNT("prize_hunt", "Охота за призом", "Охота за призом");

    companion object {
        fun fromId(value: String?): BotFeature? = entries.firstOrNull { feature ->
            feature.id == value
        }

        fun fromGroup(value: String?): BotFeature? = entries.firstOrNull { feature ->
            feature.templateGroup == value
        }
    }
}

data class BotFeatureSettings(
    val enabledFeatures: Set<BotFeature> = BotFeature.entries.toSet(),
    val repeatPrizeHunt: Boolean = true,
)
