package com.doomsdaybot.samsungmvp.bot

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object RuleStore {
    private const val PREFS_NAME = "bot_rules"
    private const val RULES_KEY = "rules_json"

    fun loadRules(context: Context): List<BotRule> {
        val raw = context
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(RULES_KEY, null)

        if (raw.isNullOrBlank()) {
            return listOf(defaultRule())
        }

        return try {
            val array = JSONArray(raw)
            buildList {
                for (index in 0 until array.length()) {
                    val item = array.getJSONObject(index)
                    val target = item.optString("target").trim()
                    if (target.isBlank()) {
                        continue
                    }

                    add(
                        BotRule(
                            name = item.optString("name", target),
                            target = target,
                            targetField = parseField(item.optString("targetField")),
                            delayMs = item.optLong("delayMs", 700L).coerceAtLeast(0L),
                            enabled = item.optBoolean("enabled", true),
                        )
                    )
                }
            }
        } catch (_: Exception) {
            listOf(defaultRule())
        }
    }

    fun saveRules(context: Context, rules: List<BotRule>) {
        val array = JSONArray()
        rules.forEach { rule ->
            array.put(
                JSONObject()
                    .put("name", rule.name)
                    .put("target", rule.target)
                    .put("targetField", rule.targetField.name)
                    .put("delayMs", rule.delayMs)
                    .put("enabled", rule.enabled)
            )
        }

        context
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(RULES_KEY, array.toString())
            .apply()
    }

    private fun defaultRule(): BotRule = BotRule(
        name = "Tap OK",
        target = "OK",
        targetField = RuleTargetField.ANY,
        delayMs = 700L,
        enabled = true,
    )

    private fun parseField(value: String): RuleTargetField =
        RuleTargetField.entries.firstOrNull { it.name == value } ?: RuleTargetField.ANY
}
