package com.doomsdaybot.samsungmvp.bot

import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LoopControlTest {
    @Test
    fun pauseSuppressesTapsAndResumeContinuesWithoutRestart() {
        val control = LoopControl()
        val taps = AtomicInteger()
        assertTrue(control.start())
        control.runIfActive { taps.incrementAndGet() }
        assertTrue(control.pause())
        assertTrue(control.isRunning)
        assertNull(control.runIfActive { taps.incrementAndGet() })
        assertFalse(control.start())
        assertTrue(control.isPaused)
        assertTrue(control.resume())
        control.runIfActive { taps.incrementAndGet() }
        assertEquals(2, taps.get())
    }

    @Test
    fun stopCannotBeUndoneByResume() {
        val control = LoopControl()
        control.start()
        control.pause()
        assertTrue(control.stop())
        assertFalse(control.resume())
        assertFalse(control.isRunning)
        assertFalse(control.isPaused)
        assertNull(control.runIfActive { error("Stopped loop submitted a tap") })
        assertTrue(control.start())
        assertEquals("tap", control.runIfActive { "tap" })
    }

    @Test
    fun stopDiscardsMatchThatFinishesAfterStop() = assertDelayedMatchSuppressed { stop() }

    @Test
    fun pauseDiscardsMatchThatFinishesWhilePaused() = assertDelayedMatchSuppressed { pause() }

    private fun assertDelayedMatchSuppressed(cancel: LoopControl.() -> Boolean) {
        val control = LoopControl()
        val matching = CountDownLatch(1)
        val finishMatching = CountDownLatch(1)
        val taps = AtomicInteger()
        val executor = Executors.newSingleThreadExecutor()
        control.start()
        try {
            val result = executor.submit<Int?> {
                matching.countDown()
                assertTrue(finishMatching.await(5, TimeUnit.SECONDS))
                control.runIfActive { taps.incrementAndGet() }
            }
            assertTrue(matching.await(5, TimeUnit.SECONDS))
            assertTrue(control.cancel())
            finishMatching.countDown()
            assertNull(result.get(5, TimeUnit.SECONDS))
            assertEquals(0, taps.get())
        } finally {
            finishMatching.countDown()
            executor.shutdownNow()
        }
    }

    @Test
    fun interruptedWorkerCannotSubmitTap() {
        val control = LoopControl()
        val executor = Executors.newSingleThreadExecutor()
        control.start()
        try {
            val result = executor.submit<Boolean> {
                Thread.currentThread().interrupt()
                try {
                    control.runIfActive<Boolean> { error("Interrupted worker submitted a tap") } == null
                } finally {
                    Thread.interrupted()
                }
            }
            assertTrue(result.get(5, TimeUnit.SECONDS))
        } finally {
            executor.shutdownNow()
        }
    }

    @Test
    fun stopWaitsForGestureSubmissionAlreadyInProgress() = assertCancellationSerialized { stop() }

    @Test
    fun pauseWaitsForGestureSubmissionAlreadyInProgress() = assertCancellationSerialized { pause() }

    private fun assertCancellationSerialized(cancel: LoopControl.() -> Boolean) {
        val control = LoopControl()
        val submitting = CountDownLatch(1)
        val finishSubmission = CountDownLatch(1)
        val cancelling = CountDownLatch(1)
        val cancelled = CountDownLatch(1)
        val executor = Executors.newFixedThreadPool(2)
        control.start()
        try {
            val tap = executor.submit<String?> {
                control.runIfActive {
                    submitting.countDown()
                    assertTrue(finishSubmission.await(5, TimeUnit.SECONDS))
                    "submitted"
                }
            }
            assertTrue(submitting.await(5, TimeUnit.SECONDS))
            val cancellation = executor.submit<Boolean> {
                cancelling.countDown()
                control.cancel().also { cancelled.countDown() }
            }
            assertTrue(cancelling.await(5, TimeUnit.SECONDS))
            assertFalse(cancelled.await(100, TimeUnit.MILLISECONDS))
            finishSubmission.countDown()
            assertEquals("submitted", tap.get(5, TimeUnit.SECONDS))
            assertTrue(cancellation.get(5, TimeUnit.SECONDS))
            assertNull(control.runIfActive { error("Tap submitted after cancellation returned") })
        } finally {
            finishSubmission.countDown()
            executor.shutdownNow()
        }
    }
}
