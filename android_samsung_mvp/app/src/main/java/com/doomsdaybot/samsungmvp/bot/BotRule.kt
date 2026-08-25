package com.doomsdaybot.samsungmvp.bot

enum class RuleTargetField {
    ANY,
    TEXT,
    CONTENT_DESCRIPTION,
    VIEW_ID,
}

data class BotRule(
    val name: String,
    val target: String,
    val targetField: RuleTargetField = RuleTargetField.ANY,
    val delayMs: Long = 700L,
    val enabled: Boolean = true,
)
