package com.doomsdaybot.samsungmvp.scenario

import android.content.Context

object BotFeatureStore {
    private const val PREFS_NAME = "bot_features"
    private const val KEY_ENABLED_FEATURES = "enabled_features"
    private const val KEY_REPEAT_PRIZE_HUNT = "repeat_prize_hunt"

    fun load(context: Context): BotFeatureSettings {
        val preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val defaultIds = BotFeature.entries.map { feature -> feature.id }.toSet()
        val storedIds = preferences.getStringSet(KEY_ENABLED_FEATURES, defaultIds) ?: defaultIds
        val enabled = storedIds.mapNotNull(BotFeature::fromId).toSet()
        return BotFeatureSettings(
            enabledFeatures = enabled,
            repeatPrizeHunt = preferences.getBoolean(KEY_REPEAT_PRIZE_HUNT, true),
        )
    }

    fun save(context: Context, settings: BotFeatureSettings) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putStringSet(
                KEY_ENABLED_FEATURES,
                settings.enabledFeatures.map { feature -> feature.id }.toSet(),
            )
            .putBoolean(KEY_REPEAT_PRIZE_HUNT, settings.repeatPrizeHunt)
            .apply()
    }
}
