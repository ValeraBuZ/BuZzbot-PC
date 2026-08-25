package com.doomsdaybot.samsungmvp.vision

import android.graphics.Bitmap
import android.graphics.Rect
import kotlin.math.max
import kotlin.math.min

data class TemplateMatchResult(
    val bounds: Rect,
    val score: Float,
)

object VisualTemplateMatcher {
    private const val MAX_MATCH_WIDTH = 720

    fun findBestMatch(
        frame: Bitmap,
        template: Bitmap,
        referenceFrameWidth: Int = 0,
        referenceFrameHeight: Int = 0,
    ): TemplateMatchResult? {
        if (template.width < 6 || template.height < 6) {
            return null
        }

        val referenceScale = if (referenceFrameWidth > 0 && referenceFrameHeight > 0) {
            min(
                frame.width.toFloat() / referenceFrameWidth.toFloat(),
                frame.height.toFloat() / referenceFrameHeight.toFloat(),
            ).coerceIn(0.35f, 3f)
        } else {
            1f
        }
        val preparedTemplate = if (kotlin.math.abs(referenceScale - 1f) > 0.01f) {
            Bitmap.createScaledBitmap(
                template,
                max(6, (template.width * referenceScale).toInt()),
                max(6, (template.height * referenceScale).toInt()),
                true,
            )
        } else {
            template
        }

        if (preparedTemplate.width > frame.width || preparedTemplate.height > frame.height) {
            if (preparedTemplate !== template) {
                preparedTemplate.recycle()
            }
            return null
        }

        val scale = if (frame.width > MAX_MATCH_WIDTH) {
            MAX_MATCH_WIDTH.toFloat() / frame.width.toFloat()
        } else {
            1f
        }

        val matchFrame = if (scale < 1f) {
            Bitmap.createScaledBitmap(
                frame,
                (frame.width * scale).toInt(),
                (frame.height * scale).toInt(),
                true,
            )
        } else {
            frame
        }

        val matchTemplate = if (scale < 1f) {
            Bitmap.createScaledBitmap(
                preparedTemplate,
                max(6, (preparedTemplate.width * scale).toInt()),
                max(6, (preparedTemplate.height * scale).toInt()),
                true,
            )
        } else {
            preparedTemplate
        }

        val result = findBestMatchScaled(matchFrame, matchTemplate, scale)

        if (matchFrame !== frame) {
            matchFrame.recycle()
        }
        if (matchTemplate !== preparedTemplate) {
            matchTemplate.recycle()
        }
        if (preparedTemplate !== template) {
            preparedTemplate.recycle()
        }

        return result
    }

    private fun findBestMatchScaled(
        frame: Bitmap,
        template: Bitmap,
        scale: Float,
    ): TemplateMatchResult? {
        val framePixels = IntArray(frame.width * frame.height)
        val templatePixels = IntArray(template.width * template.height)
        frame.getPixels(framePixels, 0, frame.width, 0, 0, frame.width, frame.height)
        template.getPixels(templatePixels, 0, template.width, 0, 0, template.width, template.height)

        val scanStep = max(2, min(template.width, template.height) / 10)
        val sampleStep = max(1, min(template.width, template.height) / 24)
        var bestScore = -1f
        var bestX = 0
        var bestY = 0

        val maxY = frame.height - template.height
        val maxX = frame.width - template.width
        var y = 0
        while (y <= maxY) {
            var x = 0
            while (x <= maxX) {
                val score = scoreAt(framePixels, frame.width, templatePixels, template.width, template.height, x, y, sampleStep)
                if (score > bestScore) {
                    bestScore = score
                    bestX = x
                    bestY = y
                }
                x += scanStep
            }
            y += scanStep
        }

        val refineRadius = scanStep
        for (refineY in max(0, bestY - refineRadius)..min(maxY, bestY + refineRadius)) {
            for (refineX in max(0, bestX - refineRadius)..min(maxX, bestX + refineRadius)) {
                val score = scoreAt(framePixels, frame.width, templatePixels, template.width, template.height, refineX, refineY, sampleStep)
                if (score > bestScore) {
                    bestScore = score
                    bestX = refineX
                    bestY = refineY
                }
            }
        }

        val inverseScale = 1f / scale
        val left = (bestX * inverseScale).toInt()
        val top = (bestY * inverseScale).toInt()
        val right = ((bestX + template.width) * inverseScale).toInt()
        val bottom = ((bestY + template.height) * inverseScale).toInt()
        return TemplateMatchResult(Rect(left, top, right, bottom), bestScore)
    }

    private fun scoreAt(
        framePixels: IntArray,
        frameWidth: Int,
        templatePixels: IntArray,
        templateWidth: Int,
        templateHeight: Int,
        startX: Int,
        startY: Int,
        sampleStep: Int,
    ): Float {
        var totalDiff = 0L
        var count = 0

        var y = 0
        while (y < templateHeight) {
            var x = 0
            while (x < templateWidth) {
                val frameColor = framePixels[(startY + y) * frameWidth + startX + x]
                val templateColor = templatePixels[y * templateWidth + x]
                totalDiff += colorDistance(frameColor, templateColor)
                count += 1
                x += sampleStep
            }
            y += sampleStep
        }

        if (count == 0) {
            return 0f
        }

        val averageDiff = totalDiff.toFloat() / count.toFloat()
        return 1f - (averageDiff / 255f)
    }

    private fun colorDistance(first: Int, second: Int): Int {
        val r1 = (first shr 16) and 0xFF
        val g1 = (first shr 8) and 0xFF
        val b1 = first and 0xFF
        val r2 = (second shr 16) and 0xFF
        val g2 = (second shr 8) and 0xFF
        val b2 = second and 0xFF
        return (kotlin.math.abs(r1 - r2) + kotlin.math.abs(g1 - g2) + kotlin.math.abs(b1 - b2)) / 3
    }
}
