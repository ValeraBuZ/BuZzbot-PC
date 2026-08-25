package com.doomsdaybot.samsungmvp

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.doomsdaybot.samsungmvp.bot.BotAccessibilityService
import com.doomsdaybot.samsungmvp.bot.BotEngine
import com.doomsdaybot.samsungmvp.scenario.BotFeature
import com.doomsdaybot.samsungmvp.scenario.BotFeatureSettings
import com.doomsdaybot.samsungmvp.scenario.BotFeatureStore
import com.doomsdaybot.samsungmvp.vision.BuiltInTemplateInstaller
import com.doomsdaybot.samsungmvp.vision.ScreenCaptureService
import com.doomsdaybot.samsungmvp.vision.TemplateManagerActivity
import com.doomsdaybot.samsungmvp.vision.VisualCaptureSettings
import com.doomsdaybot.samsungmvp.vision.VisualQuality
import com.doomsdaybot.samsungmvp.vision.VisualTemplateStore

class MainActivity : Activity() {
    private lateinit var statusView: TextView
    private lateinit var templateInfoView: TextView
    private lateinit var repeatPrizeCheck: CheckBox
    private lateinit var visualQualitySpinner: Spinner
    private val featureChecks = linkedMapOf<BotFeature, CheckBox>()
    private var startAfterCapturePermission = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val installResult = BuiltInTemplateInstaller.install(this)
        val savedSettings = BotFeatureStore.load(this)

