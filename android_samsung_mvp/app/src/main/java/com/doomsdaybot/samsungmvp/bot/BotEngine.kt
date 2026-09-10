package com.doomsdaybot.samsungmvp.bot

import android.graphics.Rect
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.concurrent.thread

object BotEngine {
    @Volatile
    var status: String = "Ready"
        private set

    var onStatusChanged: ((String) -> Unit)? = null

    private val statusListeners = CopyOnWriteArrayList<(String) -> Unit>()
    private val stopListeners = CopyOnWriteArrayList<() -> Unit>()
    private val loopControl = LoopControl()
    private var worker: Thread? = null
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

    fun addStopListener(listener: () -> Unit): () -> Unit {
        stopListeners.add(listener)
        return { stopListeners.remove(listener) }
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

    @Synchronized
    fun start(service: BotAccessibilityService, rules: List<BotRule>) {
        if (worker?.isAlive == true) {
            setStatus("Previous loop is still running or stopping.")
            return
        }
        if (rules.none { it.enabled }) {
            setStatus("No enabled rules.")
            return
        }

        if (!loopControl.start()) {
            setStatus("Already running.")
            return
        }

        setRules(rules)
        setStatus("Running with ${rules.count { it.enabled }} rule(s).")
        worker = thread(name = "BotEngine", isDaemon = true, start = false) {
            try {
                loop(service)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            } catch (error: Exception) {
                android.util.Log.e("BotEngine", "Loop failed", error)
            } finally {
                loopControl.stop()
                setStatus("Stopped.")
            }
        }
        worker?.start()
    }

    @Synchronized
    fun stop() {
        loopControl.stop()
        worker?.interrupt()
        stopListeners.forEach { listener -> listener() }
        setStatus("Stopping.")
    }

    fun pause() {
        if (!loopControl.pause()) {
            setStatus("Not running.")
            return
        }
        setStatus("Paused.")
    }

    fun resume() {
        if (!loopControl.resume()) {
            setStatus("Not running.")
            return
        }
        setStatus("Running.")
    }

    @Synchronized
    fun runOnce(service: BotAccessibilityService, rules: List<BotRule>) {
        if (worker?.isAlive == true) {
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
        while (loopControl.isRunning) {
            if (loopControl.isPaused) {
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
        val tapped = if (sleepAfterTap) {
            loopControl.runIfActive { service.tapCenter(bounds) } ?: return false
        } else {
            service.tapCenter(bounds)
        }
        setStatus("Found '${target.rule.name}' at ${bounds.centerX()}, ${bounds.centerY()}. Tap=$tapped")
        if (sleepAfterTap) {
            Thread.sleep(target.rule.delayMs.coerceAtLeast(100L))
        }
        return tapped
    }
}
