package com.doomsdaybot.samsungmvp.vision

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import android.view.ViewParent
import kotlin.math.max
import kotlin.math.min

class TemplateSelectionView(
    context: Context,
    private val sourceBitmap: Bitmap,
) : View(context) {
    private val selectionRect = RectF()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var startX = 0f
    private var startY = 0f
    private var imageScale = 1f

    fun setImageScale(scale: Float) {
        imageScale = scale.coerceIn(0.25f, 4f)
        selectionRect.setEmpty()
        requestLayout()
        invalidate()
    }

    fun imageScale(): Float = imageScale

    fun selectedImageRect(): Rect? {
        if (selectionRect.width() < 12f || selectionRect.height() < 12f) {
            return null
        }

        val left = viewToImage(selectionRect.left).toInt().coerceIn(0, sourceBitmap.width - 1)
        val top = viewToImage(selectionRect.top).toInt().coerceIn(0, sourceBitmap.height - 1)
        val right = viewToImage(selectionRect.right).toInt().coerceIn(left + 1, sourceBitmap.width)
        val bottom = viewToImage(selectionRect.bottom).toInt().coerceIn(top + 1, sourceBitmap.height)
        return Rect(left, top, right, bottom)
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredWidth = (sourceBitmap.width * imageScale).toInt()
        val desiredHeight = (sourceBitmap.height * imageScale).toInt()
        setMeasuredDimension(
            resolveSize(desiredWidth, widthMeasureSpec),
            resolveSize(desiredHeight, heightMeasureSpec),
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.rgb(12, 16, 24))

        val destination = RectF(
            0f,
            0f,
            sourceBitmap.width * imageScale,
            sourceBitmap.height * imageScale,
        )
        canvas.drawBitmap(sourceBitmap, null, destination, null)

        if (!selectionRect.isEmpty) {
            paint.style = Paint.Style.FILL
            paint.color = Color.argb(70, 0, 180, 255)
            canvas.drawRect(selectionRect, paint)

            paint.style = Paint.Style.STROKE
            paint.strokeWidth = 4f
            paint.color = Color.CYAN
            canvas.drawRect(selectionRect, paint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val maxX = (sourceBitmap.width * imageScale).coerceAtLeast(1f)
        val maxY = (sourceBitmap.height * imageScale).coerceAtLeast(1f)
        val x = event.x.coerceIn(0f, maxX)
        val y = event.y.coerceIn(0f, maxY)

        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                requestParentsDoNotIntercept(true)
                startX = x
                startY = y
                selectionRect.set(x, y, x, y)
                invalidate()
                return true
            }

            MotionEvent.ACTION_MOVE,
            MotionEvent.ACTION_UP,
            -> {
                requestParentsDoNotIntercept(true)
                selectionRect.set(
                    min(startX, x),
                    min(startY, y),
                    max(startX, x),
                    max(startY, y),
                )
                invalidate()
                if (event.action == MotionEvent.ACTION_UP) {
                    requestParentsDoNotIntercept(false)
                }
                return true
            }

            MotionEvent.ACTION_CANCEL -> {
                requestParentsDoNotIntercept(false)
                return true
            }
        }

        return true
    }

    private fun viewToImage(value: Float): Float = value / imageScale

    private fun requestParentsDoNotIntercept(disallow: Boolean) {
        var currentParent: ViewParent? = parent
        while (currentParent != null) {
            currentParent.requestDisallowInterceptTouchEvent(disallow)
            currentParent = currentParent.parent
        }
    }
}