        BotEngine.onStatusChanged = { status ->
            runOnUiThread {
                if (::statusView.isInitialized) {
                    statusView.text = status
                }
            }
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(32, 40, 32, 32)
        }
        val advancedContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }

        container.addView(TextView(this).apply {
            text = "BuZzbot Android"
            textSize = 24f
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, 8)
        })
        container.addView(TextView(this).apply {
            text = "Мобильная версия: лечение, зомби и охота за призом"
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, 20)
        })

        statusView = TextView(this).apply {
            text = if (installResult.failed == 0) {
                BotEngine.status
            } else {
                "Не удалось установить шаблонов: ${installResult.failed}."
            }
            textSize = 16f
            setPadding(16, 16, 16, 20)
        }
        templateInfoView = TextView(this).apply {
            textSize = 13f
            setPadding(0, 0, 0, 12)
        }
        container.addView(statusView)
        container.addView(templateInfoView)

        container.addView(sectionTitle("Что запускать"))
        BotFeature.entries.forEach { feature ->
            val checkBox = CheckBox(this).apply {
                text = feature.label
                textSize = 17f
                isChecked = feature in savedSettings.enabledFeatures
            }
            featureChecks[feature] = checkBox
            container.addView(checkBox, fullWidthParams())
        }
        repeatPrizeCheck = CheckBox(this).apply {
            text = "Повторять охоту за призом до остановки"
            isChecked = savedSettings.repeatPrizeHunt
        }
        container.addView(repeatPrizeCheck, fullWidthParams())

        container.addView(sectionTitle("Запуск"))
        container.addView(fullButton("1. Включить спец. возможности") {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        })
        container.addView(fullButton("2. Разрешить захват экрана") {
            saveSettingsFromUi()
            requestVisualCapture(autoStart = false)
        })
        container.addView(fullButton("3. Запустить выбранные задачи") {
            startSelectedTasks()
        })
        container.addView(fullButton("Остановить бота") {
            BotEngine.stop()
            ScreenCaptureService.stopVisualLoop()
        })
        container.addView(fullButton("Показать панель поверх игры") {
            val service = BotAccessibilityService.instance
            if (service == null) {
                BotEngine.setStatus("Сервис Accessibility не включён.")
            } else {
                service.showOverlay()
                BotEngine.setStatus("Панель показана. Можно открыть игру.")
            }
        })
        container.addView(fullButton("Открыть Doomsday: Last Survivors") {
            launchGame()
        })
        container.addView(fullButton("Диагностика и шаблоны") {
            advancedContainer.visibility = if (advancedContainer.visibility == View.VISIBLE) {
                View.GONE
            } else {
                View.VISIBLE
            }
        })

        buildAdvancedSettings(advancedContainer)
        container.addView(advancedContainer)

        setContentView(ScrollView(this).apply { addView(container) })
        refreshTemplateInfo()
    }

    override fun onResume() {
        super.onResume()
        if (::templateInfoView.isInitialized) {
            refreshTemplateInfo()
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != SCREEN_CAPTURE_REQUEST_CODE) {
            return
        }
        if (resultCode != RESULT_OK || data == null) {
            startAfterCapturePermission = false
            BotEngine.setStatus("Разрешение на захват экрана не выдано.")
            return
        }

        val serviceIntent = Intent(this, ScreenCaptureService::class.java).apply {
            action = ScreenCaptureService.ACTION_START
            putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, resultCode)
            putExtra(ScreenCaptureService.EXTRA_RESULT_DATA, data)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }

        if (startAfterCapturePermission) {
            startAfterCapturePermission = false
            Handler(Looper.getMainLooper()).postDelayed(
                {
                    ScreenCaptureService.startVisualLoop()
                    launchGame()
                },
                800L,
            )
        }
    }

    override fun onDestroy() {
        BotEngine.onStatusChanged = null
        super.onDestroy()
    }

    private fun startSelectedTasks() {
        val settings = saveSettingsFromUi()
        if (settings.enabledFeatures.isEmpty()) {
            BotEngine.setStatus("Выбери хотя бы одну задачу.")
            return
        }
        if (BotAccessibilityService.instance == null) {
            BotEngine.setStatus("Сначала включи BuZzbot в специальных возможностях Android.")
            return
        }
        if (!ScreenCaptureService.isVisualModeActive()) {
            BotEngine.setStatus("Нужно разрешение на захват экрана.")
            requestVisualCapture(autoStart = true)
            return
        }
        ScreenCaptureService.startVisualLoop()
        launchGame()
    }

    private fun saveSettingsFromUi(): BotFeatureSettings {
        val settings = BotFeatureSettings(
            enabledFeatures = featureChecks
                .filterValues(CheckBox::isChecked)
                .keys,
            repeatPrizeHunt = repeatPrizeCheck.isChecked,
        )
        BotFeatureStore.save(this, settings)
        return settings
    }

    private fun requestVisualCapture(autoStart: Boolean) {
        startAfterCapturePermission = autoStart
        val manager = getSystemService(MediaProjectionManager::class.java)
        startActivityForResult(manager.createScreenCaptureIntent(), SCREEN_CAPTURE_REQUEST_CODE)
    }

    private fun launchGame() {
        val launchIntent = packageManager.getLaunchIntentForPackage(GAME_PACKAGE)
        if (launchIntent == null) {
            BotEngine.setStatus("Doomsday: Last Survivors не найдена на телефоне.")
            return
        }
        startActivity(launchIntent)
    }

    private fun buildAdvancedSettings(container: LinearLayout) {
        container.addView(sectionTitle("Диагностика"))
        visualQualitySpinner = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity,
                android.R.layout.simple_spinner_item,
                VisualQuality.entries.map { quality -> quality.label },
            ).apply {
                setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            }
            setSelection(VisualCaptureSettings.loadQuality(this@MainActivity).ordinal)
        }
        container.addView(visualQualitySpinner, fullWidthParams())
        container.addView(fullButton("Сохранить качество кадра") {
            val quality = VisualQuality.entries.getOrElse(visualQualitySpinner.selectedItemPosition) {
                VisualQuality.FULL
            }
            VisualCaptureSettings.saveQuality(this@MainActivity, quality)
            BotEngine.setStatus("Качество: ${quality.label}. Перезапусти захват экрана.")
        })
        container.addView(fullButton("Проверить текущий кадр") { ScreenCaptureService.captureOnce() })
        container.addView(fullButton("Сохранить кадр для калибровки") { ScreenCaptureService.saveSample() })
        container.addView(fullButton("Найти лучший шаг") { ScreenCaptureService.findTemplateOnce() })
        container.addView(fullButton("Найти и нажать один шаг") { ScreenCaptureService.tapTemplateOnce() })
        container.addView(fullButton("Открыть шаблоны") {
            startActivity(Intent(this@MainActivity, TemplateManagerActivity::class.java))
        })
        container.addView(fullButton("Восстановить штатные шаблоны") {
            val result = BuiltInTemplateInstaller.install(this@MainActivity)
            refreshTemplateInfo()
            BotEngine.setStatus("Штатные шаблоны: ${result.available}, восстановлено: ${result.copied}.")
        })
        container.addView(fullButton("Остановить захват экрана") {
            ScreenCaptureService.stop(this@MainActivity)
        })
    }

    private fun refreshTemplateInfo() {
        val templates = VisualTemplateStore.listTemplates(this)
        val featureSummary = BotFeature.entries.joinToString(separator = " • ") { feature ->
            val count = templates.count { template -> template.feature == feature }
            "${feature.label}: $count"
        }
        templateInfoView.text = "Штатные шаги: $featureSummary"
    }

    private fun sectionTitle(value: String): TextView = TextView(this).apply {
        text = value
        textSize = 19f
        setPadding(0, 18, 0, 8)
    }

    private fun fullButton(value: String, onClick: () -> Unit): Button = Button(this).apply {
        text = value
        isAllCaps = false
        setOnClickListener { onClick() }
        layoutParams = fullWidthParams()
    }

    private fun fullWidthParams(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(
        LinearLayout.LayoutParams.MATCH_PARENT,
        LinearLayout.LayoutParams.WRAP_CONTENT,
    )

    companion object {
        private const val SCREEN_CAPTURE_REQUEST_CODE = 2001
        private const val GAME_PACKAGE = "com.igg.android.doomsdaylastsurvivors"
    }
}
