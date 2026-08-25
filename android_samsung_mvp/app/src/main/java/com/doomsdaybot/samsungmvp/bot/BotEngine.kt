package com.doomsdaybot.samsungmvp.bot

import android.graphics.Rect
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

object BotEngine {
    @Volatile
    var status: String = "Ready"
        private set

    var onStatusChanged: ((String) -> Unit)? = null

    private val statusListeners = CopyOnWriteArrayList<(String) -> Unit>()
    private val running = AtomicBoolean(false)
    private val paused = AtomicBoolean(false)
    @Volatile
    private var rules: List<BotRule> = emptyList()

    fun setStatus(value: String) {
        status = value
        onStatusChanged?.invoke(value)
        statusListeners.forEach { listener -> listener(value) }
    }

    fun addStatusListener(listener: (String) -> Unit): () -> Unit {
        statusListeners.add(listener)
        listener(status)
        return {
            statusListeners.remove(listener)
        }
    }

    fun setRules(value: List<BotRule>) {
        rules = value
    }

    fun inspectCurrentScreen(service: BotAccessibilityService, rules: List<BotRule> = this.rules) {
        val root = service.activeRoot()
        if (root == null) {
            setStatus("No active window.")
            return
        }

        val summary = UiNodeFinder.summarize(root)
        val match = UiNodeFinder.findFirstMatchingRule(root, rules)
        val samples = UiNodeFinder.sampleReadableNodes(root).joinToString("; ")
        val matchText = if (match == null) {
            "No rule match."
        } else {
            "Match: ${match.rule.name}"
        }
        setStatus(
            "Nodes: ${summary.totalNodes}, clickable: ${summary.clickableNodes}, readable: ${summary.readableNodes}. " +
                "$matchText Seen: $samples"
        )
    }

    fun start(service: BotAccessibilityService, rules: List<BotRule>) {
        if (rules.none { it.enabled }) {
            setStatus("No enabled rules.")
            return
        }

        if (!running.compareAndSet(false, true)) {
            setStatus("Already running.")
            return
        }

        paused.set(false)
        setRules(rules)
        setStatus("Running with ${rules.count { it.enabled }} rule(s).")
        thread(name = "BotEngine", isDaemon = true) {
            try {
                loop(service)
            } finally {
                running.set(false)
                setStatus("Stopped.")
            }
        }
    }

    fun stop() {
        running.set(false)
        setStatus("Stopping.")
    }

    fun pause() {
        if (!running.get()) {
            setStatus("Not running.")
            return
        }
        paused.set(true)
        setStatus("Paused.")
    }

    fun resume() {
        if (!running.get()) {
            setStatus("Not running.")
            return
        }
        paused.set(false)
        setStatus("Running.")
    }

    fun runOnce(service: BotAccessibilityService, rules: List<BotRule>) {
        if (running.get()) {
            setStatus("Stop the loop before Test once.")
            return
        }
        if (rules.none { it.enabled }) {
            setStatus("No enabled rules.")
            return
        }

        setRules(rules)
        executeOneStep(service, rules, sleepAfterTap = false)
    }

    private fun loop(service: BotAccessibilityService) {
        while (running.get()) {
            if (paused.get()) {
                Thread.sleep(300)
                continue
            }

            val didTap = executeOneStep(service, rules, sleepAfterTap = true)
            if (!didTap) {
                Thread.sleep(700)
            }
        }
    }

    private fun executeOneStep(
        service: BotAccessibilityService,
        rules: List<BotRule>,
        sleepAfterTap: Boolean,
    ): Boolean {
        val root = service.activeRoot()
        if (root == null) {
            setStatus("Waiting for active window.")
            return false
        }

        val target = UiNodeFinder.findFirstMatchingRule(root, rules)
        if (target == null) {
            setStatus("No matching accessible node for ${rules.count { it.enabled }} rule(s).")
            return false
        }

        val bounds = Rect()
        target.node.getBoundsInScreen(bounds)
        val tapped = service.tapCenter(bounds)
        setStatus("Found '${target.rule.name}' at ${bounds.centerX()}, ${bounds.centerY()}. Tap=$tapped")
        if (sleepAfterTap) {
            Thread.sleep(target.rule.delayMs.coerceAtLeast(100L))
        }
        return tapped
    }
}
