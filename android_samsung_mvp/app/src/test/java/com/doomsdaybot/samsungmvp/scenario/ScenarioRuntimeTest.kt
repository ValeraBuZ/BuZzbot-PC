package com.doomsdaybot.samsungmvp.scenario

import com.doomsdaybot.samsungmvp.vision.VisualTemplateInfo
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScenarioRuntimeTest {
    @Test
    fun catalogContainsOnlyRequestedFeatures() {
        val counts = BuiltInScenarioCatalog.templates.groupingBy { definition ->
            definition.feature
        }.eachCount()

        assertEquals(setOf(BotFeature.HEAL, BotFeature.ZOMBIE_HUNT, BotFeature.PRIZE_HUNT), counts.keys)
        assertEquals(4, counts[BotFeature.HEAL])
        assertEquals(7, counts[BotFeature.ZOMBIE_HUNT])
        assertEquals(12, counts[BotFeature.PRIZE_HUNT])
    }

    @Test
    fun strictZombieStepWaitsForPreviousStep() {
        val runtime = ScenarioRuntime()
        val settings = BotFeatureSettings(setOf(BotFeature.ZOMBIE_HUNT))
        val openSearch = template(BotFeature.ZOMBIE_HUNT, "world_search")
        val selectZombie = template(
            BotFeature.ZOMBIE_HUNT,
            "zombie_icon",
            requiredSteps = setOf("world_search"),
        )

        assertFalse(runtime.isReady(selectZombie, settings))
        runtime.recordTap(openSearch)
        assertTrue(runtime.isReady(selectZombie, settings))
    }

    @Test
    fun prizeResultUsesConfiguredBranch() {
        val runtime = ScenarioRuntime()
        val repeat = template(
            BotFeature.PRIZE_HUNT,
            "again",
            allowRuntimeResume = true,
            requiredPrizeRepeat = true,
        )
        val exit = template(
            BotFeature.PRIZE_HUNT,
            "safe_exit",
            allowRuntimeResume = true,
            requiredPrizeRepeat = false,
        )

        assertTrue(runtime.isReady(repeat, BotFeatureSettings(setOf(BotFeature.PRIZE_HUNT), true)))
        assertFalse(runtime.isReady(exit, BotFeatureSettings(setOf(BotFeature.PRIZE_HUNT), true)))
        assertFalse(runtime.isReady(repeat, BotFeatureSettings(setOf(BotFeature.PRIZE_HUNT), false)))
        assertTrue(runtime.isReady(exit, BotFeatureSettings(setOf(BotFeature.PRIZE_HUNT), false)))
    }

    @Test
    fun disabledFeatureNeverRuns() {
        val runtime = ScenarioRuntime()
        val healing = template(BotFeature.HEAL, "open_wounded")
        assertFalse(runtime.isReady(healing, BotFeatureSettings(setOf(BotFeature.ZOMBIE_HUNT))))
    }

    private fun template(
        feature: BotFeature,
        step: String,
        requiredSteps: Set<String> = emptySet(),
        allowRuntimeResume: Boolean = false,
        requiredPrizeRepeat: Boolean? = null,
    ) = VisualTemplateInfo(
        id = step,
        name = step,
        file = File("$step.png"),
        featureId = feature.id,
        group = feature.templateGroup,
        stepId = step,
        requiredSteps = requiredSteps,
        allowRuntimeResume = allowRuntimeResume,
        requiredPrizeRepeat = requiredPrizeRepeat,
    )
}
