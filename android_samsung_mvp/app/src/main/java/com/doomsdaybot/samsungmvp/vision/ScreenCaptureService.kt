package com.doomsdaybot.samsungmvp.vision

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import com.doomsdaybot.samsungmvp.bot.BotAccessibilityService
import com.doomsdaybot.samsungmvp.bot.BotEngine
import com.doomsdaybot.samsungmvp.scenario.BotFeatureStore
import com.doomsdaybot.samsungmvp.scenario.ScenarioRuntime
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class ScreenCaptureService : Service() {
    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var workerThread: HandlerThread? = null
    private var workerHandler: Handler? = null
    private var captureWidth = 0
    private var captureHeight = 0
    private var displayWidth = 0
    private var displayHeight = 0
    private val visualLoopRunning = AtomicBoolean(false)
    private var visualLoopThread: Thread? = null
    private val scenarioRuntime = ScenarioRuntime()

    override fun onCreate() {
        super.onCreate()
        instance = this
        workerThread = HandlerThread("VisualCapture").apply { start() }
        workerHandler = Handler(workerThread!!.looper)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
                val resultData = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(EXTRA_RESULT_DATA)
                }

                if (resultData == null) {
                    BotEngine.setStatus("Нет данных разрешения для визуального режима.")
                    stopSelf()
                    return START_NOT_STICKY
                }

                startForegroundCompat()
                startProjection(resultCode, resultData)
            }

            ACTION_STOP -> stopProjection()
            ACTION_CAPTURE_ONCE -> captureOnce()
            ACTION_SAVE_SAMPLE -> saveSample()
            ACTION_FIND_TEMPLATE -> findTemplateOnce()
            ACTION_TAP_TEMPLATE -> tapTemplateOnce()
            ACTION_START_VISUAL_LOOP -> startVisualLoop()
            ACTION_STOP_VISUAL_LOOP -> stopVisualLoop()
        }

        return START_STICKY
    }

    override fun onDestroy() {
        stopProjection()
        workerThread?.quitSafely()
        workerThread = null
        workerHandler = null
        if (instance === this) {
            instance = null
        }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    fun captureOnce() {
        val reader = imageReader
        if (reader == null) {
            BotEngine.setStatus("Визуальный режим не включён.")
            return
        }

        val image = acquireFreshFrame(reader)
        if (image == null) {
            BotEngine.setStatus("Визуальный режим включён, ждём первый кадр.")
            return
        }

        image.use { currentImage ->
            val plane = currentImage.planes.firstOrNull()
            val rowStride = plane?.rowStride ?: 0
            val pixelStride = plane?.pixelStride ?: 0
            val estimatedBytes = rowStride * currentImage.height
            val estimatedMb = estimatedBytes / (1024f * 1024f)
            BotEngine.setStatus(
                "Кадр: ${currentImage.width}x${currentImage.height}, " +
                    "rowStride=$rowStride, pixelStride=$pixelStride, ~${"%.1f".format(estimatedMb)} MB"
            )
        }
    }

    fun saveSample() {
        val reader = imageReader
        if (reader == null) {
            BotEngine.setStatus("Визуальный режим не включён.")
            return
        }

        val image = acquireFreshFrame(reader)
        if (image == null) {
            BotEngine.setStatus("Визуальный режим включён, ждём первый кадр.")
            return
        }

        image.use { currentImage ->
            val bitmap = currentImage.toBitmap()
            val outputFile = recreateLatestSampleFile()
            outputFile.outputStream().use { stream ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 90, stream)
            }
            val sizeKb = outputFile.length() / 1024
            BotEngine.setStatus("Образец сохранён: ${outputFile.name}, ${bitmap.width}x${bitmap.height}, ${sizeKb} KB")
            bitmap.recycle()
        }
    }

    fun findTemplateOnce() {
        val match = findTemplateOnFreshFrame(stopAtFirstReady = false) ?: return
        BotEngine.setStatus(
            "Вижу ${match.template.name}: x=${match.result.bounds.centerX()}, y=${match.result.bounds.centerY()}, " +
                "точность=${"%.3f".format(match.result.score)}"
        )
    }

    fun tapTemplateOnce() {
        tapBestTemplateOnce(fromLoop = false)
    }

    fun startVisualLoop() {
        if (imageReader == null) {
            BotEngine.setStatus("Визуальный режим не включён.")
            return
        }
        val settings = BotFeatureStore.load(this)
        if (settings.enabledFeatures.isEmpty()) {
            BotEngine.setStatus("Не выбрана ни одна задача.")
            return
        }
        if (VisualTemplateStore.listEnabledTemplates(this, settings.enabledFeatures).isEmpty()) {
            BotEngine.setStatus("Для выбранных задач нет шаблонов.")
            return
        }
        if (BotAccessibilityService.instance == null) {
            BotEngine.setStatus("Не могу нажимать: сервис Accessibility не включён.")
            return
        }
        if (!visualLoopRunning.compareAndSet(false, true)) {
            BotEngine.setStatus("Визуальный цикл уже работает.")
            return
        }

        scenarioRuntime.reset()
        visualLoopThread = thread(name = "VisualTemplateLoop", isDaemon = true) {
            val labels = settings.enabledFeatures.joinToString { feature -> feature.label }
            BotEngine.setStatus("Запущено: $labels.")
            try {
                while (visualLoopRunning.get()) {
                    val delayAfterTap = tapBestTemplateOnce(fromLoop = true)
                    val delay = delayAfterTap ?: VISUAL_LOOP_IDLE_MS
                    Thread.sleep(delay.coerceAtLeast(150L))
                }
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            } finally {
                visualLoopRunning.set(false)
                BotEngine.setStatus("Визуальный цикл остановлен.")
            }
        }
    }

    fun stopVisualLoop() {
        if (!visualLoopRunning.getAndSet(false)) {
            BotEngine.setStatus("Визуальный цикл не запущен.")
            return
        }
        visualLoopThread?.interrupt()
        visualLoopThread = null
        BotEngine.setStatus("Останавливаю визуальный цикл.")
    }

    private fun tapBestTemplateOnce(fromLoop: Boolean): Long? {
        val match = findTemplateOnFreshFrame(stopAtFirstReady = true) ?: return null
        if (match.result.score < match.template.threshold) {
            BotEngine.setStatus(
                "Не нажимаю: лучший ${match.template.name}, точность ${"%.3f".format(match.result.score)} " +
                    "ниже порога ${"%.2f".format(match.template.threshold)}"
            )
            return null
        }

        val service = BotAccessibilityService.instance
        if (service == null) {
            BotEngine.setStatus("Не нажимаю: сервис Accessibility не включён.")
            return null
        }

        val referenceScale = if (match.template.referenceWidth > 0 && match.template.referenceHeight > 0) {
            minOf(
                captureWidth.toFloat() / match.template.referenceWidth.toFloat(),
                captureHeight.toFloat() / match.template.referenceHeight.toFloat(),
            )
        } else {
            1f
        }
        val captureX = match.result.bounds.centerX() + match.template.clickOffsetX * referenceScale
        val captureY = match.result.bounds.centerY() + match.template.clickOffsetY * referenceScale
        val targetX = captureX * displayWidth.toFloat() / captureWidth.toFloat()
        val targetY = captureY * displayHeight.toFloat() / captureHeight.toFloat()
        val tapped = service.tap(targetX, targetY)
        if (tapped) {
            scenarioRuntime.recordTap(match.template)
        }
        val prefix = if (fromLoop) "Цикл" else "Нажал"
        BotEngine.setStatus(
            "$prefix: ${match.template.name}, x=${targetX.toInt()}, y=${targetY.toInt()}, " +
                "точность=${"%.3f".format(match.result.score)}, tap=$tapped"
        )
        return if (tapped) match.template.delayMs else null
    }

    private fun findTemplateOnFreshFrame(stopAtFirstReady: Boolean): NamedTemplateMatch? {
        val reader = imageReader
        if (reader == null) {
            BotEngine.setStatus("Визуальный режим не включён.")
            return null
        }

        val settings = BotFeatureStore.load(this)
        val templates = VisualTemplateStore
            .listEnabledTemplates(this, settings.enabledFeatures)
            .filter { template -> scenarioRuntime.isReady(template, settings) }
        if (templates.isEmpty()) {
            BotEngine.setStatus("Шаблоны не найдены. Сначала сохрани образец и выдели шаблон.")
            return null
        }

        val image = acquireFreshFrame(reader)
        if (image == null) {
            BotEngine.setStatus("Визуальный режим включён, ждём первый кадр.")
            return null
        }

        return image.use { currentImage ->
            val frame = currentImage.toBitmap()
            var bestMatch: NamedTemplateMatch? = null
            var readyMatch: NamedTemplateMatch? = null

            templates.forEach { templateInfo ->
                val template = VisualTemplateStore.loadTemplate(templateInfo) ?: return@forEach
                val result = VisualTemplateMatcher.findBestMatch(
                    frame,
                    template,
                    templateInfo.referenceWidth,
                    templateInfo.referenceHeight,
                )
                template.recycle()
                if (result != null && (bestMatch == null || result.score > bestMatch!!.result.score)) {
                    bestMatch = NamedTemplateMatch(templateInfo, result)
                }
                if (
                    stopAtFirstReady &&
                    readyMatch == null &&
                    result != null &&
                    result.score >= templateInfo.threshold
                ) {
                    readyMatch = NamedTemplateMatch(templateInfo, result)
                }
            }

            frame.recycle()
            val selectedMatch = readyMatch ?: bestMatch

            if (selectedMatch == null) {
                BotEngine.setStatus("На кадре не удалось проверить шаблоны.")
            }
            selectedMatch
        }
    }

    private fun acquireFreshFrame(reader: ImageReader): Image? {
        var latest: Image? = null
        while (true) {
            val next = try {
                reader.acquireNextImage()
            } catch (_: IllegalStateException) {
                null
            } ?: break
            latest?.close()
            latest = next
        }
        return latest
    }

    private fun Image.toBitmap(): Bitmap {
        val plane = planes[0]
        val buffer = plane.buffer
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        val rowPixels = rowStride / pixelStride
        val paddedBitmap = Bitmap.createBitmap(rowPixels, height, Bitmap.Config.ARGB_8888)
        paddedBitmap.copyPixelsFromBuffer(buffer)
        val croppedBitmap = Bitmap.createBitmap(paddedBitmap, 0, 0, width, height)
        paddedBitmap.recycle()
        return croppedBitmap
    }

    private fun recreateLatestSampleFile(): File {
        val directory = File(cacheDir, "visual")
        directory.mkdirs()
        directory.listFiles()?.forEach { file ->
            if (file.isFile) {
                file.delete()
            }
        }
        return File(directory, "latest_visual.png")
    }

    private fun startProjection(resultCode: Int, resultData: Intent) {
        stopProjection()

        val projectionManager = getSystemService(MediaProjectionManager::class.java)
        val projection = projectionManager.getMediaProjection(resultCode, resultData)
        mediaProjection = projection

        projection.registerCallback(
            object : MediaProjection.Callback() {
                override fun onStop() {
                    BotEngine.setStatus("Визуальный режим остановлен системой.")
                    stopProjection()
                }
            },
            workerHandler,
        )

        val metrics = resources.displayMetrics
        displayWidth = metrics.widthPixels
        displayHeight = metrics.heightPixels
        val quality = VisualCaptureSettings.loadQuality(this)
        val maxCaptureWidth = quality.maxWidth
        val scale = if (maxCaptureWidth > 0 && metrics.widthPixels > maxCaptureWidth) {
            maxCaptureWidth.toFloat() / metrics.widthPixels.toFloat()
        } else {
            1f
        }
        captureWidth = (metrics.widthPixels * scale).toInt().coerceAtLeast(320)
        captureHeight = (metrics.heightPixels * scale).toInt().coerceAtLeast(320)

        val reader = ImageReader.newInstance(captureWidth, captureHeight, PixelFormat.RGBA_8888, 2)
        imageReader = reader

        virtualDisplay = projection.createVirtualDisplay(
            "DoomsdayVisualCapture",
            captureWidth,
            captureHeight,
            metrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.surface,
            null,
            workerHandler,
        )

        BotEngine.setStatus("Визуальный режим включён: ${captureWidth}x${captureHeight}, ${quality.label}.")
    }

    private fun stopProjection() {
        if (visualLoopRunning.getAndSet(false)) {
            visualLoopThread?.interrupt()
            visualLoopThread = null
        }
        virtualDisplay?.release()
        virtualDisplay = null
        imageReader?.close()
        imageReader = null
        val projection = mediaProjection
        mediaProjection = null
        projection?.stop()
        BotEngine.setStatus("Визуальный режим остановлен.")
    }

    private fun startForegroundCompat() {
        createNotificationChannel()
        val notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("BuZzbot")
            .setContentText("Визуальный режим доступен для игры.")
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }

        val channel = NotificationChannel(
            CHANNEL_ID,
            "Visual capture",
            NotificationManager.IMPORTANCE_LOW,
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private data class NamedTemplateMatch(
        val template: VisualTemplateInfo,
        val result: TemplateMatchResult,
    )

    companion object {
        const val ACTION_START = "com.doomsdaybot.samsungmvp.visual.START"
        const val ACTION_STOP = "com.doomsdaybot.samsungmvp.visual.STOP"
        const val ACTION_CAPTURE_ONCE = "com.doomsdaybot.samsungmvp.visual.CAPTURE_ONCE"
        const val ACTION_SAVE_SAMPLE = "com.doomsdaybot.samsungmvp.visual.SAVE_SAMPLE"
        const val ACTION_FIND_TEMPLATE = "com.doomsdaybot.samsungmvp.visual.FIND_TEMPLATE"
        const val ACTION_TAP_TEMPLATE = "com.doomsdaybot.samsungmvp.visual.TAP_TEMPLATE"
        const val ACTION_START_VISUAL_LOOP = "com.doomsdaybot.samsungmvp.visual.START_LOOP"
        const val ACTION_STOP_VISUAL_LOOP = "com.doomsdaybot.samsungmvp.visual.STOP_LOOP"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"

        private const val CHANNEL_ID = "visual_capture"
        private const val NOTIFICATION_ID = 1001
        private const val VISUAL_LOOP_IDLE_MS = 700L

        @Volatile
        private var instance: ScreenCaptureService? = null

        fun captureOnce() {
            val service = instance
            if (service == null) {
                BotEngine.setStatus("Визуальный режим не включён. Открой приложение и включи визуальный режим.")
                return
            }
            service.captureOnce()
        }

        fun saveSample() {
            val service = instance
            if (service == null) {
                BotEngine.setStatus("Визуальный режим не включён. Открой приложение и включи визуальный режим.")
                return
            }
            service.saveSample()
        }

        fun findTemplateOnce() {
            val service = instance
            if (service == null) {
                BotEngine.setStatus("Визуальный режим не включён. Открой приложение и включи визуальный режим.")
                return
            }
            service.findTemplateOnce()
        }

        fun tapTemplateOnce() {
            val service = instance
            if (service == null) {
                BotEngine.setStatus("Визуальный режим не включён. Открой приложение и включи визуальный режим.")
                return
            }
            service.tapTemplateOnce()
        }

        fun startVisualLoop() {
            val service = instance
            if (service == null) {
                BotEngine.setStatus("Визуальный режим не включён. Открой приложение и включи визуальный режим.")
                return
            }
            service.startVisualLoop()
        }

        fun isVisualModeActive(): Boolean = instance?.imageReader != null

        fun stopVisualLoop() {
            val service = instance
            if (service == null) {
                BotEngine.setStatus("Визуальный режим не включён.")
                return
            }
            service.stopVisualLoop()
        }

        fun clearTemplates(context: Context) {
            val deleted = VisualTemplateStore.clearTemplates(context)
            BotEngine.setStatus("Удалено шаблонов: $deleted.")
        }

        fun stop(context: Context) {
            context.startService(Intent(context, ScreenCaptureService::class.java).setAction(ACTION_STOP))
        }
    }
}
