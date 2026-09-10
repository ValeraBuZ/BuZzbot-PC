package com.doomsdaybot.samsungmvp.bot

/** Serializes pause/stop with the final gesture submission, after expensive screen matching. */
internal class LoopControl {
    @Volatile
    var isRunning: Boolean = false
        private set

    @Volatile
    var isPaused: Boolean = false
        private set

    @Synchronized
    fun start(): Boolean {
        if (isRunning) return false
        isPaused = false
        isRunning = true
        return true
    }

    @Synchronized
    fun stop(): Boolean {
        val wasRunning = isRunning
        isRunning = false
        isPaused = false
        return wasRunning
    }

    @Synchronized
    fun pause(): Boolean {
        if (!isRunning) return false
        isPaused = true
        return true
    }

    @Synchronized
    fun resume(): Boolean {
        if (!isRunning) return false
        isPaused = false
        return true
    }

    @Synchronized
    fun <T> runIfActive(action: () -> T): T? {
        if (!isRunning || isPaused || Thread.currentThread().isInterrupted) return null
        return action()
    }
}
