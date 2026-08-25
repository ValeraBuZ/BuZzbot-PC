package com.doomsdaybot.samsungmvp.bot

import android.view.accessibility.AccessibilityNodeInfo

data class NodeSummary(
    val totalNodes: Int,
    val clickableNodes: Int,
    val readableNodes: Int,
)

data class RuleMatch(
    val rule: BotRule,
    val node: AccessibilityNodeInfo,
)

object UiNodeFinder {
    fun findFirst(
        root: AccessibilityNodeInfo,
        predicate: (AccessibilityNodeInfo) -> Boolean,
    ): AccessibilityNodeInfo? {
        if (predicate(root)) {
            return root
        }

        for (index in 0 until root.childCount) {
            val child = root.getChild(index) ?: continue
            val found = findFirst(child, predicate)
            if (found != null) {
                return found
            }
        }

        return null
    }

    fun findFirstMatchingRule(
        root: AccessibilityNodeInfo,
        rules: List<BotRule>,
    ): RuleMatch? {
        val activeRules = rules.filter { it.enabled && it.target.isNotBlank() }
        if (activeRules.isEmpty()) {
            return null
        }

        return findRuleMatch(root, activeRules)
    }

    fun summarize(root: AccessibilityNodeInfo): NodeSummary {
        var total = 1
        var clickable = if (root.isClickable) 1 else 0
        var readable = if (root.readableText().isNotBlank()) 1 else 0

        for (index in 0 until root.childCount) {
            val child = root.getChild(index) ?: continue
            val childSummary = summarize(child)
            total += childSummary.totalNodes
            clickable += childSummary.clickableNodes
            readable += childSummary.readableNodes
        }

        return NodeSummary(total, clickable, readable)
    }

    fun sampleReadableNodes(root: AccessibilityNodeInfo, limit: Int = 5): List<String> {
        val result = mutableListOf<String>()
        collectReadableNodes(root, result, limit)
        return result
    }

    private fun collectReadableNodes(
        node: AccessibilityNodeInfo,
        result: MutableList<String>,
        limit: Int,
    ) {
        if (result.size >= limit) {
            return
        }

        val value = node.readableText()
        if (value.isNotBlank()) {
            result.add(value)
        }

        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            collectReadableNodes(child, result, limit)
        }
    }

    private fun findRuleMatch(
        node: AccessibilityNodeInfo,
        activeRules: List<BotRule>,
    ): RuleMatch? {
        val matchedRule = activeRules.firstOrNull { rule -> node.matches(rule) }
        val clickableTarget = node.findClickableTarget()
        if (matchedRule != null && clickableTarget != null) {
            return RuleMatch(matchedRule, clickableTarget)
        }

        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            val childMatch = findRuleMatch(child, activeRules)
            if (childMatch != null) {
                return childMatch
            }
        }

        return null
    }

    private fun AccessibilityNodeInfo.matches(rule: BotRule): Boolean {
        val needle = rule.target.trim()
        if (needle.isBlank()) {
            return false
        }

        val textValue = text?.toString().orEmpty()
        val descriptionValue = contentDescription?.toString().orEmpty()
        val idValue = viewIdResourceName.orEmpty()

        return when (rule.targetField) {
            RuleTargetField.ANY ->
                textValue.contains(needle, ignoreCase = true) ||
                    descriptionValue.contains(needle, ignoreCase = true) ||
                    idValue.contains(needle, ignoreCase = true)
            RuleTargetField.TEXT -> textValue.contains(needle, ignoreCase = true)
            RuleTargetField.CONTENT_DESCRIPTION -> descriptionValue.contains(needle, ignoreCase = true)
            RuleTargetField.VIEW_ID -> idValue.contains(needle, ignoreCase = true)
        }
    }

    private fun AccessibilityNodeInfo.findClickableTarget(): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = this
        var depth = 0
        while (current != null && depth < 8) {
            if (current.isClickable) {
                return current
            }
            current = current.parent
            depth += 1
        }
        return null
    }

    private fun AccessibilityNodeInfo.readableText(): String {
        val parts = listOfNotNull(
            text?.toString()?.takeIf { it.isNotBlank() },
            contentDescription?.toString()?.takeIf { it.isNotBlank() },
            viewIdResourceName?.takeIf { it.isNotBlank() },
        )
        return parts.joinToString(" | ").take(120)
    }
}
