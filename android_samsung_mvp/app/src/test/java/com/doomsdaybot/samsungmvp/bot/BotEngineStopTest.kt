package com.doomsdaybot.samsungmvp.bot

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class BotEngineStopTest {
    @Test
    fun stopNotifiesPendingLaunchEvenWhenNoWorkerIsRunning() {
        var launchPending = true
        val remove = BotEngine.addStopListener { launchPending = false }
        try {
            BotEngine.stop()
            assertFalse(launchPending)
        } finally {
            remove()
        }
    }

    @Test
    fun removingOldActivityDoesNotRemoveCurrentActivityStopListener() {
        var previousNotifications = 0
        var currentNotifications = 0
        val removePrevious = BotEngine.addStopListener { previousNotifications++ }
        val removeCurrent = BotEngine.addStopListener { currentNotifications++ }
        try {
            removePrevious()
            BotEngine.stop()
            assertEquals(0, previousNotifications)
            assertEquals(1, currentNotifications)
        } finally {
            removePrevious()
            removeCurrent()
        }
    }
}
