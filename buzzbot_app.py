import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
import json
import uuid
import sys
import ctypes
import cv2
import numpy as np
import shutil
import logging
import queue
import subprocess
import tempfile
import zipfile
from datetime import datetime
from buzzbot.accounts import (
    apply_tasks as apply_account_tasks,
    ensure_account_task_defaults,
    default_account_profiles,
    extract_android_google_accounts,
    extract_google_account_targets,
    extract_google_accounts,
    extract_igg_id_targets,
    extract_igg_login_form,
    extract_igg_unregistered_cancel_target,
    find_account,
    mask_google_account,
    requires_manual_google_verification,
    requires_google_reauthentication,
    recover_account_profiles,
    next_enabled_account,
    normalize_account_profiles,
    snapshot_tasks as snapshot_account_tasks,
)
from buzzbot.adb import AdbClient, AdbError, find_adb_executable
from buzzbot.compact_ui import build_compact_ui
from buzzbot.credentials import CredentialError, CredentialStore
from buzzbot.device_lock import DeviceLease
from buzzbot.diagnostics import create_diagnostic_report
from buzzbot.display import make_display_profile, matching_scales
from buzzbot.grouping import build_group_iteration_plan, parse_click_sequence, parse_time_to_minutes, validate_hour_min
from buzzbot.ldplayer import (
    adb_debug_enabled,
    bridged_adb_serial_for_index,
    enable_adb_debug,
    find_ldconsole,
    index_from_serial,
    launch_instance,
    list_instances,
    reboot_instance,
    tcp_serial_for_index,
)
from buzzbot.logging_utils import configure_logging, install_exception_logging
from buzzbot.multi_emulator import (
    prepare_worker_config,
    runtime_dir_for_instance,
    worker_launch_command,
    write_worker_command,
)
from buzzbot.matching import (
    TemplateCache,
    detect_alliance_marked_project_target,
    detect_account_details_close_target,
    detect_back_confirmation_cancel_target,
    detect_blank_webview_close_target,
    detect_collective_tutorial_continue_target,
    detect_commander_profile_back_target,
    detect_camped_march_card_targets,
    detect_account_settings_back_target,
    detect_finished_healing_target,
    detect_equipment_report_close_target,
    detect_equipment_report_free_reward_target,
    detect_game_event_overlay_close_target,
    detect_igg_game_login_ok_target,
    detect_igg_id_selection_target,
    detect_login_saved_account_continue_target,
    detect_login_session_expired_ok_target,
    detect_prize_hunt_squad_confirmation_target,
    detect_processing_factory_target,
    detect_research_action_target,
    research_branch_is_selected,
    research_progress_bar_is_active,
    research_radial_menu_is_visible,
    research_tree_progress_is_active,
    research_tree_is_visible,
    detect_radar_card_action_target,
    detect_radar_deployment_prompt_target,
    detect_radar_squad_march_target,
    detect_radar_notification_targets,
    detect_radar_pass_purchase_cancel_target,
    detect_radar_world_action_target,
    detect_settings_close_target,
    detect_settlement_event_panel_collapse_target,
    detect_merchant_shop_feature_target,
    detect_merchant_shop_building_target,
    detect_shop_selection_marker_target,
    detect_shop_radial_action_target,
    detect_mysterious_merchant_absent_ok_target,
    detect_mysterious_merchant_non_gem_offer_targets,
    mysterious_merchant_screen_is_visible,
    settlement_building_catalogue_is_visible,
    detect_truck_occupied_slot_targets,
    detect_truck_active_detail_back_target,
    detect_truck_escort_confirmation_target,
    detect_truck_personal_slot_target,
    detect_truck_ready_collection_target,
    detect_truck_start_dispatch_target,
    detect_lowest_stamina_refill_target,
    detect_march_retreat_target,
    detect_stamina_refill_target,
    healing_auto_fill_is_checked,
    healing_number_editor_is_open,
    healing_selection_is_empty,
    healing_troop_form_is_visible,
    radar_overview_is_visible,
    radar_marker_has_notification,
    radar_card_has_active_countdown,
    stamina_dialog_is_visible,
    truck_alliance_escort_is_visible,
    truck_arrival_reward_is_visible,
    truck_express_overview_is_visible,
    zombie_camp_checkbox_is_checked,
)
from buzzbot.routines import (
    LEGACY_RADAR_TEMPLATE_UIDS,
    PROFILE_NAMESPACE,
    completed_runtime_steps_for_image,
    default_routine_tasks,
    effective_active_marches,
    effective_task_group,
    format_wait_duration,
    gathering_boost_active_until,
    gathering_boost_duration_hours,
    healing_pending_allows_image,
    donation_exhaustion_is_complete,
    healing_repeat_delay,
    image_is_allowed_for_routine,
    is_radar_task_id,
    is_task_effectively_enabled,
    next_due_task,
    next_run_after_finish,
    next_run_after_radar_pass,
    no_action_retry_delay,
    no_available_squad_wait_exceeded,
    normalize_routine_tasks,
    pick_due_task_index,
    prize_hunt_branch_allows_image,
    processing_restart_stall_should_defer,
    radar_marker_requires_notification,
    radar_marker_was_confirmed,
    reset_manual_run_deadlines,
    reset_radar_card_runtime_steps,
    research_queue_match_is_safe,
    reorder_routine_tasks,
    reconcile_march_deadlines,
    resource_search_retry_due,
    setting_requirement_matches,
    training_queue_match_is_safe,
    unavailable_retry_delay,
    routine_home_recovery_due,
    routine_idle_check_timeout,
    routine_idle_screen_abort_due,
    routine_idle_screen_recovery_due,
    routine_missing_followup_is_unavailable,
    routine_requires_settlement,
    routine_march_context_key,
    runtime_step_is_ready,
    select_best_resource_result_level,
    upgrade_radar_runtime_metadata,
    upgrade_mysterious_merchant_metadata,
    upgrade_truck_metadata,
    upgrade_prize_hunt_metadata,
    upgrade_processing_runtime_metadata,
    upgrade_repeatable_claim_metadata,
    upgrade_resource_runtime_metadata,
    upgrade_strict_runtime_metadata,
    zombie_fallback_levels,
)
from buzzbot.remote_control import (
    REMOTE_CREDENTIAL_KEY,
    RemoteControlClient,
    RemoteSettings,
    load_remote_settings,
    save_remote_settings,
)
from buzzbot.report_cloud import (
    ReportCloudSettings,
    load_report_cloud_settings,
    save_report_cloud_settings,
    sync_folder_provider,
    upload_report_to_sync_folder,
)
from buzzbot.state import BotState, compute_runtime_seconds
from buzzbot.storage import move_file_to_trash, save_json_with_backup
from buzzbot.updater import UpdateError, download_and_stage_update, launch_staged_update
from buzzbot.version import APP_VERSION

HEALING_CAMERA_ROUTE_VERSION = 3
HEALING_HOSPITAL_REOPEN_OFFSETS = (
    # A finished-healing portrait is anchored above the hospital.  The first
    # click collects the batch and removes that portrait, so the same pixel is
    # often empty immediately afterwards.  Probe the building underneath the
    # freshly collected marker before moving the camera or replaying a route.
    (0, 0),
    (0, 72),
    (0, 112),
    (0, 152),
    (-48, 112),
    (48, 112),
    (-82, 145),
    (82, 145),
)
HEALING_CAMERA_SCAN_PATTERN = (
    # First expose anything clipped immediately below the fixed HUD.
    ("down", "up")
    # Then force the camera against a reproducible corner. Repeated swipes at
    # the edge are harmless and remove dependence on the previous scan's end.
    + ("left",) * 12
    + ("up",) * 10
    # Cover the complete shelter in five wide rows instead of drifting through
    # the narrow central strip used by the legacy 40-move route.
    + ("right",) * 12
    + ("down",) * 3
    + ("left",) * 12
    + ("down",) * 3
    + ("right",) * 12
    + ("down",) * 3
    + ("left",) * 12
    + ("down",) * 3
    + ("right",) * 12
)

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.environ.get("BUZZBOT_RUNTIME_DIR", APP_DIR)).expanduser().resolve()
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR = APP_DIR / "img"
CONFIG_FILE = RUNTIME_DIR / "config.json"
CONFIG_BACKUP_DIR = RUNTIME_DIR / "backups" / "config"
TRASH_DIR = IMG_DIR / "_trash"
SYSTEM_TEMPLATE_GROUP = "Системные окна"
ACCOUNT_SWITCH_TEMPLATE_GROUP = "Переключение аккаунта"
GAME_PACKAGE = "com.igg.android.doomsdaylastsurvivors"
# Some accounts show the inactivity-reward popup several seconds after the base
# is already visible. Keep the login task alive long enough to close it.
GAME_LOGIN_MINIMUM_SECONDS = 50.0
GAME_LOGIN_STABLE_SECONDS = 12.0
GAME_LOGIN_RESTART_SECONDS = 150.0
GAME_LOGIN_MAX_RESTARTS = 2
GAME_LOGIN_WEBVIEW_GRACE_SECONDS = 60.0
WORLD_SEARCH_TASK_IDS = {"food", "wood", "metal", "oil", "zombie_hunt", "collective_mind"}
# The deployment panel briefly disappears after a march. Ignore only that
# transient false 0/5; every visible positive count remains authoritative.
MARCH_OBSERVER_GRACE_SECONDS = 8.0
MARCH_ZERO_CONFIRMATION_SECONDS = 5.0
MARCH_DECREASE_CONFIRMATION_SECONDS = 2.0
# A normal ordered pass should finish near the fifteen-minute target.  The
# last five minutes of the thirty-minute account budget are reserved for the
# actual profile switch, which is an external WebView flow and may be slower
# than ordinary game actions.
ACCOUNT_PASS_SOFT_SECONDS = 15.0 * 60.0
ACCOUNT_PASS_TASK_HARD_SECONDS = 25.0 * 60.0
ACCOUNT_SWITCH_TIMEOUT_SECONDS = 5.0 * 60.0
# A radar dispatch may legitimately keep the ordered pointer blocked for its
# five-minute safety interval.  Do not start one when it could consume the
# switch reserve at the end of the account pass.
ACCOUNT_PASS_RADAR_RESERVE_SECONDS = 5.5 * 60.0
RESEARCH_UNCONFIRMED_BUDGET_SECONDS = 90.0
FENCE_SURVIVOR_SCAN_PATTERN = (
    # Anchor toward one edge, then sweep the visible shelter rows. The route
    # is intentionally short enough for every account pass, but unlike the old
    # single-frame check it verifies that the survivor marker is not merely
    # outside the current camera position.
    ("left",) * 3
    + ("up",) * 2
    + ("right",) * 4
    + ("down",) * 2
    + ("left",) * 4
)
PROCESSING_FACTORY_SCAN_PATTERN = (
    # Force a reproducible corner, then cover the complete shelter in wide
    # rows.  The previous compact 13-step route only revisited the central
    # strip and missed account-specific refinery placements entirely.
    ("left",) * 12
    + ("up",) * 10
    + ("right",) * 12
    + ("down",) * 3
    + ("left",) * 12
    + ("down",) * 3
    + ("right",) * 12
    + ("down",) * 3
    + ("left",) * 12
    + ("down",) * 3
    + ("right",) * 12
)

logger = configure_logging(RUNTIME_DIR / "bot.log")


class _WindowsPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _WindowsRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def find_window_client_region(window_title):
    """Return the visible Windows client area for an exact window title."""
    title = str(window_title or "").strip()
    if os.name != "nt" or not title:
        return None

    user32 = ctypes.windll.user32
    matches = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def collect_window(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value.strip().casefold() == title.casefold():
            matches.append(hwnd)
        return True

    user32.EnumWindows(collect_window, 0)
    if len(matches) != 1:
        return None

    rect = _WindowsRect()
    if not user32.GetClientRect(matches[0], ctypes.byref(rect)):
        return None
    top_left = _WindowsPoint(rect.left, rect.top)
    bottom_right = _WindowsPoint(rect.right, rect.bottom)
    if not user32.ClientToScreen(matches[0], ctypes.byref(top_left)):
        return None
    if not user32.ClientToScreen(matches[0], ctypes.byref(bottom_right)):
        return None
    width = int(bottom_right.x - top_left.x)
    height = int(bottom_right.y - top_left.y)
    if width < 100 or height < 100:
        return None
    return int(top_left.x), int(top_left.y), width, height

# Пытаемся скрыть окно консоли, если оно есть
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except:
    pass


def enable_windows_high_dpi():
    """Let Tk render text and images at the monitor's native DPI."""
    if os.name != "nt":
        return
    try:
        per_monitor_v2 = ctypes.c_void_p(-4)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(per_monitor_v2):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

import pyautogui
from PIL import Image, ImageGrab, ImageTk

# Попробуем импортировать psutil для мониторинга системы
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil не установлен, мониторинг CPU/RAM отключён")

# Попробуем импортировать GPUtil для мониторинга GPU
try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False
    logger.warning("GPUtil не установлен, мониторинг GPU отключён")


def get_gpu_load_percent():
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None

    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            startupinfo=startupinfo,
            creationflags=creationflags,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    first_line = (result.stdout or "").strip().splitlines()
    if not first_line:
        return None

    try:
        return float(first_line[0].strip())
    except ValueError:
        return None

# Словарь переводов (русский + английский)
LANGUAGES = {
    'ru': {
        'window_title': "BuZzbot",
        'language': "Язык:",
        'status': "Статус",
        'state_stopped': "Остановлен",
        'state_running': "Работает",
        'state_paused': "Пауза",
        'areas_count': "Областей:",
        'clicks': "Кликов:",
        'time': "Время:",
        'control': "Управление",
        'settings': "Настройки",
        'select_area': "Выбрать область",
        'manage_areas': "Управление областями",
        'group_schedule': "Расписание групп",
        'start': "Старт",
        'stop': "Стоп",
        'pause': "Пауза",
        'resume': "Продолжить",
        'minimize_on_start': "Сворачивать при старте",
        'intervals': "Интервалы (сек)",
        'found': "Найдено:",
        'not_found': "Не найдено:",
        'apply': "Применить",
        'system_monitor': "Мониторинг системы",
        'status_line': "Строка состояния",
        'diagnostic_mode': "Диагностика",
        'input_backend': "Источник управления",
        'input_screen': "Экран ПК",
        'input_adb': "ADB (LDPlayer)",
        'adb_serial': "Устройство:",
        'adb_check': "Проверить ADB",
        'adb_repair': "Восстановить ADB",
        'adb_connected': "ADB подключён: {serial}",
        'adb_auto_connected': "ADB найден автоматически: {serial}",
        'adb_disconnected': "ADB недоступен: {serial}",
        'adb_disabled': "ADB выключен для LDPlayer {index}. Нажмите «Восстановить ADB».",
        'adb_multiple': "Запущено несколько LDPlayer. Выберите профиль с правильным номером экземпляра.",
        'adb_no_instance': "Не найден запущенный экземпляр LDPlayer.",
        'adb_repairing': "Включение ADB и перезапуск LDPlayer {index}. Подождите до 90 секунд...",
        'adb_repaired': "Связь восстановлена: {serial}",
        'adb_repair_failed': "Не удалось восстановить ADB для {serial}. Создайте отчёт.",
        'create_report': "Создать отчёт",
        'report_created': "Отчёт создан: {path}",
        'adb_required': "Не удалось подключиться к {serial}. Запустите LDPlayer и включите ADB.",
        'test_search': "Тест поиска",
        'test_search_busy': "Тестовый поиск уже выполняется.",
        'test_search_pause_bot': "Для тестового поиска остановите или поставьте бота на паузу.",
        'test_search_started': "Тестовый поиск запущен.",
        'test_search_summary': "Проверено: {checked} | Найдено: {found}",
        'test_search_no_matches': "Совпадений не найдено.",
        'test_search_more': "... ещё: {count}",
        'routine_tasks': "Рутинные задачи",
        'routine_start': "Старт рутины",
        'routine_settings': "Настроить задачи",
        'routine_clear_selection': "Снять все",
        'routine_help': "Сначала лечение, затем заполнение свободных походов ресурсами по кругу.",
        'routine_name_game_login': "Вход в игру",
        'routine_name_radar_rewards': "Радар: награды",
        'routine_name_radar_quick': "Радар: быстрые",
        'routine_name_radar_marches': "Радар: с отрядом",
        'routine_name_heal': "Лечение войск",
        'routine_name_prize_hunt': "Охота за призом",
        'routine_name_wasteland_exploration': "Исследование пустоши",
        'routine_name_food': "Еда",
        'routine_name_wood': "Дерево",
        'routine_name_metal': "Металл",
        'routine_name_oil': "Нефть",
        'routine_templates': "шаблонов: {count}",
        'routine_marches': "Походы: {active}/{maximum}",
        'routine_max_marches': "Максимум походов:",
        'routine_no_enabled': "Включите хотя бы одну рутинную задачу.",
        'routine_no_templates': "Для включённых задач нет активных шаблонов. Снимите хотя бы один шаблон в настройках задач.",
        'routine_task_started': "Задача: {name} | группа: {group} | шаблонов: {count}",
        'routine_waiting': "Ожидание: следующая задача «{name}» через {wait} | походы {active}/{maximum}",
        'routine_completed': "Задача «{name}» завершена | следующий запуск через {minutes:g} мин",
        'routine_no_action': "Задача «{name}» не выполнена: действий не найдено | повтор через {seconds} сек",
        'routine_recovering_home': "Действия не найдены: один раз возвращаюсь на главный экран",
        'routine_full_marches': "Все походы заняты: {active}/{maximum}",
        'routine_reset_marches': "Сбросить походы",
        'routine_dialog_title': "Настройка рутинных задач",
        'routine_group': "Группа шаблонов",
        'routine_interval': "Повтор (мин)",
        'routine_timeout': "Таймаут (сек)",
        'routine_march_duration': "Поход (мин)",
        'routine_final_template': "Финальный шаблон",
        'routine_uses_march': "Занимает поход",
        'routine_add_template': "Снять шаблон",
        'routine_new_task': "Добавить задачу",
        'routine_task_name': "Название задачи",
        'routine_auto_finish': "Авто по таймауту",
        'routine_config_help': "Для ресурсов выберите финальный шаблон кнопки «Отправить». После его нажатия бот займёт один поход в пределах установленного лимита.",
        'profile_export': "Экспорт обучения",
        'profile_import': "Импорт обучения",
        'profile_saved': "Профиль сохранён: {path}\nШаблонов: {count}",
        'profile_loaded': "Профиль загружен. Добавлено шаблонов: {added}, уже было: {skipped}.\nИсходный экран: {width}×{height}",
        'profile_format_error': "Это не профиль обучения BuZzbot.",
        'ready': "Готов",
        'groups': "Группы",
        'no_groups': "Нет групп. Создайте группу в редакторе области.",
        'active_areas': "Активные области",
        'hotkeys': "Горячие клавиши и аварийная остановка",
        'hotkeys_text': "Enter - подтвердить | ESC - отмена | Delete - удалить | Пробел - вкл/выкл | Ctrl+↑/↓ - переместить\nCtrl+P - пауза/продолжить | Ctrl+0 - аварийная остановка бота",
        'need_work_area': "Для работы необходимо выбрать рабочую область (кнопка «Выбрать»).",
        # Рабочее поле
        'work_area': "Рабочее поле",
        'fullscreen': "Весь экран",
        'monitor': "Монитор",
        'selected_region': "Выбранная область",
        'select': "Выбрать",
        # Масштабирование
        'scaling': "Масштабирование",
        'scaling_enable': "Искать с изменением масштаба",
        'scaling_range': "Диапазон:",
        'scaling_help': "Поиск с масштабом от 0.8 до 1.2",
        # Для AreaManager
        'area_manager_title': "Управление областями",
        'edit': "Редактировать",
        'toggle': "Вкл/Выкл",
        'delete': "Удалить",
        'up': "Вверх",
        'down': "Вниз",
        'refresh': "Обновить",
        'close': "Закрыть",
        'sort': "Сортировать",
        'copy_to_group': "Копировать в группу",
        'total_active': "Всего: {total} | Активных: {active}",
        # Колонки
        'col_num': "№",
        'col_description': "Описание",
        'col_action': "Действие",
        'col_delay': "Задержка",
        'col_confidence': "Точность",
        'col_grayscale': "Grayscale",
        'col_status': "Статус",
        'col_group': "Группа",
        'col_numbers': "Числа для ввода",
        'col_clicks': "Кликов",
        'yes': "Да",
        'no': "Нет",
        'active': "Активна",
        'inactive': "Откл.",
        # Диалоги
        'warning': "Внимание",
        'error': "Ошибка",
        'info': "Информация",
        'success': "Успех",
        'save_area_title': "Сохранение области",
        'enter_description': "Введите описание области:",
        'group_optional': "Группа (необязательно):",
        'save': "Сохранить",
        'cancel': "Отмена",
        'area_saved': "Область '{name}' сохранена!",
        'area_too_small': "Область слишком маленькая!",
        'area_zero': "Область не может быть нулевого размера!",
        'enter_description_error': "Введите описание!",
        'unavailable_during_run': "Нельзя выбирать область во время работы.",
        'stop_bot_first': "Остановите бота перед редактированием!",
        'no_areas': "Список областей пуст. Сначала добавьте области.",
        'select_area_first': "Выберите область из списка",
        'delete_confirm': "Удалить {count} областей и соответствующие файлы с диска?",
        'deleted_files': "Удалено областей: {deleted}",
        'delete_failed': "Не удалось удалить файлы: {failed}",
        'deleted_from_list': "Удалено из списка: {count}",
        'moved_to_trash': "Перемещено в корзину: {count}",
        'settings_saved': "Настройки сохранены",
        'choose_group': "Выберите группу",
        # Редактирование области
        'edit_title': "Редактирование: {name}",
        'action': "Действие:",
        'delay_sec': "Задержка (сек):",
        'accuracy': "Точность:",
        'grayscale_check': "Grayscale (поиск по форме)",
        'active_check': "Область активна",
        'numbers_entry': "Числа для ввода (через запятую):",
        'example': "Пример: 010, 020, 100",
        'resnap': "Переснять область",
        'click_sequence': "Последовательность кликов (dx,dy;...):",
        'click_sequence_help': "Например: 0,0; 50,0; 0,50",
        'save_enter': "Сохранить (Enter)",
        'cancel_esc': "Отмена (ESC)",
        'use_scaling': "Использовать масштабирование",
        'copy_to_group_btn': "Копировать в группу",
        # Для расписания групп
        'group_schedule_title': "Расписание и циклы",
        'group': "Группа",
        'auto': "Авто",
        'on_time': "Вкл",
        'off_time': "Выкл",
        'interval': "Интервал (мин)",
        'duration_minutes': "Длительность (мин)",
        'delete_group': "Удалить группу",
        'rename_group': "Переименовать",
        'schedule_help': "Время в формате ЧЧ:ММ. Оставьте пустым, если не используется.",
        'execution_order': "Порядок и задержки",
        'group_order': "Порядок групп",
        'delay_between_areas': "Задержка между областями",
        'delay_after_group': "Задержка после группы",
        'drag_to_reorder': "Перетащите строки для изменения порядка",
        'cycle_mode': "Циклы аккаунтов",
        'cycle_enable': "Включить циклический режим",
        'cycle_timeout': "Таймаут бездействия (сек)",
        'cycle_groups': "Порядок групп в цикле",
        'cycle_help': "Если в текущей группе нет действий дольше таймаута, бот переключится на следующую группу.",
        'ok': "OK",
        'anti_loop': "Защита от зацикливания",
        'orb_check': "Проверка ключевых точек (ORB)",
    },
    'en': {
        'window_title': "BuZzbot",
        'language': "Language:",
        'status': "Status",
        'state_stopped': "Stopped",
        'state_running': "Running",
        'state_paused': "Paused",
        'areas_count': "Areas:",
        'clicks': "Clicks:",
        'time': "Time:",
        'control': "Control",
        'settings': "Settings",
        'select_area': "Select area",
        'manage_areas': "Manage areas",
        'group_schedule': "Group schedule",
        'start': "Start",
        'stop': "Stop",
        'pause': "Pause",
        'resume': "Resume",
        'minimize_on_start': "Minimize on start",
        'intervals': "Intervals (sec)",
        'found': "Found:",
        'not_found': "Not found:",
        'apply': "Apply",
        'system_monitor': "System monitor",
        'status_line': "Status line",
        'diagnostic_mode': "Diagnostics",
        'input_backend': "Control source",
        'input_screen': "PC screen",
        'input_adb': "ADB (LDPlayer)",
        'adb_serial': "Device:",
        'adb_check': "Check ADB",
        'adb_repair': "Repair ADB",
        'adb_connected': "ADB connected: {serial}",
        'adb_auto_connected': "ADB detected automatically: {serial}",
        'adb_disconnected': "ADB unavailable: {serial}",
        'adb_disabled': "ADB is disabled for LDPlayer {index}. Click 'Repair ADB'.",
        'adb_multiple': "Several LDPlayer instances are running. Select a profile with the correct instance number.",
        'adb_no_instance': "No running LDPlayer instance was found.",
        'adb_repairing': "Enabling ADB and restarting LDPlayer {index}. Wait up to 90 seconds...",
        'adb_repaired': "Connection restored: {serial}",
        'adb_repair_failed': "Could not restore ADB for {serial}. Create a report.",
        'create_report': "Create report",
        'report_created': "Report created: {path}",
        'adb_required': "Could not connect to {serial}. Start LDPlayer and enable ADB.",
        'test_search': "Test search",
        'test_search_busy': "Search test is already running.",
        'test_search_pause_bot': "Pause or stop the bot before running a search test.",
        'test_search_started': "Search test started.",
        'test_search_summary': "Checked: {checked} | Found: {found}",
        'test_search_no_matches': "No matches found.",
        'test_search_more': "... more: {count}",
        'routine_tasks': "Routine tasks",
        'routine_start': "Start routines",
        'routine_settings': "Configure tasks",
        'routine_clear_selection': "Clear selection",
        'routine_help': "Healing runs first, then free marches are filled with resources in rotation.",
        'routine_name_game_login': "Launch game",
        'routine_name_radar_rewards': "Radar: rewards",
        'routine_name_radar_quick': "Radar: quick tasks",
        'routine_name_radar_marches': "Radar: squad tasks",
        'routine_name_heal': "Heal troops",
        'routine_name_prize_hunt': "Prize hunt",
        'routine_name_wasteland_exploration': "Wasteland exploration",
        'routine_name_food': "Food",
        'routine_name_wood': "Wood",
        'routine_name_metal': "Metal",
        'routine_name_oil': "Oil",
        'routine_templates': "templates: {count}",
        'routine_marches': "Marches: {active}/{maximum}",
        'routine_max_marches': "Maximum marches:",
        'routine_no_enabled': "Enable at least one routine task.",
        'routine_no_templates': "Enabled tasks have no active templates. Capture at least one template in task settings.",
        'routine_task_started': "Task: {name} | group: {group} | templates: {count}",
        'routine_waiting': "Waiting: next task '{name}' in {wait} | marches {active}/{maximum}",
        'routine_completed': "Task '{name}' complete | next run in {minutes:g} min",
        'routine_no_action': "Task '{name}' was not completed: no action found | retry in {seconds} sec",
        'routine_recovering_home': "No action found: returning to the main screen once",
        'routine_full_marches': "All marches are busy: {active}/{maximum}",
        'routine_reset_marches': "Reset marches",
        'routine_dialog_title': "Routine task settings",
        'routine_group': "Template group",
        'routine_interval': "Repeat (min)",
        'routine_timeout': "Timeout (sec)",
        'routine_march_duration': "March (min)",
        'routine_final_template': "Final template",
        'routine_uses_march': "Uses a march",
        'routine_add_template': "Capture template",
        'routine_new_task': "Add task",
        'routine_task_name': "Task name",
        'routine_auto_finish': "Automatic by timeout",
        'routine_config_help': "For resource tasks select the final 'Deploy' button template. Clicking it occupies one march within the configured limit.",
        'profile_export': "Export training",
        'profile_import': "Import training",
        'profile_saved': "Profile saved: {path}\nTemplates: {count}",
        'profile_loaded': "Profile loaded. Added templates: {added}, already present: {skipped}.\nSource screen: {width}×{height}",
        'profile_format_error': "This is not a BuZzbot training profile.",
        'ready': "Ready",
        'groups': "Groups",
        'no_groups': "No groups. Create a group in area editor.",
        'active_areas': "Active areas",
        'hotkeys': "Hotkeys and emergency stop",
        'hotkeys_text': "Enter - confirm | ESC - cancel | Delete - delete | Space - toggle | Ctrl+↑/↓ - move\nCtrl+P - pause/resume | Ctrl+0 - emergency stop",
        'need_work_area': "Please select a work area (use 'Select area' button).",
        'work_area': "Work area",
        'fullscreen': "Full screen",
        'monitor': "Monitor",
        'selected_region': "Selected region",
        'select': "Select",
        'scaling': "Scaling",
        'scaling_enable': "Enable scaling search",
        'scaling_range': "Range:",
        'scaling_help': "Search with scale from 0.8 to 1.2",
        'area_manager_title': "Area Manager",
        'edit': "Edit",
        'toggle': "Toggle",
        'delete': "Delete",
        'up': "Up",
        'down': "Down",
        'refresh': "Refresh",
        'close': "Close",
        'sort': "Sort",
        'copy_to_group': "Copy to group",
        'total_active': "Total: {total} | Active: {active}",
        'col_num': "#",
        'col_description': "Description",
        'col_action': "Action",
        'col_delay': "Delay",
        'col_confidence': "Confidence",
        'col_grayscale': "Grayscale",
        'col_status': "Status",
        'col_group': "Group",
        'col_numbers': "Numbers",
        'col_clicks': "Clicks",
        'yes': "Yes",
        'no': "No",
        'active': "Active",
        'inactive': "Inactive",
        'warning': "Warning",
        'error': "Error",
        'info': "Info",
        'success': "Success",
        'save_area_title': "Save area",
        'enter_description': "Enter area description:",
        'group_optional': "Group (optional):",
        'save': "Save",
        'cancel': "Cancel",
        'area_saved': "Area '{name}' saved!",
        'area_too_small': "Area is too small!",
        'area_zero': "Area cannot be zero size!",
        'enter_description_error': "Please enter a description!",
        'unavailable_during_run': "Cannot select area while bot is running.",
        'stop_bot_first': "Stop the bot before editing!",
        'no_areas': "No areas. Add some first.",
        'select_area_first': "Select an area from the list",
        'delete_confirm': "Delete {count} areas and corresponding files?",
        'deleted_files': "Deleted areas: {deleted}",
        'delete_failed': "Failed to delete files: {failed}",
        'deleted_from_list': "Removed from list: {count}",
        'moved_to_trash': "Moved to trash: {count}",
        'settings_saved': "Settings saved",
        'choose_group': "Choose group",
        'edit_title': "Editing: {name}",
        'action': "Action:",
        'delay_sec': "Delay (sec):",
        'accuracy': "Confidence:",
        'grayscale_check': "Grayscale (shape matching)",
        'active_check': "Area active",
        'numbers_entry': "Numbers to type (comma separated):",
        'example': "Example: 010, 020, 100",
        'resnap': "Resnap area",
        'click_sequence': "Click sequence (dx,dy;...):",
        'click_sequence_help': "E.g.: 0,0; 50,0; 0,50",
        'save_enter': "Save (Enter)",
        'cancel_esc': "Cancel (ESC)",
        'use_scaling': "Use scaling",
        'copy_to_group_btn': "Copy to group",
        'group_schedule_title': "Schedule and cycles",
        'group': "Group",
        'auto': "Auto",
        'on_time': "On",
        'off_time': "Off",
        'interval': "Interval (min)",
        'duration_minutes': "Duration (min)",
        'delete_group': "Delete group",
        'rename_group': "Rename",
        'schedule_help': "Time format HH:MM. Leave empty if not used.",
        'execution_order': "Order and delays",
        'group_order': "Group order",
        'delay_between_areas': "Delay between areas",
        'delay_after_group': "Delay after group",
        'drag_to_reorder': "Drag rows to reorder",
        'cycle_mode': "Account cycles",
        'cycle_enable': "Enable cycle mode",
        'cycle_timeout': "Inactivity timeout (sec)",
        'cycle_groups': "Cycle order",
        'cycle_help': "If no actions in current group for timeout, bot switches to next group.",
        'ok': "OK",
        'anti_loop': "Anti-loop protection",
        'orb_check': "Keypoint check (ORB)",
    }
}

class AutoClicker:
    """
    Основной класс бота-автокликера.
    Управляет поиском изображений на экране, выполнением действий, группами и расписанием.
    """
    def __init__(self, root=None):
        self.root = root
        self.app_version = APP_VERSION
        self.is_multi_worker = should_run_multi_worker()
        self.multi_emulator_workers = {}
        self.multi_emulator_command_sequence = 0
        self.multi_emulator_total = 1
        self.device_lease = None
        self.search_images = []
        self.groups = {}
        self.group_schedules = {}
        self.group_execution = {}  # {group: {"order": int, "delay_between": float, "delay_after": float}}

        # Профили циклов аккаунтов
        self.cycle_profiles = {}          # {имя: {"enabled": bool, "timeout": float, "groups": list}}
        self.current_cycle_profile = "default"

        # Для обратной совместимости (временно храним текущие настройки цикла)
        self.cycle_groups = []
        self.cycle_timeout = 5.0
        self.cycle_mode = False

        self.current_cycle_index = 0
        self.last_action_time = time.time()  # время последнего клика (для цикла)

        # Простой диспетчер игровых сценариев.
        self.routine_mode = False
        self.routine_tasks = default_routine_tasks()
        self.routine_max_marches = 5
        self.routine_march_deadlines = []
        self.routine_march_context = ""
        self.routine_deployment_blocked_until = 0.0
        self.routine_confirmed_march_floor = 0
        self.routine_march_observer_grace_until = 0.0
        self.routine_display_active_marches = 0
        self.routine_zero_observation_started_at = 0.0
        self.routine_zero_observation_count = 0
        self.routine_lower_observation_value = None
        self.routine_lower_observation_started_at = 0.0
        self.routine_lower_observation_count = 0
        self.zombie_camp_scan_next_at = 0.0
        self.zombie_camp_blocked_until = 0.0
        self.routine_next_run = {}
        self.current_routine_index = 0
        self.routine_pass_completed = False
        self.current_routine_task_id = None
        self.routine_task_started_at = 0.0
        self.routine_research_budget_started_at = 0.0
        self.routine_last_action_time = time.time()
        self.routine_current_had_action = False
        self.routine_current_action_count = 0
        self.routine_action_counts = {}
        self.routine_completed_steps = set()
        self.routine_last_outcome = {}
        self.routine_action_completes_task = False
        self.routine_action_failure_reason = ""
        self.routine_idle_confirmation_count = 0
        self.routine_home_recovery_attempted = False
        self.routine_login_restart_count = 0
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.routine_resource_retry_count = 0
        self.zombie_level_restore = {}
        self.zombie_level_restore_pending = {}
        self.routine_radar_pending_marker_key = None
        self.routine_radar_confirmed_marker_keys = set()
        self.routine_radar_marker_failure_counts = {}
        self.routine_radar_in_progress_seen = False
        self.routine_radar_return_hold = False
        self.routine_radar_return_active_seen = False
        self.routine_radar_return_observed_peak = 0
        self.routine_radar_dispatched_this_pass = False
        self.routine_forced_task_queue = []
        self.routine_forced_task_active_id = None
        self.routine_forced_task_return_index = None
        self.routine_collective_tutorial_taps = 0
        self.routine_fence_survivor_scan_index = 0
        self.routine_processing_factory_scan_index = 0
        self.routine_processing_factory_dynamic_selected_at = 0.0
        self.routine_processing_factory_dynamic_target = None
        self.routine_processing_factory_radial_attempted = False
        self.routine_processing_factory_recenter_attempted = False
        self.routine_merchant_build_menu_requested_at = 0.0
        self.routine_merchant_pending_target = None
        self.routine_merchant_scan_index = 0
        self.routine_merchant_catalog_scroll_attempts = 0
        self.routine_merchant_force_scan_move = False
        self.routine_merchant_shop_target = None
        self.routine_healing_pan_route = []
        self.routine_healing_replay_index = 0
        self.routine_healing_scan_index = 0
        self.routine_healing_settle_checks = 0
        self.routine_healing_overlay_recovery_done = False
        self.routine_healing_saved_route_rejected = False
        self.routine_healing_search_started = False
        self.routine_healing_recenter_attempted = False
        self.routine_only_task_id = None

        # Profiles let one LDPlayer instance rotate through saved in-game accounts.
        self.account_profiles = default_account_profiles("emulator-5564")
        self.current_account_id = self.account_profiles[0]["id"]
        self.account_rotation_enabled = False
        self.account_session_deadline = 0.0
        self.account_pass_started_at = 0.0
        self.account_pass_account_id = ""
        self.account_switch_failure_count = 0
        self.account_switch_retry_at = 0.0
        self.account_switch_task = None
        self.account_switch_error = ""
        self.account_switch_selected_at = 0.0
        self.account_switch_confirmed = False
        self.account_switch_probe_ready = False
        self.account_switch_auto_login_attempted = False
        self.account_switch_candidates = []
        self.account_switch_last_result = ""
        self.credential_store = CredentialStore()

        # Remote settings are machine-local so copied portable folders receive
        # a distinct device identity and never publish the shared secret.
        self.remote_settings = (
            load_remote_settings()
            if self.root
            else RemoteSettings(device_id="headless", device_name="headless")
        )
        self.remote_control_client = None
        self.remote_access_allowed = True
        self.remote_update_thread = None
        self.remote_update_in_progress = False
        self.report_cloud_settings = load_report_cloud_settings() if self.root else ReportCloudSettings()

        # Источник изображения и ввода: обычный экран Windows или прямой ADB.
        discovered_adb = find_adb_executable()
        self.input_backend = "screen"
        self.adb_path = str(discovered_adb) if discovered_adb else ""
        self.adb_serial = "emulator-5564"
        self.adb_client = None
        self._adb_frame_cache = None
        self._adb_frame_timestamp = 0.0
        self._adb_iteration_frame = None
        self._adb_capture_lock = threading.RLock()
        self._adb_recovery_lock = threading.Lock()
        self._adb_last_recovery_attempt = 0.0
        self.player_width = 1280
        self.player_height = 720
        self.player_name = ""
        self.player_index = None
        self.environment_ready = False

        self.ssim_enabled = True
        self.ssim_threshold = 0.9

        # События для управления потоками
        self.stop_event = threading.Event()
        self.stop_event.set()  # изначально остановлен
        self.schedule_stop_event = threading.Event()
        self._thread = None
        self.schedule_thread = None

        self._region = None
        self.work_area_type = 'fullscreen'
        self.monitors = self.get_monitors()
        self.scale_enabled = False
        self.scale_min = 0.9
        self.scale_max = 1.2
        self.scale_steps = 5
        self.minimize_on_start = True

        self.sleep_found = 2.0
        self.sleep_not_found = 0.05
        self.sleep_error = 0.20

        self.stats = {}
        self.click_count = 0
        self.start_time = None
        self.stop_hotkey_pressed = False
        self.is_running = False
        self.is_paused = False
        self.pause_started_at = None
        self.total_paused_duration = 0.0
        self.state = BotState.STOPPED

        self.lang = 'ru'
        self.diagnostic_enabled = True
        self.status_message = ""
        self.test_search_thread = None

        self.refresh_groups_callback = None
        self._pending_area_group = None
        self._pending_area_description = None
        self._pending_adb_capture = None

        # Блокировка координат
        self.blocked_coords = {}
        self.block_duration = 120
        self.anti_loop_enabled = True

        # ORB
        self.orb_enabled = True
        self.orb_cache = {}
        self.orb_match_threshold = 10
        self.template_cache = TemplateCache()

        # Очередь для GUI
        self.gui_queue = queue.Queue()
        if self.root:
            self.process_gui_queue()

        self.load_config()
        self._refresh_adb_client()
        for task in self.routine_tasks:
            self.groups.setdefault(effective_task_group(task), task.get("enabled", True))
        self.save_config()
        self.update_region_from_work_area()
        self.start_schedule_thread()

    def process_gui_queue(self):
        try:
            while True:
                func, args, kwargs = self.gui_queue.get_nowait()
                func(*args, **kwargs)
        except queue.Empty:
            pass
        finally:
            if self.root:
                self.root.after(100, self.process_gui_queue)

    def _remote_token(self):
        try:
            return self.credential_store.get_password(REMOTE_CREDENTIAL_KEY) or ""
        except CredentialError as exc:
            logger.error("Не удалось прочитать секрет удалённого управления: %s", exc)
            return ""

    def remote_has_token(self):
        try:
            return self.credential_store.has_password(REMOTE_CREDENTIAL_KEY)
        except CredentialError:
            return False

    def start_remote_control(self):
        self.stop_remote_control()
        token = self._remote_token()
        client = RemoteControlClient(
            self.remote_settings,
            token,
            self._remote_status_payload,
            self._queue_remote_command,
            self._queue_remote_access,
            logger=logger,
        )
        self.remote_control_client = client
        self.remote_access_allowed = bool(client.access_allowed)
        if (
            getattr(self, "remote_settings", RemoteSettings()).enabled
            and not getattr(self, "remote_access_allowed", True)
        ):
            self.set_status_message("Доступ отключён администратором", force=True)
        if client.start():
            logger.info(
                "Remote control enabled: device=%s hub=%s",
                self.remote_settings.device_name,
                self.remote_settings.hub_url,
            )
            return True
        return False

    def stop_remote_control(self):
        client = self.remote_control_client
        self.remote_control_client = None
        if client is not None:
            client.stop()

    def configure_remote_control(self, *, enabled, hub_url, device_name, token=""):
        if not self.remote_access_allowed and not enabled:
            raise ValueError("Сначала откройте доступ к устройству из Remote Hub.")
        normalized_url = str(hub_url or "").strip().rstrip("/")
        if enabled and not normalized_url.lower().startswith(("http://", "https://")):
            raise ValueError("Адрес Hub должен начинаться с http:// или https://")
        supplied_token = str(token or "").strip()
        if supplied_token:
            if len(supplied_token) < 24:
                raise ValueError("Секрет Hub должен содержать не менее 24 символов.")
            self.credential_store.set_password(REMOTE_CREDENTIAL_KEY, supplied_token)
        if enabled and not supplied_token and not self.remote_has_token():
            raise ValueError("Введите секрет Remote Hub.")
        self.remote_settings = save_remote_settings(
            RemoteSettings(
                enabled=bool(enabled),
                hub_url=normalized_url,
                device_id=self.remote_settings.device_id,
                device_name=str(device_name or "").strip(),
                heartbeat_seconds=self.remote_settings.heartbeat_seconds,
            )
        )
        if not enabled:
            self.remote_access_allowed = True
        self.start_remote_control()
        return self.get_remote_control_snapshot()

    def get_remote_control_snapshot(self):
        client = self.remote_control_client
        if client is None:
            return {
                "configured": False,
                "connected": False,
                "last_error": "",
                "last_checkin_at": 0.0,
                "access_allowed": bool(self.remote_access_allowed),
                "device_id": self.remote_settings.device_id,
                "device_name": self.remote_settings.device_name,
                "hub_url": self.remote_settings.hub_url,
            }
        return client.snapshot()

    def get_remote_control_summary(self):
        if not self.remote_settings.enabled:
            return "Удалённо: выключено"
        snapshot = self.get_remote_control_snapshot()
        if not snapshot.get("access_allowed", True):
            return "Удалённо: ДОСТУП ЗАКРЫТ"
        if snapshot.get("connected"):
            return f"Удалённо: онлайн · {self.remote_settings.device_name}"
        error_message = str(snapshot.get("last_error") or "ожидание Hub")
        return f"Удалённо: нет связи · {error_message}"

    def check_remote_connection(self):
        client = self.remote_control_client
        if client is None or not client.configured:
            raise ValueError("Удалённое управление не настроено.")
        client.checkin_once()
        return client.snapshot()

    def _remote_status_payload(self):
        current_account = self.get_current_account()
        current_task = self.get_routine_task(self.current_routine_task_id)
        return {
            "app_version": APP_VERSION,
            "state": "blocked" if not self.remote_access_allowed else self.state.value,
            "status": self.status_message,
            "account": current_account.get("name", "") if current_account else "",
            "current_task": current_task.get("name", "") if current_task else "",
            "adb_serial": self.adb_serial,
        }

    def _queue_remote_command(self, action):
        if self.root:
            self.gui_queue.put((self._execute_remote_command, (action,), {}))
        else:
            self._execute_remote_command(action)
        return True

    def _queue_remote_access(self, allowed):
        self.remote_access_allowed = bool(allowed)
        action = "allow" if allowed else "deny"
        if self.root:
            self.gui_queue.put((self._execute_remote_command, (action,), {}))
        else:
            self._execute_remote_command(action)

    def _execute_remote_command(self, action):
        action = str(action or "").strip().lower()
        logger.info("Remote command received: %s", action)
        if action == "deny":
            self.remote_access_allowed = False
            if self.is_running:
                self.stop()
            self.set_status_message("Доступ отключён администратором", force=True)
            return True
        if action == "allow":
            self.remote_access_allowed = True
            self.set_status_message("Удалённый доступ разрешён", force=True)
            return True
        if action == "stop":
            if self.is_running:
                self.stop()
            return True
        if action == "update":
            return self.start_update()
        if not self.remote_access_allowed:
            logger.warning("Remote command ignored while access is denied: %s", action)
            return True
        if action == "start":
            if not self.is_running:
                self.start_routines()
            return True
        if action == "pause":
            if self.is_running and not self.is_paused:
                self.pause()
            return True
        if action == "resume":
            if self.is_paused:
                self.resume()
            return True
        logger.warning("Unknown remote command: %s", action)
        return False

    def start_update(self):
        if self.remote_update_thread is not None and self.remote_update_thread.is_alive():
            return True
        self.remote_update_in_progress = True
        self.set_status_message("Обновление: проверяю новый релиз", force=True)

        def worker():
            try:
                staged = download_and_stage_update(APP_VERSION)
                if staged is None:
                    self.set_status_message(
                        f"Установлена актуальная версия {APP_VERSION}",
                        force=True,
                    )
                    return
                self.set_status_message(
                    f"Обновление {staged.version} загружено; установка",
                    force=True,
                )
                if self.root:
                    self.gui_queue.put((self._install_update, (staged,), {}))
                else:
                    raise UpdateError("Для установки требуется запущенный интерфейс BuZzbot.")
            except Exception as exc:
                logger.exception("Update failed")
                self.set_status_message(f"Ошибка обновления: {exc}", force=True)
            finally:
                self.remote_update_in_progress = False

        self.remote_update_thread = threading.Thread(
            target=worker,
            name="BuZzbotUpdate",
            daemon=True,
        )
        self.remote_update_thread.start()
        return True

    def start_remote_update(self):
        return self.start_update()

    def _install_update(self, staged):
        try:
            launch_staged_update(staged, APP_DIR)
        except UpdateError as exc:
            self.set_status_message(f"Ошибка установки обновления: {exc}", force=True)
            return False
        if self.is_running:
            self.stop()
        self.stop_schedule_thread()
        self.stop_remote_control()
        self.set_status_message("Обновление подготовлено; перезапускаю BuZzbot", force=True)
        self.root.after(500, self.root.destroy)
        return True

    def configure_report_cloud(self, *, enabled, sync_folder, device_name):
        folder = str(sync_folder or "").strip()
        if enabled:
            if not folder:
                raise ValueError("Выберите папку Yandex Disk, Google Drive или OneDrive.")
            folder_path = Path(folder).expanduser()
            if not folder_path.is_dir():
                raise FileNotFoundError(f"Облачная папка недоступна: {folder}")
            try:
                folder_path.resolve().relative_to(APP_DIR.resolve())
            except (OSError, ValueError):
                pass
            else:
                raise ValueError(
                    "Выбрана локальная папка BuZzbot. Выберите папку внутри "
                    "Yandex Disk, Google Drive или OneDrive."
                )
        self.report_cloud_settings = save_report_cloud_settings(
            ReportCloudSettings(
                enabled=bool(enabled),
                sync_folder=folder,
                device_name=str(device_name or "").strip(),
            )
        )
        return self.report_cloud_settings

    def create_and_upload_diagnostic_report(self):
        report_path = self.create_diagnostic_report()
        if not self.report_cloud_settings.configured:
            return report_path, False
        provider = sync_folder_provider(self.report_cloud_settings.sync_folder)
        try:
            uploaded_path = upload_report_to_sync_folder(
                report_path,
                self.report_cloud_settings,
            )
        except Exception:
            logger.exception("Не удалось поместить диагностический отчёт в облачную папку")
            self.set_status_message(
                f"Отчёт сохранён локально: {report_path}",
                force=True,
            )
            raise
        if provider:
            logger.info(
                "Диагностический отчёт помещён в папку синхронизации %s: %s",
                provider,
                uploaded_path,
            )
            self.set_status_message(
                f"Отчёт передан в {provider}: {uploaded_path.name}",
                force=True,
            )
        else:
            logger.warning(
                "Папка отчётов не распознана как облачная; ZIP скопирован локально: %s",
                uploaded_path,
            )
            self.set_status_message(
                f"Отчёт скопирован в указанную папку: {uploaded_path.name}",
                force=True,
            )
        return uploaded_path, True

    def _set_state(self, new_state):
        self.state = new_state
        self.is_running = new_state != BotState.STOPPED
        self.is_paused = new_state == BotState.PAUSED

    @property
    def uses_adb(self):
        return self.input_backend == "adb"

    def _refresh_adb_client(self):
        self.adb_client = AdbClient(self.adb_path or None, self.adb_serial)
        if self.adb_client.adb_path:
            self.adb_path = str(self.adb_client.adb_path)
        self._invalidate_capture()

    def _invalidate_capture(self):
        with self._adb_capture_lock:
            self._adb_frame_cache = None
            self._adb_frame_timestamp = 0.0
            self._adb_iteration_frame = None

    def get_display_profile(self):
        return make_display_profile(self.player_width, self.player_height)

    def _screen_game_region(self):
        """Resolve the game client area so screen-mode input follows LDPlayer."""
        configured_region = getattr(self, "_region", None)
        if configured_region is not None:
            return configured_region
        current_account = self.get_current_account()
        candidate_titles = [
            (current_account or {}).get("name", ""),
            getattr(self, "player_name", ""),
        ]
        for title in dict.fromkeys(str(item).strip() for item in candidate_titles if item):
            region = find_window_client_region(title)
            if region is not None:
                left, top, width, height = region
                expected_width = int(getattr(self, "player_width", 1280) or 1280)
                expected_height = int(getattr(self, "player_height", 720) or 720)
                if (
                    width >= expected_width
                    and height >= expected_height
                    and width - expected_width <= 200
                    and height - expected_height <= 200
                ):
                    # LDPlayer draws its custom title bar inside the Win32
                    # client area. The Android surface is centred horizontally
                    # and aligned to the bottom of that client area.
                    left += (width - expected_width) // 2
                    top += height - expected_height
                    return left, top, expected_width, expected_height
                return region
        return None

    def _screen_normalized_point(self, x_ratio, y_ratio):
        region = self._screen_game_region()
        if region is not None:
            left, top, width, height = region
            return (
                int(round(left + width * float(x_ratio))),
                int(round(top + height * float(y_ratio))),
            )
        screen = pyautogui.size()
        return (
            int(round(screen.width * float(x_ratio))),
            int(round(screen.height * float(y_ratio))),
        )

    def _apply_player_resolution(self, width, height, persist=False):
        profile = make_display_profile(width, height)
        changed = (profile.width, profile.height) != (self.player_width, self.player_height)
        self.player_width = profile.width
        self.player_height = profile.height
        if changed:
            logger.info(
                "Player resolution detected: %sx%s; template scale %s",
                profile.width,
                profile.height,
                profile.percent_label,
            )
            if persist:
                self.save_config()
        return profile

    def get_environment_summary(self):
        profile = self.get_display_profile()
        if not self.uses_adb:
            state = "готово" if self.environment_ready else "не готово"
            return (
                f"Экранный режим | шаблоны {profile.width}x{profile.height} | {state}"
            )
        player = f"LDPlayer {self.player_index} {self.player_name}" if self.player_index is not None else "LDPlayer"
        state = "\u0433\u043e\u0442\u043e\u0432\u043e" if self.environment_ready else "\u043d\u0435\u0442 \u0441\u0432\u044f\u0437\u0438"
        return (
            f"ADB: {self.adb_serial} | {player} | "
            f"{profile.width}x{profile.height} | \u043f\u043e\u0434\u0433\u043e\u043d\u043a\u0430 {profile.percent_label} | {state}"
        )

    def check_runtime_environment(self, notify=True, wait_seconds=0.0):
        self.environment_ready = False
        self.player_index = None
        self.player_name = ""
        if not self.uses_adb:
            self.environment_ready = True
            summary = self.get_environment_summary()
            self.set_status_message(summary, force=True)
            if notify:
                self._show_notification('success', 'info', message=summary)
            return True
        deadline = time.monotonic() + max(0.0, float(wait_seconds))
        connected = self.check_adb_connection(notify=False)
        while not connected and time.monotonic() < deadline:
            time.sleep(min(2.0, max(0.1, deadline - time.monotonic())))
            connected = self.check_adb_connection(notify=False)
        if not connected:
            if notify:
                self._show_notification('error', 'adb_required', serial=self.adb_serial)
            return False
        try:
            frame = self._capture_adb_frame(force=True)
        except (AdbError, OSError, ValueError) as exc:
            logger.warning("ADB screenshot check failed for %s: %s", self.adb_serial, exc)
            self.set_status_message(
                f"ADB: {self.adb_serial} | \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u044d\u043a\u0440\u0430\u043d",
                force=True,
            )
            return False

        profile = self._apply_player_resolution(frame.shape[1], frame.shape[0], persist=True)
        _ldconsole, instances = self._ldplayer_instances()
        connected_index = index_from_serial(self.adb_serial)
        instance = next(
            (
                item for item in instances
                if item.adb_serial == self.adb_serial or item.index == connected_index
            ),
            None,
        )
        if instance:
            self.player_index = instance.index
            self.player_name = instance.name
            if (instance.width, instance.height) != (profile.width, profile.height):
                logger.info(
                    "LDPlayer configured resolution %sx%s; live game frame %sx%s",
                    instance.width,
                    instance.height,
                    profile.width,
                    profile.height,
                )
        self.environment_ready = True
        self.save_config()
        summary = self.get_environment_summary()
        self.set_status_message(summary, force=True)
        if notify:
            self._show_notification('success', 'info', message=summary)
        return True

    def set_input_backend(self, backend, serial=None, adb_path=None):
        self.input_backend = "adb" if backend == "adb" else "screen"
        if serial is not None and str(serial).strip():
            self.adb_serial = str(serial).strip()
        if adb_path is not None:
            self.adb_path = str(adb_path).strip()
        self._refresh_adb_client()
        self._ensure_routine_march_context()
        self.save_config()

    def _ldplayer_instances(self):
        ldconsole = find_ldconsole(self.adb_path)
        if not ldconsole:
            return None, []
        try:
            return ldconsole, list_instances(ldconsole)
        except Exception as exc:
            logger.warning("Не удалось получить список LDPlayer: %s", exc)
            return ldconsole, []

    def _adopt_adb_serial(self, serial, instance_index=None):
        serial = str(serial or "").strip()
        if not serial:
            return False
        changed = serial != self.adb_serial
        self.adb_serial = serial
        profile = self.get_current_account()
        if profile:
            changed = changed or profile.get("adb_serial") != serial
            profile["adb_serial"] = serial
            if instance_index is None:
                instance_index = index_from_serial(serial)
            if instance_index is not None:
                changed = changed or int(profile.get("ldplayer_index", -1)) != int(instance_index)
                profile["ldplayer_index"] = int(instance_index)
        self._refresh_adb_client()
        if changed:
            logger.info("Профиль автоматически привязан к ADB %s", serial)
            self._ensure_routine_march_context()
            self.save_config()
            if self.root:
                self.gui_queue.put((self.root.event_generate, ("<<AccountChanged>>",), {"when": "tail"}))
        return True

    def _auto_detect_adb_connection(self):
        probe = AdbClient(self.adb_path or None, "")
        try:
            devices = probe.list_devices()
        except AdbError as exc:
            logger.warning("Не удалось получить список ADB-устройств: %s", exc)
            return False
        if self.adb_serial in devices:
            return True

        target = self.get_adb_repair_target()
        if target:
            tcp_serial = tcp_serial_for_index(target.index)
            try:
                probe.connect(tcp_serial)
                devices = probe.list_devices()
            except AdbError as exc:
                logger.debug("TCP ADB %s пока недоступен: %s", tcp_serial, exc)
            if tcp_serial in devices:
                self._adopt_adb_serial(tcp_serial, target.index)
                return True

            bridged_serial = bridged_adb_serial_for_index(target.index)
            if bridged_serial:
                try:
                    probe.connect(bridged_serial)
                    devices = probe.list_devices()
                except AdbError as exc:
                    logger.debug("Bridged ADB %s пока недоступен: %s", bridged_serial, exc)
                if bridged_serial in devices:
                    self._adopt_adb_serial(bridged_serial, target.index)
                    return True

        _ldconsole, instances = self._ldplayer_instances()
        current = self.get_current_account()
        preferred_index = int(current.get("ldplayer_index", -1)) if current else -1
        preferred = next(
            (item for item in instances if item.index == preferred_index and item.adb_serial in devices),
            None,
        )
        if preferred:
            self._adopt_adb_serial(preferred.adb_serial, preferred.index)
            return True
        # A configured profile must never jump to another running emulator just
        # because it is currently the only ADB device that answered.
        if target or preferred_index >= 0:
            return False
        if len(devices) == 1:
            serial = devices[0]
            self._adopt_adb_serial(serial, index_from_serial(serial))
            return True
        return False

    def get_adb_repair_target(self):
        _ldconsole, instances = self._ldplayer_instances()
        running = [item for item in instances if item.running]
        current = self.get_current_account()
        preferred_index = int(current.get("ldplayer_index", -1)) if current else -1
        preferred = next((item for item in running if item.index == preferred_index), None)
        if preferred:
            return preferred
        if len(running) == 1:
            return running[0]
        return None

    def check_adb_connection(self, notify=True):
        self._refresh_adb_client()
        connected = self.adb_client.is_responsive()
        auto_detected = False
        if not connected:
            auto_detected = self._auto_detect_adb_connection()
            connected = auto_detected and self.adb_client.is_responsive()
        if connected:
            key = 'adb_auto_connected' if auto_detected else 'adb_connected'
            message = self.tr(key, serial=self.adb_serial)
        else:
            target = self.get_adb_repair_target()
            ldconsole, instances = self._ldplayer_instances()
            running = [item for item in instances if item.running]
            adb_enabled = adb_debug_enabled(ldconsole, target.index) if ldconsole and target else None
            if target and adb_enabled is False:
                key = 'adb_disabled'
                message = self.tr(key, index=target.index)
            elif len(running) > 1:
                key = 'adb_multiple'
                message = self.tr(key)
            elif not running:
                key = 'adb_no_instance'
                message = self.tr(key)
            else:
                key = 'adb_disconnected'
                message = self.tr(key, serial=self.adb_serial)
        logger.info("Проверка ADB: %s", message)
        self.set_status_message(message, force=True)
        if notify:
            kwargs = {"serial": self.adb_serial, "index": getattr(self.get_adb_repair_target(), "index", "?")}
            self._show_notification('success' if connected else 'error', key, **kwargs)
        return connected

    def repair_adb_connection(self, instance_index=None):
        if self._auto_detect_adb_connection() and self.adb_client.is_responsive():
            self.set_status_message(self.tr('adb_repaired', serial=self.adb_serial), force=True)
            return True

        ldconsole, instances = self._ldplayer_instances()
        running = [item for item in instances if item.running]
        target = next((item for item in instances if item.index == instance_index), None)
        if target is None:
            target = self.get_adb_repair_target()
        if target is None:
            current = self.get_current_account()
            preferred_index = int(current.get("ldplayer_index", -1)) if current else -1
            target = next((item for item in instances if item.index == preferred_index), None)
        if not ldconsole or not target:
            key = 'adb_multiple' if len(running) > 1 else 'adb_no_instance'
            self.set_status_message(self.tr(key), force=True)
            return False

        self.set_status_message(self.tr('adb_repairing', index=target.index), force=True)
        logger.info("Восстановление ADB для LDPlayer %s (%s)", target.index, target.name)
        try:
            changed = enable_adb_debug(ldconsole, target.index)
            logger.info("Настройка ADB LDPlayer изменена: %s", changed)
            AdbClient(self.adb_path or None, "").restart_server()
            if target.running:
                reboot_instance(ldconsole, target.index)
            else:
                launch_instance(ldconsole, target.index)
        except Exception as exc:
            logger.exception("Не удалось включить ADB для LDPlayer %s", target.index)
            self.set_status_message(f"Ошибка восстановления ADB: {exc}", force=True)
            return False

        client = AdbClient(self.adb_path or None, target.adb_serial)
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            if client.is_responsive():
                self._adopt_adb_serial(target.adb_serial, target.index)
                message = self.tr('adb_repaired', serial=target.adb_serial)
                logger.info(message)
                self.set_status_message(message, force=True)
                return True
            if self._auto_detect_adb_connection() and self.adb_client.is_responsive():
                message = self.tr('adb_repaired', serial=self.adb_serial)
                logger.info(message)
                self.set_status_message(message, force=True)
                return True
            time.sleep(2.0)
        message = self.tr('adb_repair_failed', serial=target.adb_serial)
        logger.error(message)
        self.set_status_message(message, force=True)
        return False

    def _recover_runtime_adb_connection(self):
        now = time.monotonic()
        if now - self._adb_last_recovery_attempt < 20.0:
            return False
        if not self._adb_recovery_lock.acquire(blocking=False):
            return False
        try:
            self._adb_last_recovery_attempt = now
            instance_index = index_from_serial(self.adb_serial)
            current = self.get_current_account()
            if current and int(current.get("ldplayer_index", -1)) >= 0:
                instance_index = int(current["ldplayer_index"])
            logger.warning(
                "ADB connection lost during execution; recovering LDPlayer %s",
                instance_index,
            )
            self.set_status_message("Связь с LDPlayer потеряна. Восстанавливаю...", force=True)
            if not self.repair_adb_connection(instance_index=instance_index):
                return False
            self._refresh_adb_client()
            self.adb_client.launch_package(GAME_PACKAGE)
            self._interruptible_sleep(8.0)
            self.blocked_coords.clear()
            self.routine_completed_steps = set()
            self.routine_current_had_action = False
            self.routine_last_action_time = time.time()
            logger.info("Runtime ADB recovery completed for %s", self.adb_serial)
            self.set_status_message("Связь восстановлена. Продолжаю текущую задачу", force=True)
            return True
        except Exception:
            logger.exception("Runtime ADB recovery failed")
            return False
        finally:
            self._adb_recovery_lock.release()

    def create_diagnostic_report(self):
        for handler in logger.handlers:
            try:
                handler.flush()
            except Exception:
                pass
        ldconsole = find_ldconsole(self.adb_path)
        frame_age = None
        if self._adb_frame_cache is not None and self._adb_frame_timestamp > 0:
            frame_age = max(0.0, time.monotonic() - self._adb_frame_timestamp)
        runtime_state = {
            "bot_state": self.state.value,
            "input_backend": self.input_backend,
            "adb_serial": self.adb_serial,
            "adb_path": self.adb_path,
            "player_resolution": f"{self.player_width}x{self.player_height}",
            "resolution_scale": self.get_display_profile().percent_label,
            "adb_cached_frame": self._adb_frame_cache is not None,
            "adb_cached_frame_age_seconds": round(frame_age, 3) if frame_age is not None else None,
            "templates": len(self.search_images),
            "routine_tasks": len(self.routine_tasks),
            "active_marches": self.get_active_marches(),
            "maximum_marches": self.routine_max_marches,
            "status": self.status_message,
            "account_profiles": len(self.account_profiles),
            "current_task": self.current_routine_task_id,
            "standalone_task": self.routine_only_task_id,
            "completed_steps": sorted(self.routine_completed_steps),
            "current_action_count": self.routine_current_action_count,
            "enabled_tasks": [
                task.get("id") for task in self.routine_tasks
                if is_task_effectively_enabled(task)
            ],
        }
        log_paths = [
            getattr(handler, "baseFilename", None)
            for handler in logger.handlers
            if getattr(handler, "baseFilename", None)
        ]
        screenshot_png = self._cached_diagnostic_screenshot_png()
        logger.info(
            "Создание диагностического отчёта из кеша; живые ADB-команды отключены, снимок=%s",
            "добавлен" if screenshot_png else "пропущен",
        )
        report_path = create_diagnostic_report(
            APP_DIR,
            app_version=APP_VERSION,
            config_path=CONFIG_FILE,
            runtime_state=runtime_state,
            # A live `adb devices` call can contend with the capture loop and
            # wedge LDPlayer's ADB server. Runtime state and logs already carry
            # the connection details needed for diagnostics.
            adb_path=None,
            adb_devices_text=(
                "Живая проверка пропущена, чтобы не прерывать работу ADB. "
                f"Настроенный адрес: {self.adb_serial}"
            ),
            ldconsole_path=ldconsole,
            log_paths=log_paths,
            screenshot_png=screenshot_png,
        )
        logger.info("Диагностический отчёт создан: %s", report_path)
        self.set_status_message(self.tr('report_created', path=report_path), force=True)
        return report_path

    def _cached_diagnostic_screenshot_png(self):
        if not self._adb_capture_lock.acquire(blocking=False):
            return None
        try:
            if self._adb_frame_cache is None:
                return None
            frame = self._adb_frame_cache.copy()
        finally:
            self._adb_capture_lock.release()

        try:
            encoded, payload = cv2.imencode(
                ".png",
                frame,
                [cv2.IMWRITE_PNG_COMPRESSION, 1],
            )
        except Exception:
            logger.exception("Не удалось закодировать кешированный снимок для отчёта")
            return None
        if not encoded:
            return None
        return payload.tobytes()

    def _capture_adb_frame(self, force=False):
        now = time.monotonic()
        with self._adb_capture_lock:
            if not force and self._adb_iteration_frame is not None:
                return self._adb_iteration_frame
            if (
                not force
                and self._adb_frame_cache is not None
                and now - self._adb_frame_timestamp <= 0.15
            ):
                return self._adb_frame_cache
            if self.adb_client is None:
                self._refresh_adb_client()
            try:
                frame = self.adb_client.screenshot_bgr()
            except AdbError:
                if not self.is_running or not self._recover_runtime_adb_connection():
                    raise
                frame = self.adb_client.screenshot_bgr()
            self._adb_frame_cache = frame
            self._adb_frame_timestamp = time.monotonic()
            self._apply_player_resolution(frame.shape[1], frame.shape[0], persist=False)
            return frame

    def _capture_screen_bgr(self, region=None, force=False):
        if self.uses_adb:
            frame = self._capture_adb_frame(force=force)
            effective_region = region
            if not effective_region:
                return frame, (0, 0)
            x, y, width, height = map(int, effective_region)
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(frame.shape[1], x + max(0, width))
            y2 = min(frame.shape[0], y + max(0, height))
            if x2 <= x1 or y2 <= y1:
                raise AdbError("Выбранная область находится вне экрана Android.")
            return frame[y1:y2, x1:x2], (x1, y1)

        effective_region = region if region is not None else self._screen_game_region()
        screenshot = pyautogui.screenshot(region=effective_region)
        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        return (
            frame,
            (int(effective_region[0]), int(effective_region[1]))
            if effective_region
            else (0, 0),
        )

    def _capture_bbox_bgr(self, bbox):
        frame, _ = self._capture_screen_bgr(region=bbox)
        return frame

    def _is_main_screen_visible(self):
        markers = [
            image for image in self.search_images
            if image.get("home_screen_marker") and image.get("enabled", True)
        ]
        if not markers:
            markers = [
                image for image in self.search_images
                if image.get("description") == "Открыть альянс" and image.get("enabled", True)
            ]
        for marker in markers:
            try:
                location, bbox, _score = self._locate_image(marker)
            except Exception:
                logger.exception("Ошибка проверки главного экрана")
                continue
            if location and bbox:
                return True
        return False

    def _is_settlement_screen_visible(self):
        markers = [
            image for image in self.search_images
            if image.get("settlement_screen_marker") and image.get("enabled", True)
        ]
        for marker in markers:
            try:
                location, bbox, _score = self._locate_image(marker)
            except Exception:
                logger.exception("Ошибка проверки экрана убежища")
                continue
            if location and bbox:
                return True
        return False

    def _switch_to_settlement_screen(self):
        if self._is_settlement_screen_visible():
            return True
        if not self._is_main_screen_visible():
            return False

        frame, _origin = self._capture_screen_bgr(force=True)
        target_x = int(round(frame.shape[1] * 65 / 1280))
        target_y = int(round(frame.shape[0] * 655 / 720))
        self.set_status_message("Переход с карты мира в убежище", force=True)
        try:
            if self.uses_adb:
                self.adb_client.tap(target_x, target_y)
            else:
                pyautogui.click(target_x, target_y)
        except Exception:
            logger.exception("Не удалось перейти с карты мира в убежище")
            return False
        self._invalidate_capture()

        for _attempt in range(4):
            self._interruptible_sleep(0.8)
            if self._is_settlement_screen_visible():
                logger.info("Переход с карты мира в убежище подтверждён")
                return True

        # A full-screen chat can leave base markers visible around its edges,
        # so the screen looks like the world map while the region button is
        # actually covered. Close that overlay once and re-check before giving
        # up; this is safer than repeating a blind region-button tap.
        if self._is_main_screen_visible():
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Не удалось закрыть перекрывающее окно перед убежищем")
            else:
                self._invalidate_capture()
                self._interruptible_sleep(0.8)
                try:
                    frame, origin = self._capture_screen_bgr(force=True)
                    cancel_target = detect_back_confirmation_cancel_target(frame)
                except Exception:
                    cancel_target = None
                if cancel_target is not None:
                    cancel_x, cancel_y = cancel_target
                    if self.uses_adb:
                        self.adb_client.tap(cancel_x, cancel_y)
                    else:
                        pyautogui.click(origin[0] + cancel_x, origin[1] + cancel_y)
                    self._invalidate_capture()
                    logger.warning("Отменено окно выхода после попытки закрыть перекрытие")
                    return False
                if self._is_settlement_screen_visible():
                    logger.info("Перекрывающее окно закрыто; убежище подтверждено")
                    return True
        logger.warning("Переход с карты мира в убежище не подтверждён")
        return False

    def _world_search_panel_visible(self):
        task = self.get_routine_task(self.current_routine_task_id)
        if task is None:
            return False
        panel_steps = {"resource_icon", "search_button", "zombie_icon", "leader_icon"}
        for image in self.get_routine_templates(task, active_only=True):
            if str(image.get("runtime_step") or "") not in panel_steps:
                continue
            try:
                location, bbox, _confidence = self._locate_image(image)
                if location is None or bbox is None:
                    continue
                is_valid, _reason = self._validate_detected_match(image, bbox)
                if is_valid:
                    return True
            except Exception:
                logger.exception(
                    "World search panel confirmation failed for %s",
                    image.get("description"),
                )
        return False

    def _prepare_world_search_screen(self):
        """Open the world-search panel without relying on a base-layout template."""
        if not self._is_main_screen_visible() and not self._return_to_main_screen(max_back_steps=4):
            return False

        display = self.get_display_profile() if self.uses_adb else make_display_profile(1280, 720)
        region_x = int(round(65 * display.scale_x))
        region_y = int(round(655 * display.scale_y))
        search_x = int(round(43 * display.scale_x))
        search_y = int(round(447 * display.scale_y))

        for attempt in range(1, 4):
            if self._world_search_panel_visible():
                self.set_status_message("Карта мира: поиск открыт", force=True)
                return True
            try:
                if self._is_settlement_screen_visible():
                    if self.uses_adb:
                        self.adb_client.tap(region_x, region_y)
                    else:
                        pyautogui.click(region_x, region_y)
                    self._invalidate_capture()
                    self._interruptible_sleep(1.5)

                if self.uses_adb:
                    self.adb_client.tap(search_x, search_y)
                else:
                    pyautogui.click(search_x, search_y)
                self._invalidate_capture()
                for _check in range(4):
                    self._interruptible_sleep(0.5)
                    if self._world_search_panel_visible():
                        self.set_status_message("Карта мира: поиск открыт", force=True)
                        logger.info(
                            "World search confirmed for task %s on attempt %s",
                            self.current_routine_task_id,
                            attempt,
                        )
                        return True
            except Exception:
                logger.exception("Не удалось открыть поиск на карте мира")

            logger.warning(
                "World search was not confirmed for task %s on attempt %s/3",
                self.current_routine_task_id,
                attempt,
            )
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("World search recovery back action failed")
            self._invalidate_capture()
            self._interruptible_sleep(1.0)
            if not self._is_main_screen_visible():
                self._return_to_main_screen(max_back_steps=3)

        self.set_status_message("Не удалось подтвердить панель поиска", force=True)
        return False

    def _return_to_main_screen(self, max_back_steps=5, require_settlement=False):
        for step in range(max(1, int(max_back_steps)) + 1):
            if self.uses_adb:
                try:
                    foreground_package = self.adb_client.current_foreground_package()
                except Exception:
                    foreground_package = None
                if foreground_package and foreground_package != GAME_PACKAGE:
                    logger.warning(
                        "Stopped main-screen recovery after Doomsday left foreground: %s",
                        foreground_package,
                    )
                    return False
            try:
                frame, origin = self._capture_screen_bgr(force=True)
                cancel_target = detect_back_confirmation_cancel_target(frame)
            except Exception:
                cancel_target = None
            if cancel_target is not None:
                cancel_x, cancel_y = cancel_target
                logger.warning("Отменяю окно выхода из игры во время возврата на главный экран")
                if self.uses_adb:
                    self.adb_client.tap(cancel_x, cancel_y)
                else:
                    pyautogui.click(origin[0] + cancel_x, origin[1] + cancel_y)
                self._invalidate_capture()
                self._interruptible_sleep(0.8)
                continue
            if self._is_main_screen_visible():
                if require_settlement and not self._is_settlement_screen_visible():
                    return self._switch_to_settlement_screen()
                logger.info("Возврат на главный экран подтверждён после %s шагов", step)
                self.set_status_message("Главный экран найден, переход к следующей задаче", force=True)
                return True
            if step >= max_back_steps or self.stop_event.is_set():
                break
            self.set_status_message(
                f"Возврат на главный экран: шаг {step + 1}/{max_back_steps}",
                force=True,
            )
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Не удалось выполнить возврат на главный экран")
                break
            self._invalidate_capture()
            self._interruptible_sleep(0.8)
        logger.warning("Главный экран не подтверждён после завершения задачи")
        return False

    def _try_global_login_connection_recovery(self, task):
        """Recover the one-button in-game login/network error without looping Back."""
        if not self.uses_adb or not task or task.get("id") == "game_login":
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Login connection recovery could not capture the screen")
            return False
        # Two-button Android Back confirmation is handled by normal screen
        # recovery.  Only the distinct single wide OK dialog may restart login.
        if detect_back_confirmation_cancel_target(frame) is not None:
            return False
        target = detect_login_session_expired_ok_target(frame)
        if target is None:
            return False

        interrupted_index = int(self.current_routine_index or 0)
        login_index = next(
            (
                index
                for index, candidate in enumerate(self.routine_tasks)
                if candidate.get("id") == "game_login"
                and is_task_effectively_enabled(candidate)
            ),
            None,
        )
        if login_index is None:
            return False
        try:
            self.adb_client.tap(*map(int, target))
            self._invalidate_capture()
            self._interruptible_sleep(0.8)
            self.adb_client.force_stop_package(GAME_PACKAGE)
            self._interruptible_sleep(2.0)
            self.adb_client.launch_package(GAME_PACKAGE)
        except Exception:
            logger.exception("Login connection error recovery failed")
            return False

        self.routine_forced_task_active_id = "game_login"
        self.routine_forced_task_return_index = interrupted_index
        self.routine_next_run["game_login"] = 0.0
        self.current_routine_index = int(login_index)
        self.current_routine_task_id = None
        self.routine_current_had_action = False
        self.routine_completed_steps = set()
        self.routine_idle_confirmation_count = 0
        self.blocked_coords.clear()
        self.routine_last_action_time = time.time()
        self.set_status_message(
            "Ошибка входа: перезапускаю игру и затем продолжу текущую задачу",
            force=True,
        )
        logger.warning(
            "In-game login connection error confirmed; forced game_login will return "
            "to interrupted routine %s at index %s",
            task.get("id"),
            interrupted_index,
        )
        self.save_config()
        self._interruptible_sleep(8.0)
        return True

    def _find_template_opencv(self, template_path, region, confidence, grayscale, scales):
        screen_bgr, origin = self._capture_screen_bgr(region=region)
        if grayscale:
            screen = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            template = self.template_cache.get_gray(template_path)
        else:
            screen = screen_bgr
            template = self.template_cache.get_color(template_path)
        if template is None:
            return None, None, 0

        best_val = -1.0
        best_loc = None
        best_size = None
        for scale in scales:
            if isinstance(scale, (tuple, list)):
                scale_x, scale_y = map(float, scale[:2])
            else:
                scale_x = scale_y = float(scale)
            if scale_x <= 0 or scale_y <= 0:
                continue
            if abs(scale_x - 1.0) < 0.0001 and abs(scale_y - 1.0) < 0.0001:
                resized = template
            else:
                width = int(template.shape[1] * scale_x)
                height = int(template.shape[0] * scale_y)
                if width < 5 or height < 5:
                    continue
                resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_LINEAR)
            if resized.shape[0] > screen.shape[0] or resized.shape[1] > screen.shape[1]:
                continue
            result = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_val:
                best_val = float(max_val)
                best_loc = max_loc
                best_size = (resized.shape[1], resized.shape[0])

        if best_loc is None or best_val < float(confidence):
            return None, None, max(0.0, best_val)
        left = int(best_loc[0] + origin[0])
        top = int(best_loc[1] + origin[1])
        width, height = best_size
        return (
            pyautogui.Point(left + width // 2, top + height // 2),
            (left, top, int(width), int(height)),
            best_val,
        )

    def get_default_status_message(self):
        if self.state == BotState.RUNNING:
            return self.tr('state_running')
        if self.state == BotState.PAUSED:
            return self.tr('state_paused')
        if self.start_time:
            return self.tr('state_stopped')
        return self.tr('ready')

    def sync_status_message(self):
        message = self.status_message if self.diagnostic_enabled and self.status_message else self.get_default_status_message()
        self._apply_status_message(message)

    def _locate_image(self, img_config):
        confidence = img_config.get("confidence", 0.8)
        if self.uses_adb:
            search_region = self._region if self.work_area_type == 'selected' else None
            configured_region = img_config.get("search_region")
            if configured_region and len(configured_region) == 4:
                display = self.get_display_profile()
                x, y, width, height = map(float, configured_region)
                search_region = (
                    int(round(x * display.scale_x)),
                    int(round(y * display.scale_y)),
                    int(round(width * display.scale_x)),
                    int(round(height * display.scale_y)),
                )
            scales = matching_scales(
                self.get_display_profile(),
                extra_enabled=self.scale_enabled and img_config.get("use_scaling", True),
                minimum=self.scale_min,
                maximum=self.scale_max,
                steps=self.scale_steps,
            )
            return self._find_template_opencv(
                img_config["path"],
                search_region,
                confidence,
                img_config.get("grayscale", True),
                scales,
            )
        screen_region = self._screen_game_region()
        if self.scale_enabled and img_config.get("use_scaling", True):
            return self._find_template_scaled(
                img_config["path"],
                screen_region,
                confidence=confidence,
            )

        try:
            rect = pyautogui.locateOnScreen(
                img_config["path"],
                region=screen_region,
                confidence=confidence,
                grayscale=img_config.get("grayscale", True)
            )
        except pyautogui.ImageNotFoundException:
            return None, None, 0
        if not rect:
            return None, None, 0

        template_size = self.template_cache.get_size(img_config["path"])
        if not template_size:
            return None, None, 0
        orig_w, orig_h = template_size
        if abs(rect[2] - orig_w) > orig_w * 0.2 or abs(rect[3] - orig_h) > orig_h * 0.2:
            return None, None, 0

        location = pyautogui.center(rect)
        bbox = (int(rect.left), int(rect.top), int(rect.width), int(rect.height))
        return location, bbox, confidence

    def _passes_color_check(self, img_config, bbox):
        if img_config.get("grayscale", True):
            return True
        template_img = self.template_cache.get_color(img_config["path"])
        if template_img is None:
            return False
        template_avg = cv2.mean(template_img)[:3]
        found = self._capture_bbox_bgr(bbox)
        found_avg = cv2.mean(found)[:3]
        dist = np.linalg.norm(np.array(found_avg) - np.array(template_avg))
        color_threshold = 60
        logger.info(f"Цветовое расстояние для {img_config['description']}: {dist:.1f}")
        return dist <= color_threshold

    def _validate_detected_match(self, img_config, bbox):
        if img_config.get("research_queue_region"):
            display = (
                self.get_display_profile()
                if self.uses_adb
                else make_display_profile(1280, 720)
            )
            if not research_queue_match_is_safe(
                bbox,
                display.width,
                display.height,
            ):
                return False, "REGION"
        if img_config.get("training_queue_region"):
            display = (
                self.get_display_profile()
                if self.uses_adb
                else make_display_profile(1280, 720)
            )
            if not training_queue_match_is_safe(bbox, display.width, display.height):
                return False, "REGION"
        if self.orb_enabled and img_config.get("use_orb", True):
            orb_threshold = int(img_config.get("orb_match_threshold", self.orb_match_threshold))
            if not self._check_orb_match(img_config["path"], bbox, orb_threshold):
                return False, "ORB"
        elif self.ssim_enabled and not self._ssim_check(img_config["path"], bbox):
            return False, "SSIM"

        if not self._passes_color_check(img_config, bbox):
            return False, "COLOR"
        return True, None

    def _build_test_search_summary(self, checked, found_matches, group_name=None):
        lines = [self.tr('test_search_summary', checked=checked, found=len(found_matches))]
        if group_name:
            lines.append(f"{self.tr('group')}: {group_name}")
        if found_matches:
            for match in found_matches[:5]:
                lines.append(f"- {match['description']} @ ({match['x']}, {match['y']})")
            extra = len(found_matches) - 5
            if extra > 0:
                lines.append(self.tr('test_search_more', count=extra))
        else:
            lines.append(self.tr('test_search_no_matches'))
        return "\n".join(lines)

    def start_test_search(self):
        if self.is_running and not self.is_paused:
            self._show_notification('warning', 'test_search_pause_bot')
            return False
        if self.test_search_thread and self.test_search_thread.is_alive():
            self.set_status_message(self.tr('test_search_busy'), force=True)
            self._show_notification('info', 'test_search_busy')
            return False

        self.test_search_thread = threading.Thread(target=self._test_search_worker, daemon=True)
        self.test_search_thread.start()
        return True

    def _launch_game_for_login(self):
        if not self.uses_adb:
            self.set_status_message(
                "Вход в игру: ожидаю открытое окно и возвращаюсь на главный экран",
                force=True,
            )
            return True
        try:
            if self.adb_client is None:
                self._refresh_adb_client()
            self.set_status_message("Вход в игру: запускаю Doomsday", force=True)
            self.adb_client.launch_package(GAME_PACKAGE)
            self._adb_frame_cache = None
            self._adb_frame_timestamp = 0.0
            self._interruptible_sleep(5.0)
            self.routine_last_action_time = time.time()
            return True
        except AdbError as exc:
            logger.error("Не удалось запустить игру через ADB: %s", exc)
            self.set_status_message(f"Не удалось запустить игру: {exc}", force=True)
            return False

    def _restart_game_for_login(self):
        if (
            not self.uses_adb
            or self.routine_login_restart_count >= GAME_LOGIN_MAX_RESTARTS
        ):
            return False
        self.routine_login_restart_count += 1
        try:
            if self.adb_client is None:
                self._refresh_adb_client()
            self.set_status_message(
                (
                    "Вход в игру: загрузка зависла, перезапускаю Doomsday "
                    f"({self.routine_login_restart_count}/{GAME_LOGIN_MAX_RESTARTS})"
                ),
                force=True,
            )
            self.adb_client.force_stop_package(GAME_PACKAGE)
            self._interruptible_sleep(2.0)
            self.adb_client.launch_package(GAME_PACKAGE)
            self._adb_frame_cache = None
            self._adb_frame_timestamp = 0.0
            self.blocked_coords.clear()
            self.routine_completed_steps = set()
            self.routine_idle_confirmation_count = 0
            self._interruptible_sleep(8.0)
            restarted_at = time.time()
            self.routine_task_started_at = restarted_at
            self.routine_last_action_time = restarted_at
            logger.info("Game login package restart completed for %s", self.adb_serial)
            return True
        except AdbError as exc:
            logger.error("Не удалось перезапустить игру через ADB: %s", exc)
            self.set_status_message(f"Не удалось перезапустить игру: {exc}", force=True)
            return False

    def _test_search_worker(self):
        current_group = None
        if self.routine_mode:
            task = self.get_routine_task(self.current_routine_task_id)
            if task is None:
                task = next(
                    (item for item in self.routine_tasks if item.get("enabled")),
                    None,
                )
            current_group = task.get("group") if task else None
            images = [
                img for img in self.search_images
                if img.get("group") == current_group and self._is_active(img)
            ]
        elif self.cycle_mode and self.cycle_groups:
            current_group = self.cycle_groups[self.current_cycle_index % len(self.cycle_groups)]
            images = [
                img for img in self.search_images
                if img.get("group") == current_group and self._is_active(img)
            ]
        else:
            images = [img for img in self.search_images if self._is_active(img)]

        if not images:
            self.set_status_message(self.tr('no_areas'), force=True)
            self._show_notification('info', 'no_areas')
            return

        self.set_status_message(self.tr('test_search_started'), force=True)
        found_matches = []
        checked = 0

        for index, img_config in enumerate(images, start=1):
            self.set_status_message(
                f"{self.tr('test_search')}: {index}/{len(images)} - {img_config['description']}",
                force=True,
            )
            try:
                location, bbox, _ = self._locate_image(img_config)
                checked += 1
                if not location or not bbox:
                    continue
                is_valid, reject_reason = self._validate_detected_match(img_config, bbox)
                if not is_valid:
                    self.set_status_message(
                        f"{self.tr('test_search')}: {img_config['description']} - {reject_reason}",
                        force=True,
                    )
                    continue
                found_matches.append({
                    "description": img_config["description"],
                    "x": int(location.x),
                    "y": int(location.y),
                })
                self.set_status_message(
                    f"{self.tr('test_search')}: {img_config['description']} @ ({int(location.x)}, {int(location.y)})",
                    force=True,
                )
            except Exception:
                logger.exception(f"Ошибка тестового поиска для области {img_config.get('description')}:")

        summary = self._build_test_search_summary(checked, found_matches, group_name=current_group)
        self.set_status_message(summary, force=True)
        self._show_notification('info', 'info', message=summary)

    def attach_status_var(self, status_var):
        self.status_var = status_var
        self.sync_status_message()

    def set_status_message(self, message, force=False):
        message = str(message)
        if not force and not self.diagnostic_enabled:
            return
        if message == self.status_message:
            return
        self.status_message = message
        if force:
            logger.info("Статус: %s", message)
        if self.root and hasattr(self, "status_var"):
            self.gui_queue.put((self._apply_status_message, (message,), {}))

    def _apply_status_message(self, message):
        if hasattr(self, "status_var"):
            self.status_var.set(message)

    def invalidate_template(self, template_path):
        self.orb_cache.pop(template_path, None)
        self.template_cache.invalidate(template_path)

    def get_monitors(self):
        try:
            import screeninfo
            return [(m.x, m.y, m.width, m.height) for m in screeninfo.get_monitors()]
        except ImportError:
            logger.warning("screeninfo не установлен, используется основной монитор")
            if self.root:
                return [(0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())]
            screen_size = pyautogui.size()
            return [(0, 0, screen_size.width, screen_size.height)]

    def _ssim_check(self, template_path, bbox):
        try:
            from skimage.metrics import structural_similarity as ssim
        except ImportError:
            return True
        template = self.template_cache.get_gray(template_path)
        if template is None:
            return True
        screen = self._capture_bbox_bgr(bbox)
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        h, w = template.shape
        screen_resized = cv2.resize(screen_gray, (w, h))
        score = ssim(template, screen_resized)
        logger.info(f"SSIM: {score:.3f} (порог {self.ssim_threshold})")
        return score >= self.ssim_threshold

    def update_region_from_work_area(self):
        if self.work_area_type == 'fullscreen':
            self._region = None
        elif self.work_area_type.startswith('monitor'):
            idx = int(self.work_area_type.replace('monitor', '')) - 1
            if 0 <= idx < len(self.monitors):
                self._region = self.monitors[idx]
            else:
                self._region = None

    def tr(self, key, **kwargs):
        text = LANGUAGES.get(self.lang, LANGUAGES['ru']).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except:
                return text
        return text

    def _resolve_image_path(self, stored_path, group=None):
        path = Path(stored_path)
        candidates = []
        if path.is_absolute():
            try:
                path.relative_to(APP_DIR)
                candidates.append(path)
            except ValueError:
                parts_lower = [part.lower() for part in path.parts]
                if "img" in parts_lower:
                    img_index = len(parts_lower) - 1 - parts_lower[::-1].index("img")
                    candidates.append(IMG_DIR.joinpath(*path.parts[img_index + 1:]))
                if group:
                    candidates.append(self._get_group_path(group) / path.name)
                candidates.append(IMG_DIR / path.name)
                candidates.append(path)
        else:
            candidates.append(APP_DIR / path)
            if group:
                candidates.append(self._get_group_path(group) / path.name)
            candidates.append(IMG_DIR / path.name)

        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()

        if path.name and IMG_DIR.exists():
            match = next(IMG_DIR.rglob(path.name), None)
            if match:
                return match.resolve()
        return candidates[0] if candidates else path

    def _images_for_config(self):
        serialized = []
        for image in self.search_images:
            item = dict(image)
            path = Path(item.get("path", ""))
            try:
                item["path"] = str(path.resolve().relative_to(APP_DIR.resolve()))
            except (OSError, ValueError):
                item["path"] = str(path)
            serialized.append(item)
        return serialized

    def export_training_profile(self, destination):
        destination = Path(destination)
        routine_groups = {task.get("group") for task in self.routine_tasks}
        routine_groups.add(SYSTEM_TEMPLATE_GROUP)
        routine_groups.add(ACCOUNT_SWITCH_TEMPLATE_GROUP)
        images = [img for img in self.search_images if img.get("group") in routine_groups]
        if self.uses_adb:
            source_frame = self._capture_adb_frame(force=True)
            source_width, source_height = source_frame.shape[1], source_frame.shape[0]
        else:
            screen_size = pyautogui.size()
            source_width, source_height = screen_size.width, screen_size.height
        manifest = {
            "format": "doomsday-training-profile",
            "format_version": 1,
            "app_version": APP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_screen": {"width": source_width, "height": source_height},
            "routine_tasks": self.routine_tasks,
            "routine_max_marches": self.routine_max_marches,
            "groups": {
                group: self.groups.get(group, True)
                for group in routine_groups if group
            },
            "matching": {
                "scale_enabled": self.scale_enabled,
                "scale_min": self.scale_min,
                "scale_max": self.scale_max,
            },
            "images": [],
        }

        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for image in images:
                source = Path(image.get("path", ""))
                if not source.exists():
                    continue
                uid = image.get("uid") or uuid.uuid4().hex
                entry_name = f"templates/{uid}{source.suffix.lower() or '.png'}"
                image_data = dict(image)
                image_data["uid"] = uid
                image_data["path"] = entry_name
                manifest["images"].append(image_data)
                archive.write(source, entry_name)
            archive.writestr(
                "profile.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
        return len(manifest["images"])

    def import_training_profile(self, source_path):
        with zipfile.ZipFile(source_path, "r") as archive:
            try:
                manifest = json.loads(archive.read("profile.json").decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(self.tr('profile_format_error')) from exc
            if manifest.get("format") != "doomsday-training-profile":
                raise ValueError(self.tr('profile_format_error'))

            self.routine_tasks = normalize_routine_tasks(manifest.get("routine_tasks"))
            self.routine_max_marches = min(5, max(1, int(manifest.get("routine_max_marches", 5))))
            for group, enabled in manifest.get("groups", {}).items():
                if group:
                    self.groups[group] = bool(enabled)
            for task in self.routine_tasks:
                self.groups.setdefault(task.get("group"), task.get("enabled", True))

            existing_by_uid = {
                image.get("uid"): image
                for image in self.search_images if image.get("uid")
            }
            added = 0
            skipped = 0
            archive_names = set(archive.namelist())
            for image_data in manifest.get("images", []):
                if not isinstance(image_data, dict):
                    continue
                uid = str(image_data.get("uid") or uuid.uuid4())
                entry_name = str(image_data.get("path", ""))
                entry_path = Path(entry_name)
                if (
                    entry_name not in archive_names
                    or not entry_name.startswith("templates/")
                    or ".." in entry_path.parts
                ):
                    continue
                if uid in existing_by_uid:
                    skipped += 1
                    continue

                group = str(image_data.get("group") or "").strip() or None
                target_folder = self._get_group_path(group)
                suffix = entry_path.suffix.lower() or ".png"
                target = target_folder / f"{uid}{suffix}"
                target.write_bytes(archive.read(entry_name))

                image = dict(image_data)
                image["uid"] = uid
                image["path"] = str(target.resolve())
                image["group"] = group
                image["last_used"] = 0
                self.search_images.append(image)
                self.stats[image["path"]] = 0
                existing_by_uid[uid] = image
                added += 1

        matching = manifest.get("matching", {})
        upgrade_resource_runtime_metadata(self.search_images, self.routine_tasks)
        upgrade_strict_runtime_metadata(self.search_images, self.routine_tasks)
        upgrade_prize_hunt_metadata(self.search_images, self.routine_tasks)
        upgrade_radar_runtime_metadata(self.search_images, self.routine_tasks)
        upgrade_mysterious_merchant_metadata(self.search_images, self.routine_tasks)
        upgrade_truck_metadata(self.search_images, self.routine_tasks)
        upgrade_repeatable_claim_metadata(self.search_images, self.routine_tasks)
        upgrade_processing_runtime_metadata(self.search_images, self.routine_tasks)
        self.scale_enabled = bool(matching.get("scale_enabled", self.scale_enabled))
        self.scale_min = float(matching.get("scale_min", self.scale_min))
        self.scale_max = float(matching.get("scale_max", self.scale_max))
        self.save_config()
        if self.root:
            self.root.event_generate("<<GroupsChanged>>")
        source_screen = manifest.get("source_screen", {})
        return {
            "added": added,
            "skipped": skipped,
            "width": source_screen.get("width", "?"),
            "height": source_screen.get("height", "?"),
        }

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    self.search_images = data.get('images', [])
                    self.groups = data.get('groups', {})
                    self.group_schedules = data.get('group_schedules', {})
                    self.group_execution = data.get('group_execution', {})
                    self.routine_tasks = normalize_routine_tasks(data.get('routine_tasks'))
                    self.routine_max_marches = min(5, max(1, int(data.get('routine_max_marches', 5))))
                    now = time.time()
                    self.routine_next_run = {
                        str(task_id): float(deadline)
                        for task_id, deadline in data.get('routine_next_run', {}).items()
                        if isinstance(deadline, (int, float))
                    }
                    try:
                        self.current_routine_index = max(
                            0,
                            int(data.get('current_routine_index', 0) or 0),
                        )
                    except (TypeError, ValueError):
                        self.current_routine_index = 0
                    self.routine_pass_completed = bool(
                        data.get('routine_pass_completed', False)
                    )
                    self.routine_radar_dispatched_this_pass = bool(
                        data.get('routine_radar_dispatched_this_pass', False)
                    )
                    self.routine_radar_return_hold = bool(
                        self.routine_radar_dispatched_this_pass
                        and not self.routine_pass_completed
                    )
                    try:
                        self.routine_radar_return_observed_peak = min(
                            self.routine_max_marches,
                            max(
                                0,
                                int(
                                    data.get(
                                        'routine_radar_return_observed_peak',
                                        0,
                                    )
                                    or 0
                                ),
                            ),
                        )
                    except (TypeError, ValueError):
                        self.routine_radar_return_observed_peak = 0
                    if not self.routine_radar_return_hold:
                        self.routine_radar_return_observed_peak = 0
                    # March reservations are estimates for the current process.
                    # Carrying them across restarts can stop one squad too early
                    # after the real march has already returned.
                    self.routine_march_deadlines = []
                    self.routine_march_context = str(data.get('routine_march_context') or "")
                    raw_zombie_restore = data.get('zombie_level_restore', {})
                    self.zombie_level_restore = {}
                    self.zombie_level_restore_pending = {
                        str(context): min(3, max(0, int(levels)))
                        for context, levels in raw_zombie_restore.items()
                        if isinstance(context, str) and isinstance(levels, (int, float))
                    } if isinstance(raw_zombie_restore, dict) else {}
                    for task in self.routine_tasks:
                        self.groups.setdefault(effective_task_group(task), task.get("enabled", True))
                    self.groups.setdefault(SYSTEM_TEMPLATE_GROUP, True)

                    # Загрузка профилей циклов
                    self.cycle_profiles = data.get('cycle_profiles', {})
                    self.current_cycle_profile = data.get('current_cycle_profile', 'default')

                    # Если профилей нет, создаём профиль по умолчанию из старых настроек
                    if not self.cycle_profiles:
                        cycle_data = data.get('cycle_config', {})
                        self.cycle_profiles["default"] = {
                            "enabled": cycle_data.get('enabled', False),
                            "timeout": cycle_data.get('timeout', 5.0),
                            "groups": cycle_data.get('groups', [])
                        }
                        self.current_cycle_profile = "default"

                    # Применяем текущий профиль к рабочим переменным
                    profile = self.cycle_profiles.get(self.current_cycle_profile, {})
                    self.cycle_mode = profile.get("enabled", False)
                    self.cycle_timeout = profile.get("timeout", 5.0)
                    self.cycle_groups = profile.get("groups", [])

                    self.sleep_found = data.get('sleep_found', 2.0)
                    self.sleep_not_found = data.get('sleep_not_found', 0.05)
                    self.work_area_type = data.get('work_area_type', 'fullscreen')
                    self.scale_enabled = data.get('scale_enabled', False)
                    self.scale_min = data.get('scale_min', 0.8)
                    self.scale_max = data.get('scale_max', 1.2)
                    self.minimize_on_start = data.get('minimize_on_start', True)
                    self.lang = data.get('language', 'ru')
                    self.anti_loop_enabled = data.get('anti_loop_enabled', True)
                    self.orb_enabled = data.get('orb_enabled', True)
                    self.ssim_enabled = data.get('ssim_enabled', True)
                    self.ssim_threshold = data.get('ssim_threshold', 0.9)
                    self.diagnostic_enabled = data.get('diagnostic_enabled', True)
                    self.input_backend = data.get('input_backend', 'screen')
                    if self.input_backend not in ('screen', 'adb'):
                        self.input_backend = 'screen'
                    self.adb_serial = str(data.get('adb_serial', self.adb_serial) or self.adb_serial)
                    self.adb_path = str(data.get('adb_path', self.adb_path) or self.adb_path)
                    self.player_width = max(1, int(data.get('player_width', self.player_width)))
                    self.player_height = max(1, int(data.get('player_height', self.player_height)))
                    self.account_profiles = normalize_account_profiles(
                        data.get('account_profiles'),
                        self.adb_serial,
                    )
                    ensure_account_task_defaults(
                        self.account_profiles,
                        self.routine_tasks,
                        enabled_task_ids=("mysterious_merchant", "trucks"),
                    )
                    self._migrate_account_logins_to_credential_store()
                    if not self.is_multi_worker:
                        try:
                            self.account_profiles = recover_account_profiles(
                                self.account_profiles,
                                self.credential_store.list_keys(),
                                self.adb_serial,
                            )
                        except CredentialError as exc:
                            logger.warning("Не удалось восстановить локальные профили: %s", exc)
                    self.current_account_id = str(
                        data.get('current_account_id') or self.account_profiles[0]['id']
                    )
                    if not find_account(self.account_profiles, self.current_account_id):
                        self.current_account_id = self.account_profiles[0]['id']
                    self.account_rotation_enabled = bool(data.get('account_rotation_enabled', False))
                    self.account_pass_account_id = str(
                        data.get('account_pass_account_id') or ""
                    )
                    try:
                        self.account_pass_started_at = max(
                            0.0,
                            float(data.get('account_pass_started_at', 0.0) or 0.0),
                        )
                    except (TypeError, ValueError):
                        self.account_pass_started_at = 0.0
                    if self.account_pass_account_id != self.current_account_id:
                        # A copied or manually edited config must not apply one
                        # profile's expired budget to another profile.
                        self.account_pass_account_id = ""
                        self.account_pass_started_at = 0.0
                    try:
                        self.routine_research_budget_started_at = max(
                            0.0,
                            float(
                                data.get(
                                    'routine_research_budget_started_at',
                                    0.0,
                                )
                                or 0.0
                            ),
                        )
                    except (TypeError, ValueError):
                        self.routine_research_budget_started_at = 0.0
                    try:
                        self.account_switch_failure_count = max(
                            0,
                            int(data.get('account_switch_failure_count', 0) or 0),
                        )
                    except (TypeError, ValueError):
                        self.account_switch_failure_count = 0
                    current_account = find_account(self.account_profiles, self.current_account_id)
                    if current_account:
                        self.adb_serial = current_account.get('adb_serial', self.adb_serial)
                        apply_account_tasks(current_account, self.routine_tasks)
                        if current_account.get('routine_next_run'):
                            self.routine_next_run = {
                                str(task_id): float(deadline)
                                for task_id, deadline in current_account['routine_next_run'].items()
                                if isinstance(deadline, (int, float))
                            }

                    for img in self.search_images:
                        img["path"] = str(self._resolve_image_path(img.get("path", ""), img.get("group")))
                        if "uid" not in img:
                            img["uid"] = str(uuid.uuid4())
                        if "group" not in img:
                            img["group"] = None
                        if "numbers" in img:
                            img["numbers"] = [str(n) for n in img["numbers"]]
                        else:
                            img["numbers"] = []
                        if "click_sequence" not in img:
                            img["click_sequence"] = []
                        if "last_used" not in img:
                            img["last_used"] = 0
                        if "cooldown" not in img:
                            img["cooldown"] = 1.5
                        if "use_scaling" not in img:
                            img["use_scaling"] = True
                        if "match_method" in img:
                            del img["match_method"]

                    legacy_radar_images = [
                        image
                        for image in self.search_images
                        if str(image.get("uid") or "") in LEGACY_RADAR_TEMPLATE_UIDS
                    ]
                    if legacy_radar_images:
                        managed_root = IMG_DIR.resolve()
                        for image in legacy_radar_images:
                            try:
                                legacy_path = Path(image.get("path", "")).resolve()
                                if legacy_path.is_relative_to(managed_root) and legacy_path.exists():
                                    legacy_path.unlink()
                            except OSError:
                                logger.warning(
                                    "Не удалось удалить старый шаблон радара: %s",
                                    image.get("path"),
                                )
                        self.search_images = [
                            image
                            for image in self.search_images
                            if str(image.get("uid") or "") not in LEGACY_RADAR_TEMPLATE_UIDS
                        ]
                        self.groups.pop("Радарная станция", None)
                        self.group_schedules.pop("Радарная станция", None)
                        self.group_execution.pop("Радарная станция", None)
                        self.routine_next_run.pop("radar", None)
                        logger.info(
                            "Удалено старых встроенных шаблонов радара: %s",
                            len(legacy_radar_images),
                        )

                    upgraded_resources = upgrade_resource_runtime_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_resources:
                        logger.info("Resource runtime sequence upgraded for %s templates", upgraded_resources)
                    upgraded_strict = upgrade_strict_runtime_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_strict:
                        logger.info("Strict runtime sequence upgraded for %s templates", upgraded_strict)
                    upgraded_prize = upgrade_prize_hunt_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_prize:
                        logger.info("Prize hunt branches upgraded for %s templates", upgraded_prize)
                    upgraded_radar = upgrade_radar_runtime_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_radar:
                        logger.info("Radar template priorities upgraded for %s templates", upgraded_radar)
                    upgraded_merchant = upgrade_mysterious_merchant_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_merchant:
                        logger.info(
                            "Mysterious merchant sequence upgraded for %s templates",
                            upgraded_merchant,
                        )
                    upgraded_trucks = upgrade_truck_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_trucks:
                        logger.info(
                            "Truck sequence upgraded for %s templates",
                            upgraded_trucks,
                        )
                    upgraded_claims = upgrade_repeatable_claim_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_claims:
                        logger.info("Repeatable reward guards upgraded for %s templates", upgraded_claims)
                    upgraded_processing = upgrade_processing_runtime_metadata(
                        self.search_images,
                        self.routine_tasks,
                    )
                    if upgraded_processing:
                        logger.info(
                            "Processing camera movement upgraded for %s templates",
                            upgraded_processing,
                        )

                    self.stats = {img['path']: 0 for img in self.search_images}
                    logger.info(f"Загружено {len(self.search_images)} областей из конфига")

                    # The configured path is authoritative. Moving files on every
                    # startup breaks stable task folders and non-ASCII Windows paths.
                    self.save_config()

            except Exception as e:
                logger.error(f"Ошибка загрузки конфига: {e}")
                self._load_existing_images()
        else:
            self._load_existing_images()

    def save_config(self):
        try:
            current_account = find_account(self.account_profiles, self.current_account_id)
            if current_account:
                snapshot_account_tasks(current_account, self.routine_tasks)
                current_account['routine_next_run'] = dict(self.routine_next_run)
            data = {
                'images': self._images_for_config(),
                'groups': self.groups,
                'group_schedules': self.group_schedules,
                'group_execution': self.group_execution,
                'routine_tasks': self.routine_tasks,
                'routine_max_marches': self.routine_max_marches,
                'routine_march_context': self.routine_march_context,
                'zombie_level_restore': {
                    **getattr(self, 'zombie_level_restore_pending', {}),
                    **self.zombie_level_restore,
                },
                'routine_next_run': self.routine_next_run,
                'current_routine_index': self.current_routine_index,
                'routine_pass_completed': self.routine_pass_completed,
                'routine_research_budget_started_at': float(
                    self.routine_research_budget_started_at or 0.0
                ),
                'routine_radar_dispatched_this_pass': bool(
                    self.routine_radar_dispatched_this_pass
                ),
                'routine_radar_return_observed_peak': int(
                    self.routine_radar_return_observed_peak or 0
                ),
                'account_profiles': self.account_profiles,
                'current_account_id': self.current_account_id,
                'account_rotation_enabled': self.account_rotation_enabled,
                'account_pass_started_at': float(
                    self.account_pass_started_at or 0.0
                ),
                'account_pass_account_id': str(
                    self.account_pass_account_id or ""
                ),
                'account_switch_failure_count': int(
                    self.account_switch_failure_count or 0
                ),
                'cycle_profiles': self.cycle_profiles,
                'current_cycle_profile': self.current_cycle_profile,
                'sleep_found': self.sleep_found,
                'sleep_not_found': self.sleep_not_found,
                'work_area_type': self.work_area_type,
                'scale_enabled': self.scale_enabled,
                'scale_min': self.scale_min,
                'scale_max': self.scale_max,
                'minimize_on_start': self.minimize_on_start,
                'language': self.lang,
                'anti_loop_enabled': self.anti_loop_enabled,
                'orb_enabled': self.orb_enabled,
                'ssim_enabled': self.ssim_enabled,
                'ssim_threshold': self.ssim_threshold,
                'diagnostic_enabled': self.diagnostic_enabled,
                'input_backend': self.input_backend,
                'adb_serial': self.adb_serial,
                'adb_path': self.adb_path,
                'player_width': self.player_width,
                'player_height': self.player_height,
            }
            save_json_with_backup(CONFIG_FILE, data, backup_dir=CONFIG_BACKUP_DIR, keep_backups=10)
            logger.debug("Конфиг сохранён")
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")

    def _load_existing_images(self):
        img_folder = IMG_DIR
        if img_folder.exists():
            for png_file in img_folder.rglob("*.png"):
                if TRASH_DIR in png_file.parents:
                    continue
                if not any(img["path"] == str(png_file) for img in self.search_images):
                    description = png_file.stem
                    if '_' in description:
                        parts = description.split('_')
                        if len(parts) > 1 and not parts[0].isascii():
                            description = parts[0]
                    group = None
                    if png_file.parent != img_folder:
                        group = png_file.parent.name
                    new_image = {
                        "uid": str(uuid.uuid4()),
                        "path": str(png_file),
                        "action": "click",
                        "delay": self.sleep_found,
                        "confidence": 0.9,
                        "grayscale": True,
                        "description": description,
                        "enabled": True,
                        "click_offset": (0, 0),
                        "numbers": [],
                        "click_sequence": [],
                        "last_used": 0,
                        "cooldown": 1.5,
                        "group": group,
                        "use_scaling": True,
                    }
                    self.search_images.append(new_image)
                    self.stats[str(png_file)] = 0
            self.save_config()

    def _sanitize_filename(self, name):
        if not name:
            return ""
        invalid_chars = '<>:"/\\|?*'
        for ch in invalid_chars:
            name = name.replace(ch, '_')
        return name.strip()

    def _get_group_path(self, group_name):
        if not group_name:
            return IMG_DIR
        safe_name = self._transliterate(group_name)
        safe_name = self._sanitize_filename(safe_name)
        group_folder = IMG_DIR / safe_name
        group_folder.mkdir(parents=True, exist_ok=True)
        return group_folder

    def _move_image_to_group(self, img_config, new_group):
        old_path = Path(img_config["path"])
        if not old_path.exists():
            return False
        if new_group:
            new_folder = self._get_group_path(new_group)
        else:
            new_folder = IMG_DIR
        new_path = new_folder / old_path.name
        if new_path.exists():
            base = new_path.stem
            ext = new_path.suffix
            counter = 1
            while new_path.exists():
                new_path = new_folder / f"{base}_{counter}{ext}"
                counter += 1
        if old_path.parent == new_folder:
            return True
        try:
            old_path.rename(new_path)
            self.invalidate_template(str(old_path))
            img_config["path"] = str(new_path)
            logger.info(f"Файл перемещён: {old_path} -> {new_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка перемещения файла: {e}")
            return False

    def _delete_image(self, img_config):
        path = Path(img_config["path"])
        if path.exists():
            try:
                destination = move_file_to_trash(path, TRASH_DIR)
                self.invalidate_template(str(path))
                logger.info(f"Файл перемещён в корзину: {path} -> {destination}")
                return destination
            except Exception as e:
                logger.error(f"Ошибка удаления файла {path}: {e}")
        return None

    def _transliterate(self, text):
        ru_to_en = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
            'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
            'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
        }
        result = ''
        for char in text:
            if char in ru_to_en:
                result += ru_to_en[char]
            elif char.isalnum() or char in (' ', '-', '_'):
                result += char
            else:
                result += '_'
        return result

    def set_sleeps(self, found, not_found):
        if found < 0 or not_found < 0:
            logger.warning("Попытка установить отрицательные задержки")
            return
        self.sleep_found = float(found)
        self.sleep_not_found = float(not_found)
        self.save_config()

    def set_work_area(self, area_type):
        self.work_area_type = area_type
        self.update_region_from_work_area()
        self.save_config()

    def set_scaling(self, enabled, min_scale, max_scale, steps=None):
        self.scale_enabled = enabled
        self.scale_min = min_scale
        self.scale_max = max_scale
        if steps is not None:
            self.scale_steps = steps
        self.save_config()

    def set_custom_region(self, x, y, w, h):
        self._region = (x, y, w, h)
        self.work_area_type = 'selected'
        self.save_config()

    def get_routine_task_name(self, task):
        key = f"routine_name_{task.get('id', '')}"
        translated = self.tr(key)
        if translated != key:
            return translated
        return task.get("name") or task.get("group") or task.get("id", "")

    def get_routine_task(self, task_id):
        if task_id == "__account_switch__":
            return self.account_switch_task
        return next((task for task in self.routine_tasks if task.get("id") == task_id), None)

    def get_routine_templates(self, task, active_only=False):
        group = effective_task_group(task)
        images = [img for img in self.search_images if img.get("group") == group]
        if task.get("id") == "mysterious_merchant":
            settings = task.get("settings", {})

            def merchant_offer_is_allowed(image):
                currency = str(image.get("merchant_currency") or "")
                if currency == "free":
                    return bool(settings.get("buy_free", True))
                if currency == "resources":
                    return bool(settings.get("buy_resources", True))
                if currency == "gems":
                    return not bool(settings.get("avoid_gems", True))
                return True

            images = [image for image in images if merchant_offer_is_allowed(image)]
        if active_only:
            if not self.groups.get(group, True):
                return []
            images = [img for img in images if img.get("enabled", True)]
        return images

    def set_routine_enabled(self, task_id, enabled, emit_event=True):
        task = self.get_routine_task(task_id)
        if not task:
            return
        task["enabled"] = bool(enabled)
        group = effective_task_group(task)
        if group:
            self.groups[group] = bool(enabled)
        self.save_config()
        if self.root and emit_event:
            self.root.event_generate("<<GroupsChanged>>")

    def clear_routine_selection(self):
        changed = 0
        for task in self.routine_tasks:
            if task.get("enabled", False):
                changed += 1
            task["enabled"] = False
            group = effective_task_group(task)
            if group:
                self.groups[group] = False
        self.save_config()
        if self.root:
            self.root.event_generate("<<GroupsChanged>>")
        return changed

    def set_routine_task_order(self, ordered_ids):
        self.routine_tasks = reorder_routine_tasks(self.routine_tasks, ordered_ids)
        self.current_routine_index = 0
        self.routine_pass_completed = False
        self.save_config()
        if self.root:
            self.root.event_generate("<<GroupsChanged>>")

    def get_current_account(self):
        return find_account(self.account_profiles, self.current_account_id)

    def _account_password_key(self, account_id, login_method=None):
        method = str(login_method or "").strip().lower()
        if not method:
            profile = find_account(self.account_profiles, account_id)
            method = str((profile or {}).get("login_method") or "igg").strip().lower()
        # Google passwords from older versions were stored under the bare ID.
        return str(account_id) if method == "google" else f"igg:{account_id}"

    def _account_login_key(self, account_id, login_method=None):
        method = str(login_method or "").strip().lower()
        if not method:
            profile = find_account(self.account_profiles, account_id)
            method = str((profile or {}).get("login_method") or "igg").strip().lower()
        return f"login:{method}:{account_id}"

    @staticmethod
    def _normalize_account_login(login):
        value = str(login or "").strip()
        if value.count("@") == 1:
            return value
        if "@" in value:
            return value
        for domain in ("yandex.ru", "mail.ru", "gmail.com", "bk.ru", "icloud.com"):
            if value.casefold().endswith(domain) and len(value) > len(domain):
                return f"{value[:-len(domain)]}@{value[-len(domain):]}"
        return value

    def get_account_login(self, account_id, login_method=None):
        try:
            key = self._account_login_key(account_id, login_method)
            stored_login = self.credential_store.get_password(key) or ""
            normalized_login = self._normalize_account_login(stored_login)
            if normalized_login != stored_login:
                self.credential_store.set_password(key, normalized_login)
            return normalized_login
        except CredentialError as exc:
            logger.warning("Не удалось прочитать логин профиля %s: %s", account_id, exc)
            return ""

    def account_has_saved_login(self, account_id):
        try:
            return self.credential_store.has_password(self._account_login_key(account_id))
        except CredentialError as exc:
            logger.warning("Не удалось проверить логин профиля %s: %s", account_id, exc)
            return False

    def account_has_saved_password(self, account_id):
        try:
            return self.credential_store.has_password(self._account_password_key(account_id))
        except CredentialError as exc:
            logger.warning("Не удалось проверить пароль профиля %s: %s", account_id, exc)
            return False

    def save_account_credentials(self, account_id, login, password=None, auto_login=False):
        profile = find_account(self.account_profiles, account_id)
        if not profile:
            raise ValueError("Профиль аккаунта не найден.")
        normalized_login = self._normalize_account_login(login)
        if not normalized_login:
            raise ValueError("Введите логин IGG.")
        login_method = str(profile.get("login_method") or "igg").strip().lower()
        if password is not None and str(password):
            self.credential_store.set_password(
                self._account_password_key(account_id, login_method),
                str(password),
            )
        self.credential_store.set_password(
            self._account_login_key(account_id, login_method),
            normalized_login,
        )
        # Credentials are machine-local. Never keep even the login in portable config.json.
        profile["google_login"] = ""
        profile["igg_login"] = ""
        profile["auto_login"] = bool(auto_login)
        self.save_config()
        return True

    def delete_account_password(self, account_id):
        profile = find_account(self.account_profiles, account_id)
        login_method = str((profile or {}).get("login_method") or "igg")
        removed_password = self.credential_store.delete_password(
            self._account_password_key(account_id, login_method)
        )
        removed_login = self.credential_store.delete_password(
            self._account_login_key(account_id, login_method)
        )
        if profile:
            profile["google_login"] = ""
            profile["igg_login"] = ""
            profile["auto_login"] = False
            self.save_config()
        return removed_password or removed_login

    def _migrate_account_logins_to_credential_store(self):
        changed = False
        for profile in self.account_profiles:
            account_id = str(profile.get("id") or "").strip()
            if not account_id:
                continue
            for method, field in (("igg", "igg_login"), ("google", "google_login")):
                legacy_login = str(profile.get(field) or "").strip()
                if not legacy_login:
                    continue
                key = self._account_login_key(account_id, method)
                try:
                    if not self.credential_store.has_password(key):
                        self.credential_store.set_password(key, legacy_login)
                except CredentialError as exc:
                    logger.warning(
                        "Не удалось перенести логин профиля %s в защищённое хранилище: %s",
                        account_id,
                        exc,
                    )
                    continue
                profile[field] = ""
                changed = True
        return changed

    @staticmethod
    def _google_signin_frame_is_visible(frame):
        if frame is None or frame.ndim != 3 or frame.shape[0] < 300 or frame.shape[1] < 500:
            return False
        height, width = frame.shape[:2]
        panel = frame[
            int(height * 0.08):int(height * 0.93),
            int(width * 0.20):int(width * 0.80),
        ]
        side = np.concatenate(
            (
                frame[:, :max(1, int(width * 0.12))],
                frame[:, int(width * 0.88):],
            ),
            axis=1,
        )
        bright_panel_ratio = float(np.mean(np.min(panel, axis=2) >= 225))
        side_values = side.astype(np.int16)
        blue_side_ratio = float(np.mean(
            (side_values[:, :, 0] >= 145)
            & (side_values[:, :, 0] >= side_values[:, :, 1] + 30)
            & (side_values[:, :, 1] >= side_values[:, :, 2] + 25)
        ))
        return bright_panel_ratio >= 0.55 and blue_side_ratio >= 0.35

    def fill_google_credential(self, account_id, stage):
        profile = find_account(self.account_profiles, account_id)
        if not profile:
            self.set_status_message("Профиль аккаунта не найден", force=True)
            return False
        if stage not in {"login", "password"}:
            self.set_status_message("Неизвестный этап входа Google", force=True)
            return False
        if not self.uses_adb or self.adb_client is None or not self.adb_client.is_responsive():
            self.set_status_message("Для входа Google требуется подключённый ADB", force=True)
            return False
        try:
            package = self.adb_client.current_foreground_package()
            if package not in {"com.google.android.gms", "com.google.android.gsf.login"}:
                raise CredentialError("Откройте соответствующее поле на странице входа Google.")
            frame = self.adb_client.screenshot_bgr()
            if not self._google_signin_frame_is_visible(frame):
                raise CredentialError("Страница входа Google не подтверждена.")
            value = self.get_account_login(account_id, "google")
            if stage == "password":
                value = self.credential_store.get_password(
                    self._account_password_key(account_id, "google")
                ) or ""
            if not value:
                label = "Пароль" if stage == "password" else "Логин"
                raise CredentialError(f"{label} не сохранён в профиле.")

            height, width = frame.shape[:2]
            field_x = int(round(width * 0.50))
            field_y = int(round(height * 0.47))
            next_x = int(round(width * 0.728))
            next_y = int(round(height * 0.659))
            self.adb_client.tap(field_x, field_y)
            time.sleep(0.25)
            self.adb_client.clear_focused_text(160)
            self.adb_client.input_private_text(value)
            time.sleep(0.35)
            self.adb_client.tap(next_x, next_y)
            self._invalidate_capture()
            label = "Пароль" if stage == "password" else "Логин"
            self.set_status_message(f"{label} Google введён; ожидаю следующий экран", force=True)
            return True
        except (AdbError, CredentialError, OSError, ValueError) as exc:
            logger.warning("Безопасный ввод Google не выполнен: %s", exc)
            self.set_status_message(str(exc), force=True)
            return False

    def fill_igg_credentials(self, account_id, form=None):
        profile = find_account(self.account_profiles, account_id)
        if not profile:
            raise CredentialError("Профиль аккаунта не найден.")
        if not self.uses_adb or self.adb_client is None or not self.adb_client.is_responsive():
            raise CredentialError("Для входа IGG требуется подключённый ADB.")
        if self.adb_client.current_foreground_package() != GAME_PACKAGE:
            raise CredentialError("Форма входа IGG не открыта в игре.")

        ui_xml = self.adb_client.ui_xml()
        targets = form or extract_igg_login_form(ui_xml)
        if not targets:
            raise CredentialError("Форма входа IGG не подтверждена.")
        login = self.get_account_login(account_id, "igg")
        password = self.credential_store.get_password(
            self._account_password_key(account_id, "igg")
        ) or ""
        if not login:
            raise CredentialError("Логин IGG не сохранён в профиле.")
        if not password:
            raise CredentialError("Пароль IGG не сохранён в профиле.")

        def enter_verified(target, value, label, *, exact):
            for attempt in range(2):
                self.adb_client.tap(*target)
                time.sleep(0.25)
                self.adb_client.clear_focused_text(256)
                self.adb_client.input_private_text(value)
                time.sleep(0.35)
                actual = self.adb_client.focused_edit_text_value()
                if actual is None or (actual == value if exact else bool(actual)):
                    return
                logger.warning("Поле IGG «%s» осталось пустым; повтор ввода", label)
            raise CredentialError(f"Не удалось безопасно заполнить поле IGG «{label}».")

        enter_verified(targets["login"], login, "логин", exact=True)
        enter_verified(targets["password"], password, "пароль", exact=False)

        # LDPlayer keeps the soft keyboard open after the password field. The
        # WebView may temporarily omit the submit button from UIAutomator until
        # the keyboard is hidden and the page has completed one layout pass.
        self.adb_client.keyevent(4)
        time.sleep(0.45)
        refreshed_targets = None
        for _attempt in range(3):
            refreshed_targets = extract_igg_login_form(self.adb_client.ui_xml())
            if refreshed_targets:
                break
            time.sleep(0.5)
        if not refreshed_targets:
            # Some IGG WebView versions submit automatically after the keyboard
            # closes. Continue with screen verification instead of restarting
            # the credential flow and risking a loop.
            self._invalidate_capture()
            self.set_status_message(
                "Данные IGG введены; форма закрылась, проверяю вход",
                force=True,
            )
            logger.info("IGG login form advanced after credential entry")
            return True
        self.adb_client.tap(*refreshed_targets["submit"])
        self._invalidate_capture()
        self.set_status_message("Данные IGG введены; проверяю главный экран", force=True)
        return True

    def select_account_profile(self, account_id, save=True, start_fresh_pass=False):
        profile = find_account(self.account_profiles, account_id)
        if not profile:
            return False
        current = self.get_current_account()
        if current:
            snapshot_account_tasks(current, self.routine_tasks)
            current["routine_next_run"] = dict(self.routine_next_run)
        self.current_account_id = profile["id"]
        self.account_switch_retry_at = 0.0
        self.current_routine_index = 0
        self.routine_pass_completed = False
        self.current_routine_task_id = None
        self.routine_radar_return_hold = False
        self.routine_radar_return_active_seen = False
        self.routine_radar_return_observed_peak = 0
        self.routine_radar_dispatched_this_pass = False
        self.routine_forced_task_queue = []
        self.routine_forced_task_active_id = None
        self.routine_forced_task_return_index = None
        self.routine_research_budget_started_at = 0.0
        self.account_switch_failure_count = 0
        apply_account_tasks(profile, self.routine_tasks)
        self.routine_next_run = {
            str(task_id): float(deadline)
            for task_id, deadline in profile.get("routine_next_run", {}).items()
            if isinstance(deadline, (int, float))
        }
        if start_fresh_pass:
            enabled_tasks = [
                task for task in self.routine_tasks if is_task_effectively_enabled(task)
            ]
            reset_manual_run_deadlines(enabled_tasks, self.routine_next_run)
            logger.info(
                "Fresh ordered pass scheduled immediately for account profile %s",
                profile["id"],
            )
        self.adb_serial = str(profile.get("adb_serial") or self.adb_serial)
        self._refresh_adb_client()
        self._ensure_routine_march_context()
        for task in self.routine_tasks:
            self.groups[effective_task_group(task)] = bool(task.get("enabled", False))
        if start_fresh_pass:
            self._reset_account_pass_clock()
        else:
            self.account_pass_started_at = 0.0
            self.account_pass_account_id = ""
            self.account_session_deadline = 0.0
        if save:
            self.save_config()
        if self.root:
            self.root.event_generate("<<AccountChanged>>")
            self.root.event_generate("<<GroupsChanged>>")
        return True

    def add_account_profile(
        self, name, ldplayer_index=5, adb_serial=None, session_minutes=30.0, chooser_index=1
    ):
        base_id = "".join(char if char.isalnum() else "_" for char in name.lower()).strip("_") or uuid.uuid4().hex[:8]
        account_id = base_id
        suffix = 2
        while find_account(self.account_profiles, account_id):
            account_id = f"{base_id}_{suffix}"
            suffix += 1
        profile = {
            "id": account_id,
            "name": str(name).strip() or f"Аккаунт {len(self.account_profiles) + 1}",
            "enabled": True,
            "ldplayer_index": int(ldplayer_index),
            "adb_serial": str(adb_serial or self.adb_serial),
            "session_minutes": max(1.0, float(session_minutes)),
            "login_method": "igg",
            "chooser_index": min(20, max(1, int(chooser_index))),
            "google_login": "",
            "igg_login": "",
            "auto_login": False,
            "switch_group": f"Аккаунт: {str(name).strip() or account_id}",
            "switch_completion_uid": "",
            "task_enabled": {},
            "task_settings": {},
            "routine_next_run": {},
        }
        snapshot_account_tasks(profile, self.routine_tasks)
        self.account_profiles.append(profile)
        self.save_config()
        return profile

    def remove_account_profile(self, account_id):
        if len(self.account_profiles) <= 1:
            return False
        try:
            self.credential_store.delete_password(self._account_password_key(account_id, "igg"))
            self.credential_store.delete_password(self._account_password_key(account_id, "google"))
            self.credential_store.delete_password(self._account_login_key(account_id, "igg"))
            self.credential_store.delete_password(self._account_login_key(account_id, "google"))
        except CredentialError as exc:
            logger.warning("Не удалось удалить учётные данные профиля %s: %s", account_id, exc)
        self.account_profiles = [profile for profile in self.account_profiles if profile.get("id") != account_id]
        if self.current_account_id == account_id:
            self.select_account_profile(self.account_profiles[0]["id"], save=False)
        self.save_config()
        return True

    def _prepare_account_switch(self, profile):
        group = ACCOUNT_SWITCH_TEMPLATE_GROUP
        templates = [
            image for image in self.search_images
            if image.get("group") == group and image.get("enabled", True)
        ]
        if not templates:
            self.set_status_message(f"Не обучено переключение аккаунта: {profile.get('name')}", force=True)
            return False
        # These controls are small, flat UI elements. ORB cannot reach the
        # global keypoint threshold on them, while template and color checks
        # remain stable across accounts.
        for image in templates:
            image["use_orb"] = False
            description = str(image.get("description") or "").casefold()
            action = str(image.get("action") or "")
            if "google" in description or action == "google_account_select":
                image["required_setting_key"] = "login_method"
                image["required_setting_value"] = "google"
            elif "igg" in description:
                image["required_setting_key"] = "login_method"
                image["required_setting_value"] = "igg"
        login_method = str(profile.get("login_method") or "igg").strip().lower()
        if login_method == "igg":
            if not profile.get("auto_login", False):
                self.set_status_message("Для переключения включите автоматический вход IGG", force=True)
                return False
            if not self.account_has_saved_login(profile["id"]):
                self.set_status_message("Для переключения сохраните логин IGG", force=True)
                return False
            if not self.account_has_saved_password(profile["id"]):
                self.set_status_message("Для переключения сохраните пароль IGG", force=True)
                return False
        self.account_switch_task = {
            "id": "__account_switch__",
            "name": f"Переключение: {profile.get('name')}",
            "group": group,
            "category": "system",
            "enabled": True,
            "uses_march": False,
            "priority": 1,
            "interval_minutes": 1.0,
            "timeout_seconds": ACCOUNT_SWITCH_TIMEOUT_SECONDS,
            "march_duration_minutes": 1.0,
            "completion_uid": str(profile.get("switch_completion_uid") or ""),
            "settings": {
                "target_account_id": profile["id"],
                "login_method": login_method,
                "chooser_index": int(profile.get("chooser_index", 1)),
                "auto_login": bool(profile.get("auto_login", False)),
            },
        }
        self.routine_only_task_id = "__account_switch__"
        self.current_routine_task_id = None
        self.account_switch_error = ""
        self.account_switch_selected_at = 0.0
        self.account_switch_confirmed = False
        self.account_switch_probe_ready = False
        self.account_switch_auto_login_attempted = False
        return True

    def start_account_switch(self, account_id):
        profile = find_account(self.account_profiles, account_id)
        # An explicit request is allowed to retry a previously blocked switch;
        # unattended rotation itself remains one bounded attempt per pass.
        self.account_switch_failure_count = 0
        if not profile or not self._prepare_account_switch(profile):
            return False
        # Latch the attempt before entering the external IGG flow.  If the
        # application is restarted mid-switch, autostart must not submit the
        # same profile transition again without an explicit retry.
        self.account_switch_failure_count = 1
        self.save_config()
        self.routine_mode = True
        self.routine_next_run["__account_switch__"] = 0.0
        return self.start()

    def start_account_probe(self, account_id=None):
        if self.uses_adb and self.adb_client is not None:
            try:
                account_dump = self.adb_client._run(
                    ["shell", "dumpsys", "account"],
                    timeout=30,
                )
                accounts = extract_android_google_accounts(account_dump)
            except (AdbError, OSError):
                accounts = []
            if accounts:
                self.account_switch_candidates = [
                    {"chooser_index": index, "email": email}
                    for index, email in enumerate(accounts, start=1)
                ]
                self.account_switch_last_result = f"Найдено аккаунтов Google: {len(accounts)}"
                labels = ", ".join(
                    f"№{item['chooser_index']} {mask_google_account(item['email'])}"
                    for item in self.account_switch_candidates
                )
                self.set_status_message(
                    f"{self.account_switch_last_result} ({labels})",
                    force=True,
                )
                return True
        profile = find_account(
            self.account_profiles,
            account_id or self.current_account_id,
        )
        if not profile or not self._prepare_account_switch(profile):
            return False
        self.account_switch_task["name"] = "Проверка аккаунтов Google"
        self.account_switch_task["settings"]["probe_only"] = True
        self.routine_mode = True
        self.routine_next_run["__account_switch__"] = 0.0
        return self.start()

    def _ensure_routine_march_context(self):
        context = routine_march_context_key(
            self.input_backend,
            self.adb_serial,
            self.current_account_id,
        )
        if context == self.routine_march_context:
            return False
        if self.routine_march_deadlines:
            logger.info(
                "March context changed from %s to %s; clearing %s estimated deadlines",
                self.routine_march_context or "legacy",
                context,
                len(self.routine_march_deadlines),
            )
        self.routine_march_context = context
        self.routine_march_deadlines = []
        self.routine_deployment_blocked_until = 0.0
        self.routine_confirmed_march_floor = 0
        self.routine_march_observer_grace_until = 0.0
        self.routine_zero_observation_started_at = 0.0
        self.routine_zero_observation_count = 0
        self.routine_lower_observation_value = None
        self.routine_lower_observation_started_at = 0.0
        self.routine_lower_observation_count = 0
        return True

    def get_active_marches(self, now=None):
        now = time.time() if now is None else float(now)
        previous_display = int(getattr(self, "routine_display_active_marches", 0) or 0)
        context_changed = self._ensure_routine_march_context()
        active = [deadline for deadline in self.routine_march_deadlines if float(deadline) > now]
        if context_changed or len(active) != len(self.routine_march_deadlines):
            self.routine_march_deadlines = active[:self.routine_max_marches]
            self.save_config()
        observed = self._detect_observed_marches()
        reconciled = reconcile_march_deadlines(
            self.routine_march_deadlines,
            observed,
            now,
            self.routine_march_observer_grace_until,
        )
        if reconciled != self.routine_march_deadlines:
            logger.info(
                "Observed march counter reconciled local reservations: %s -> %s",
                len(self.routine_march_deadlines),
                len(reconciled),
            )
            self.routine_march_deadlines = reconciled
            self.save_config()
        active_count = effective_active_marches(
            observed,
            len(reconciled),
            self.routine_confirmed_march_floor,
            now,
            self.routine_march_observer_grace_until,
        )
        if now >= self.routine_march_observer_grace_until:
            self.routine_confirmed_march_floor = 0
        self.routine_display_active_marches = min(self.routine_max_marches, active_count)
        if self.routine_display_active_marches != previous_display:
            logger.info(
                "March counter updated: displayed=%s, observed=%s, estimated=%s",
                self.routine_display_active_marches,
                observed,
                len(reconciled),
            )
        return self.routine_display_active_marches

    def _try_return_camped_zombie_march(self, active_marches, now=None):
        """Recall one zombie squad that remained in a camp after combat."""
        now = time.time() if now is None else float(now)
        if active_marches <= 0:
            self.zombie_camp_blocked_until = 0.0
            return False
        blocked_until = float(getattr(self, "zombie_camp_blocked_until", 0.0) or 0.0)
        if now < self.zombie_camp_scan_next_at:
            return now < blocked_until
        self.zombie_camp_scan_next_at = now + 3.0

        if self.current_routine_task_id:
            return False
        if self.routine_only_task_id not in {None, "zombie_hunt"}:
            return False
        task = self.get_routine_task("zombie_hunt")
        if not task or not is_task_effectively_enabled(task):
            return False
        if not self.groups.get(effective_task_group(task), True):
            return False

        try:
            frame, origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Не удалось проверить лагеря походов")
            self.zombie_camp_scan_next_at = now + 15.0
            return False
        if not self._world_map_visible_in_frame(frame):
            return now < blocked_until

        camp_targets = detect_camped_march_card_targets(frame)
        if not camp_targets:
            self.zombie_camp_blocked_until = 0.0
            return False
        card_x, card_y = camp_targets[0]
        camp_count_before = len(camp_targets)
        self.zombie_camp_blocked_until = now + 20.0

        def tap_frame(x, y, current_origin):
            if self.uses_adb:
                self.adb_client.tap(int(round(x)), int(round(y)))
            else:
                pyautogui.click(
                    current_origin[0] + int(round(x)),
                    current_origin[1] + int(round(y)),
                )
            self._invalidate_capture()

        self.set_status_message("Возвращаю отряд, оставшийся в лагере", force=True)
        logger.info("Найден лагерь похода в карточке (%s, %s); начинаю возврат", card_x, card_y)
        tap_frame(card_x, card_y, origin)
        self._interruptible_sleep(0.8)

        selected_frame, selected_origin = self._capture_screen_bgr(force=True)
        retreat_target = detect_march_retreat_target(selected_frame)
        if retreat_target is None:
            # March cards may reorder while a squad returns. Re-read the cyan
            # card instead of clicking a stale row or an arbitrary map point.
            refreshed_targets = detect_camped_march_card_targets(selected_frame)
            if refreshed_targets:
                refreshed_x, refreshed_y = refreshed_targets[0]
                tap_frame(refreshed_x, refreshed_y, selected_origin)
                self._interruptible_sleep(0.8)
                selected_frame, selected_origin = self._capture_screen_bgr(force=True)
                retreat_target = detect_march_retreat_target(selected_frame)
        if retreat_target is not None:
            # The world map contains many circular gold controls. Confirm the
            # same action pair on a second frame before issuing a retreat tap.
            self._interruptible_sleep(0.25)
            confirmed_frame, confirmed_origin = self._capture_screen_bgr(force=True)
            confirmed_target = detect_march_retreat_target(confirmed_frame)
            if (
                confirmed_target is None
                or abs(confirmed_target[0] - retreat_target[0]) > 12
                or abs(confirmed_target[1] - retreat_target[1]) > 12
            ):
                retreat_target = None
            else:
                retreat_target = confirmed_target
                selected_origin = confirmed_origin
        if retreat_target is None:
            logger.warning("Лагерь выбран, но кнопка возврата не подтверждена")
            self.set_status_message("Лагерь найден, возврат не подтверждён: повторю позже", force=True)
            self.zombie_camp_scan_next_at = time.time() + 15.0
            self.zombie_camp_blocked_until = self.zombie_camp_scan_next_at
            return True

        retreat_x, retreat_y = retreat_target
        tap_frame(retreat_x, retreat_y, selected_origin)
        for _attempt in range(10):
            self._interruptible_sleep(0.5)
            result_frame, _result_origin = self._capture_screen_bgr(force=True)
            if len(detect_camped_march_card_targets(result_frame)) < camp_count_before:
                logger.info("Возврат застрявшего похода подтверждён исчезновением значка лагеря")
                self.set_status_message("Застрявший отряд возвращается в убежище", force=True)
                self.zombie_camp_scan_next_at = time.time() + 1.5
                self.zombie_camp_blocked_until = self.zombie_camp_scan_next_at
                return True

        logger.warning("После нажатия возврата значок лагеря не исчез")
        self.set_status_message("Отряд остался в лагере: повторю возврат позже", force=True)
        self.zombie_camp_scan_next_at = time.time() + 15.0
        self.zombie_camp_blocked_until = self.zombie_camp_scan_next_at
        return True

    def _detect_observed_marches(self):
        observers = [
            image for image in self.search_images
            if image.get("observer_only") and image.get("march_count") is not None
        ]
        if not observers:
            return None
        try:
            frame, _origin = self._capture_screen_bgr(force=False)
        except Exception:
            logged_at = float(getattr(self, "_march_observer_error_logged_at", 0.0) or 0.0)
            now = time.monotonic()
            if now - logged_at >= 30.0:
                logger.exception("Не удалось проверить фактическое число походов")
                self._march_observer_error_logged_at = now
            return None
        self._march_observer_error_logged_at = 0.0

        height, width = frame.shape[:2]
        x1, y1 = int(width * 1194 / 1280), int(height * 150 / 720)
        x2, y2 = int(width * 1274 / 1280), int(height * 188 / 720)
        roi_bgr = frame[y1:y2, x1:x2]
        if roi_bgr.size == 0:
            return None
        observed_capacity = self._detect_observed_march_capacity(
            roi_bgr,
            observers,
        )
        if (
            observed_capacity is not None
            and observed_capacity
            != int(getattr(self, "routine_max_marches", 5) or 5)
        ):
            previous_capacity = int(
                getattr(self, "routine_max_marches", 5) or 5
            )
            self.routine_max_marches = observed_capacity
            self.routine_march_deadlines = list(
                getattr(self, "routine_march_deadlines", ())
            )[:observed_capacity]
            self.routine_confirmed_march_floor = min(
                int(
                    getattr(self, "routine_confirmed_march_floor", 0)
                    or 0
                ),
                observed_capacity,
            )
            self.save_config()
            logger.info(
                "Observed march capacity updated: %s -> %s",
                previous_capacity,
                observed_capacity,
            )
        screen_roi = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        best_count = None
        best_score = -1.0
        for image in observers:
            template = self.template_cache.get_gray(image["path"])
            if template is None:
                continue
            if template.shape != screen_roi.shape:
                template = cv2.resize(template, (screen_roi.shape[1], screen_roi.shape[0]))
            if not screen_roi.size or not template.size:
                continue
            result = cv2.matchTemplate(screen_roi, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            if score >= float(image.get("observer_confidence", 0.70)) and score > best_score:
                best_score = float(score)
                best_count = int(image["march_count"])
        if best_count is not None:
            self.routine_zero_observation_started_at = 0.0
            self.routine_zero_observation_count = 0
            previous_count = int(getattr(self, "routine_display_active_marches", 0) or 0)
            if 0 < best_count < previous_count:
                observed_at = time.monotonic()
                candidate = getattr(self, "routine_lower_observation_value", None)
                if candidate != best_count:
                    self.routine_lower_observation_value = best_count
                    self.routine_lower_observation_started_at = observed_at
                    self.routine_lower_observation_count = 1
                    return previous_count
                self.routine_lower_observation_count = int(
                    getattr(self, "routine_lower_observation_count", 0) or 0
                ) + 1
                started_at = float(
                    getattr(self, "routine_lower_observation_started_at", 0.0) or 0.0
                )
                if (
                    self.routine_lower_observation_count < 3
                    or observed_at - started_at < MARCH_DECREASE_CONFIRMATION_SECONDS
                ):
                    return previous_count
            self.routine_lower_observation_value = None
            self.routine_lower_observation_started_at = 0.0
            self.routine_lower_observation_count = 0
            return best_count

        if self._world_map_visible_in_frame(frame):
            # Overlays and animated panel transitions can temporarily hide an
            # otherwise occupied counter. Only a stable absence may mean 0/5.
            observed_at = time.monotonic()
            started_at = float(
                getattr(self, "routine_zero_observation_started_at", 0.0) or 0.0
            )
            if started_at <= 0.0:
                self.routine_zero_observation_started_at = observed_at
                self.routine_zero_observation_count = 1
                return None
            self.routine_zero_observation_count = int(
                getattr(self, "routine_zero_observation_count", 0) or 0
            ) + 1
            if (
                self.routine_zero_observation_count >= 3
                and observed_at - started_at >= MARCH_ZERO_CONFIRMATION_SECONDS
            ):
                return 0
            return None

        self.routine_zero_observation_started_at = 0.0
        self.routine_zero_observation_count = 0
        return best_count

    def _detect_observed_march_capacity(self, roi_bgr, observers):
        """Read the denominator of the compact ``active/maximum`` counter.

        Account bonuses can change the live capacity between four and five.
        The configured observer images already contain clean numerator glyphs
        for digits 1-5, so reuse those glyphs as a tiny local OCR alphabet
        instead of assuming that every account has five squads.
        """
        if roi_bgr is None or not getattr(roi_bgr, "size", 0):
            return None
        reference_roi = cv2.resize(
            roi_bgr,
            (80, 38),
            interpolation=cv2.INTER_AREA,
        )

        def normalized_digit(image_bgr, left, right):
            if image_bgr is None or not getattr(image_bgr, "size", 0):
                return None
            reference = cv2.resize(
                image_bgr,
                (80, 38),
                interpolation=cv2.INTER_AREA,
            )
            hsv = cv2.cvtColor(reference, cv2.COLOR_BGR2HSV)
            bright_neutral = (
                (hsv[:, :, 2] >= 155)
                & (hsv[:, :, 1] <= 110)
            ).astype(np.uint8)
            digit = bright_neutral[:, left:right]
            ys, xs = np.where(digit)
            if not len(xs):
                return None
            digit = digit[
                int(ys.min()):int(ys.max()) + 1,
                int(xs.min()):int(xs.max()) + 1,
            ]
            return cv2.resize(
                digit,
                (16, 24),
                interpolation=cv2.INTER_NEAREST,
            )

        denominator = normalized_digit(reference_roi, 32, 44)
        if denominator is None:
            return None

        candidates = []
        for image in observers:
            try:
                digit_value = int(image.get("march_count"))
            except (TypeError, ValueError):
                continue
            template = None
            get_color = getattr(self.template_cache, "get_color", None)
            if callable(get_color):
                template = get_color(image["path"])
            if template is None:
                get_gray = getattr(self.template_cache, "get_gray", None)
                if callable(get_gray):
                    gray_template = get_gray(image["path"])
                    if gray_template is not None:
                        template = cv2.cvtColor(
                            gray_template,
                            cv2.COLOR_GRAY2BGR,
                        )
            numerator = normalized_digit(template, 15, 25)
            if numerator is None:
                continue
            mismatch = float(np.mean(numerator != denominator))
            candidates.append((mismatch, digit_value))

        if not candidates:
            return None
        mismatch, capacity = min(candidates)
        if mismatch > 0.28 or not 1 <= capacity <= 5:
            return None
        return capacity

    def _world_map_visible_in_frame(self, frame):
        height, width = frame.shape[:2]
        roi = frame[
            int(height * 380 / 720):int(height * 510 / 720),
            0:int(width * 120 / 1280),
        ]
        if roi.size == 0:
            return False
        candidates = [
            image for image in self.search_images
            if image.get("runtime_step") == "world_search"
            and image.get("description") == "Открыть поиск"
        ]
        for image in candidates:
            template = self.template_cache.get_color(image["path"])
            if template is None:
                continue
            if template.shape[0] > roi.shape[0] or template.shape[1] > roi.shape[1]:
                continue
            result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            if score >= 0.72:
                return True
        return False

    def reset_routine_marches(self):
        self.routine_march_deadlines = []
        self.routine_confirmed_march_floor = 0
        self.routine_march_observer_grace_until = 0.0
        self.routine_display_active_marches = 0
        self.save_config()
        self.set_status_message(
            self.tr('routine_marches', active=0, maximum=self.routine_max_marches),
            force=True,
        )

    def _register_routine_march(self, task, now=None):
        now = time.time() if now is None else float(now)
        self._ensure_routine_march_context()
        self.routine_march_deadlines = [
            deadline for deadline in self.routine_march_deadlines
            if float(deadline) > now
        ][:self.routine_max_marches]
        estimated_before = len(self.routine_march_deadlines)
        observed = self._detect_observed_marches()
        if observed is None:
            target_count = min(self.routine_max_marches, estimated_before + 1)
        else:
            # The counter is read after the send screen closes, so it already
            # includes this march and also reflects squads that returned while
            # the next target was being selected.
            target_count = min(self.routine_max_marches, max(1, int(observed)))
        duration = max(1.0, float(task.get("march_duration_minutes", 30.0)))
        kept_deadlines = self.routine_march_deadlines[:target_count]
        if len(kept_deadlines) < target_count:
            kept_deadlines.extend(
                now + duration * 60.0
                for _ in range(target_count - len(kept_deadlines))
            )
        self.routine_march_deadlines = kept_deadlines
        self.routine_confirmed_march_floor = target_count
        self.routine_display_active_marches = self.routine_confirmed_march_floor
        self.routine_march_observer_grace_until = max(
            self.routine_march_observer_grace_until,
            now + MARCH_OBSERVER_GRACE_SECONDS,
        )
        logger.info(
            "Confirmed march reserved: active=%s, observed=%s, observer grace=%.0f sec",
            self.routine_confirmed_march_floor,
            observed,
            MARCH_OBSERVER_GRACE_SECONDS,
        )
        self.save_config()
        return True

    def _scheduler_routine_tasks(self):
        if self.routine_only_task_id == "__account_switch__" and self.account_switch_task:
            return [dict(self.account_switch_task)]
        tasks = []
        for task in self.routine_tasks:
            runtime_task = dict(task)
            runtime_task["group"] = effective_task_group(task)
            has_templates = task.get("id") in {"game_login", "mysterious_merchant", "trucks"} or any(
                image.get("group") == runtime_task["group"] and image.get("enabled", True)
                for image in self.search_images
            )
            runtime_task["enabled"] = bool(
                is_task_effectively_enabled(task)
                and self.groups.get(runtime_task.get("group"), True)
                and (self.routine_only_task_id in (None, task.get("id")))
                and has_templates
            )
            # The radar block must always reach its final squad check.  The
            # task itself can then settle safely when every squad is busy and
            # still hand control to the post-radar reward pass.
            if task.get("id") == "radar_marches":
                runtime_task["uses_march"] = False
            tasks.append(runtime_task)
        return tasks

    def _clear_routine_coordinate_blocks(self, task):
        """Forget anti-loop clicks from the previous pass of the same task."""
        template_ids = set()
        for image in self.get_routine_templates(task, active_only=False):
            identifier = image.get("uid") or image.get("path")
            if identifier:
                template_ids.add(identifier)
        is_radar = is_radar_task_id(task.get("id"))
        removed = 0
        for key in list(self.blocked_coords):
            prefix = key[0] if isinstance(key, tuple) and key else key
            if prefix in template_ids or (is_radar and str(prefix).startswith("radar_dynamic")):
                del self.blocked_coords[key]
                removed += 1
        if removed:
            logger.info(
                "Cleared %s stale coordinate blocks for routine %s",
                removed,
                task.get("id"),
            )

    def _skip_satisfied_gathering_boost(self, boost_deadline, now):
        """Treat an already-active gathering boost as complete for this pass."""
        if (
            float(boost_deadline or 0.0) <= float(now)
            or self.routine_only_task_id is not None
            or self.routine_forced_task_queue
            or bool(getattr(self, "routine_radar_return_hold", False))
            or not self.routine_tasks
        ):
            return False
        start_index = int(self.current_routine_index or 0) % len(self.routine_tasks)
        for offset in range(len(self.routine_tasks)):
            index = (start_index + offset) % len(self.routine_tasks)
            task = self.routine_tasks[index]
            if not is_task_effectively_enabled(task):
                continue
            if not self.groups.get(effective_task_group(task), True):
                continue
            if str(task.get("id") or "") != "gathering_boost":
                return False
            self.current_routine_index = (index + 1) % len(self.routine_tasks)
            self.set_status_message(
                "Усиление сбора уже активно: продолжаю очередь ресурсов",
                force=True,
            )
            logger.info(
                "Active gathering boost deferred until %.0f; ordered queue advances to the next task",
                float(boost_deadline),
            )
            return True
        return False

    def _defer_due_ordinary_marches_when_full(
        self,
        runtime_tasks,
        now,
        active_marches,
    ):
        """Advance past due ordinary marches when every squad is occupied.

        Radar marches are deliberately excluded: an active or returning radar
        squad must keep the queue on the radar block. Ordinary gathering and
        combat tasks are deferred so they cannot make the status jump to a
        daily timer while the current account pass is still incomplete.
        """
        if (
            int(active_marches or 0) < int(self.routine_max_marches)
            or self.routine_only_task_id is not None
            or self.routine_forced_task_queue
            or bool(getattr(self, "routine_radar_return_hold", False))
            or not runtime_tasks
        ):
            return False

        deferred_ids = []
        for _attempt in range(len(runtime_tasks)):
            start_index = int(self.current_routine_index or 0) % len(runtime_tasks)
            index = next(
                (
                    (start_index + offset) % len(runtime_tasks)
                    for offset in range(len(runtime_tasks))
                    if is_task_effectively_enabled(
                        runtime_tasks[(start_index + offset) % len(runtime_tasks)]
                    )
                ),
                None,
            )
            if index is None:
                break
            task = runtime_tasks[index]
            task_id = str(task.get("id") or "")
            deadline = float(self.routine_next_run.get(task_id, 0.0) or 0.0)
            if (
                task_id == "radar_marches"
                or not task.get("uses_march", False)
                or deadline > float(now)
            ):
                break

            self.current_routine_index = index
            self.routine_next_run[task_id] = float(now) + 60.0
            self.routine_last_outcome = {
                "task_id": task_id,
                "outcome": "deferred_no_squad",
                "reason": "all_ordinary_marches_busy",
                "completed_steps": [],
                "actions": 0,
            }
            logger.info(
                "Routine %s deferred before launch because every ordinary squad is busy; ordered queue advances",
                task_id,
            )
            deferred_ids.append(task_id)
            self._advance_routine_after_outcome(task, now)
            if bool(getattr(self, "routine_pass_completed", False)):
                break

        if not deferred_ids:
            return False
        names = [
            self.get_routine_task_name(self.get_routine_task(task_id) or {"id": task_id})
            for task_id in deferred_ids
        ]
        self.set_status_message(
            "Все обычные отряды заняты: отложено "
            + ", ".join(names)
            + "; продолжаю очередь",
            force=True,
        )
        self.save_config()
        return True

    def _begin_due_routine(self, now):
        if self.current_routine_task_id:
            task = self.get_routine_task(self.current_routine_task_id)
            if task and task.get("enabled") and self.groups.get(effective_task_group(task), True):
                return task
            self.current_routine_task_id = None

        if (
            self.account_rotation_enabled
            and bool(getattr(self, "routine_pass_completed", False))
            and self.routine_only_task_id is None
            and int(getattr(self, "account_switch_failure_count", 0) or 0) > 0
        ):
            # This persisted latch covers both a reported failure and a process
            # restart during the one allowed switch attempt.  Do not fall
            # through to the normal scheduler and repeat the completed account.
            logger.error(
                "Automatic account rotation is blocked after its bounded switch attempt"
            )
            self.set_status_message(
                "Переключение аккаунта остановлено после одной попытки; нужен явный повтор",
                force=True,
            )
            self.routine_mode = False
            stop_event = getattr(self, "stop_event", None)
            if stop_event is not None:
                stop_event.set()
            return None

        if self._account_rotation_switch_due(now):
            current_profile = self.get_current_account() or {}
            next_profile = next_enabled_account(
                self.account_profiles,
                self.current_account_id,
                current_profile.get("ldplayer_index"),
            )
            if next_profile:
                if self._prepare_account_switch(next_profile):
                    # Persist the attempt before the external WebView flow so a
                    # process restart cannot start a duplicate transition.
                    self.account_switch_failure_count = 1
                    self.account_switch_retry_at = 0.0
                    self.save_config()
                else:
                    # Missing templates/credentials are not repaired by
                    # retrying the same switch every minute.  Block unattended
                    # rotation after one bounded attempt and surface the error.
                    self.account_switch_failure_count = 1
                    self.account_switch_retry_at = 0.0
                    logger.error(
                        "Automatic account switch preparation failed; rotation is blocked until an explicit retry"
                    )
                    self.save_config()
                    self.routine_mode = False
                    self.stop_event.set()
                    return None

        active_marches = self.get_active_marches(now)
        self._release_radar_return_hold(active_marches, now)
        if self._try_return_camped_zombie_march(active_marches, now):
            return None
        deployment_wait = max(0.0, self.routine_deployment_blocked_until - now)
        if deployment_wait > 0:
            active_marches = self.routine_max_marches
        boost_task = self.get_routine_task("gathering_boost")
        boost_deadline = gathering_boost_active_until(boost_task, now)
        if boost_deadline:
            self.routine_next_run["gathering_boost"] = max(
                boost_deadline,
                float(self.routine_next_run.get("gathering_boost", 0.0) or 0.0),
            )
            self._skip_satisfied_gathering_boost(boost_deadline, now)
        runtime_tasks = self._scheduler_routine_tasks()
        forced_index = None
        while self.routine_forced_task_queue:
            forced_task_id = str(self.routine_forced_task_queue[0] or "")
            forced_index = next(
                (
                    task_index
                    for task_index, candidate in enumerate(runtime_tasks)
                    if candidate.get("id") == forced_task_id
                    and candidate.get("enabled")
                ),
                None,
            )
            if forced_index is not None:
                self.routine_next_run[forced_task_id] = min(
                    float(self.routine_next_run.get(forced_task_id, now) or now),
                    float(now),
                )
                break
            logger.warning(
                "Skipping unavailable forced routine follow-up %s",
                forced_task_id,
            )
            self.routine_forced_task_queue.pop(0)
        if forced_index is None and self._defer_due_ordinary_marches_when_full(
            runtime_tasks,
            now,
            active_marches,
        ):
            return None
        index = forced_index
        if index is None:
            index = pick_due_task_index(
                runtime_tasks,
                self.routine_next_run,
                self.current_routine_index,
                now,
                active_marches=active_marches,
                max_marches=self.routine_max_marches,
            )
        if index is None:
            next_task, wait_seconds = next_due_task(
                runtime_tasks,
                self.routine_next_run,
                now,
                active_marches=active_marches,
                max_marches=self.routine_max_marches,
                start_index=self.current_routine_index,
            )
            # Cooldowns belong to later passes.  Once an account pass has
            # started, a stale/future deadline at the visible queue pointer
            # must not park the whole account for minutes or hours.  Preserve
            # the deadline, record a deferral, and continue in saved order.
            # The atomic radar return hold is the sole timed exception.
            if (
                next_task is not None
                and float(wait_seconds or 0.0) > 0.0
                and self.account_rotation_enabled
                and not bool(getattr(self, "routine_pass_completed", False))
                and self.routine_only_task_id is None
                and not self.routine_forced_task_queue
                and not (
                    str(next_task.get("id") or "") == "radar_marches"
                    and bool(getattr(self, "routine_radar_return_hold", False))
                )
            ):
                deferred_id = str(next_task.get("id") or "")
                deferred_index = next(
                    (
                        task_index
                        for task_index, candidate in enumerate(runtime_tasks)
                        if str(candidate.get("id") or "") == deferred_id
                    ),
                    int(self.current_routine_index or 0) % len(runtime_tasks),
                )
                self.current_routine_index = deferred_index
                self.routine_last_outcome = {
                    "task_id": deferred_id,
                    "outcome": "deferred_not_due",
                    "reason": "saved_cooldown_inside_active_pass",
                    "completed_steps": [],
                    "actions": 0,
                }
                logger.info(
                    "Routine %s has %.1f sec of saved cooldown inside the active account pass; ordered queue advances without waiting",
                    deferred_id,
                    float(wait_seconds),
                )
                self.set_status_message(
                    f"{self.get_routine_task_name(next_task)} ещё на повторе: откладываю и продолжаю очередь",
                    force=True,
                )
                self._advance_routine_after_outcome(next_task, now)
                self.save_config()
                return None
            if next_task is None:
                if deployment_wait > 0:
                    self.set_status_message(
                        f"Нет свободных отрядов: повторная проверка через {max(1, int(deployment_wait + 0.999))} сек",
                        force=True,
                    )
                else:
                    self.set_status_message(
                        self.tr('routine_full_marches', active=active_marches, maximum=self.routine_max_marches),
                        force=True,
                    )
            else:
                self.set_status_message(
                    self.tr(
                        'routine_waiting',
                        name=self.get_routine_task_name(next_task),
                        wait=format_wait_duration(wait_seconds, self.lang),
                        active=active_marches,
                        maximum=self.routine_max_marches,
                    ),
                    force=True,
                )
            return None

        task = runtime_tasks[index]
        if (
            task.get("id") == "mysterious_merchant"
            and not self.get_routine_templates(task, active_only=True)
            and not bool(task.get("settings", {}).get("visual_fallback", False))
        ):
            settings = task.get("settings", {})
            retry_minutes = min(
                1440.0,
                max(1.0, float(settings.get("arrival_retry_minutes", 60) or 60)),
            )
            self.routine_next_run[task["id"]] = float(now) + retry_minutes * 60.0
            self.current_routine_index = (index + 1) % len(runtime_tasks)
            self.routine_last_outcome = {
                "task_id": task["id"],
                "outcome": "deferred_unavailable",
                "reason": "merchant_not_arrived",
                "completed_steps": [],
                "actions": 0,
            }
            self.set_status_message(
                "Таинственный торговец ещё не прибыл: продолжаю строгую очередь",
                force=True,
            )
            logger.info(
                "Mysterious merchant has not arrived; task remains pending and the ordered queue advances"
            )
            self.save_config()
            return None
        if self.uses_adb and task.get("id") != "game_login":
            login_index = next(
                (
                    task_index
                    for task_index, candidate in enumerate(runtime_tasks)
                    if candidate.get("id") == "game_login" and candidate.get("enabled")
                ),
                None,
            )
            if login_index is not None:
                try:
                    foreground_package = self.adb_client.current_foreground_package()
                except Exception:
                    logger.exception("Failed to verify the foreground Android package")
                    foreground_package = None
                if foreground_package and foreground_package != GAME_PACKAGE:
                    logger.warning(
                        "Doomsday is not in foreground (%s); forcing the enabled login task",
                        foreground_package,
                    )
                    # Starting LDPlayer after an application or system crash
                    # leaves the saved ordered pass pointing at the interrupted
                    # task while Android is still on its launcher.  The login
                    # task is only a temporary recovery step in that case; it
                    # must return to the saved slot instead of advancing from
                    # game_login to vip_rewards and abandoning the rest of the
                    # pass until the next daily deadline.
                    if task.get("id") != "game_login":
                        self.routine_forced_task_active_id = "game_login"
                        self.routine_forced_task_return_index = int(index)
                        logger.info(
                            "Forced game login will return to interrupted routine %s at index %s",
                            task.get("id"),
                            index,
                        )
                    self.routine_next_run["game_login"] = 0.0
                    index = login_index
                    task = runtime_tasks[index]
        if (
            task.get("id") == "radar_marches"
            and self.account_rotation_enabled
            and not bool(task.get("settings", {}).get("dispatch_until_full", False))
            and not bool(
                getattr(self, "routine_radar_dispatched_this_pass", False)
            )
            and self._account_pass_remaining(now)
            < ACCOUNT_PASS_RADAR_RESERVE_SECONDS
        ):
            self.current_routine_index = int(index)
            self.routine_next_run["radar_marches"] = float(now) + 60.0
            self.routine_last_outcome = {
                "task_id": "radar_marches",
                "outcome": "deferred_pass_budget",
                "reason": "insufficient_radar_return_budget",
                "completed_steps": [],
                "actions": 0,
            }
            logger.warning(
                "Radar dispatch deferred: less than %.0f seconds remain in the account task budget",
                ACCOUNT_PASS_RADAR_RESERVE_SECONDS,
            )
            self._advance_routine_after_outcome(task, now)
            self.save_config()
            return None
        if (
            self.routine_forced_task_queue
            and task.get("id") == self.routine_forced_task_queue[0]
        ):
            self.routine_forced_task_active_id = str(task.get("id") or "")
            logger.info(
                "Starting forced post-radar follow-up %s",
                self.routine_forced_task_active_id,
            )
        self.current_routine_index = index
        self.current_routine_task_id = task["id"]
        self.routine_task_started_at = now
        if task.get("id") == "research":
            if float(
                getattr(self, "routine_research_budget_started_at", 0.0)
                or 0.0
            ) <= 0.0:
                self.routine_research_budget_started_at = float(now)
                # Persist before the visual flow starts so an application
                # restart cannot grant the same blocked research a fresh 90s.
                self.save_config()
        self.routine_last_action_time = now
        self.routine_current_had_action = False
        self.routine_current_action_count = 0
        self.routine_action_counts = {}
        self.routine_completed_steps = set()
        self.routine_last_outcome = {}
        self.routine_action_completes_task = False
        self.routine_action_failure_reason = ""
        self.routine_idle_confirmation_count = 0
        self.routine_home_recovery_attempted = False
        self.routine_login_restart_count = 0
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.routine_resource_retry_count = 0
        self.routine_radar_pending_marker_key = None
        self.routine_radar_confirmed_marker_keys = set()
        self.routine_radar_marker_failure_counts = {}
        self.routine_radar_in_progress_seen = False
        self.routine_collective_tutorial_taps = 0
        self.routine_fence_survivor_scan_index = 0
        self.routine_processing_factory_scan_index = 0
        self.routine_processing_factory_dynamic_selected_at = 0.0
        self.routine_processing_factory_dynamic_target = None
        self.routine_processing_factory_radial_attempted = False
        self.routine_processing_factory_recenter_attempted = False
        self.routine_merchant_build_menu_requested_at = 0.0
        self.routine_merchant_pending_target = None
        self.routine_merchant_scan_index = 0
        self.routine_merchant_catalog_scroll_attempts = 0
        self.routine_merchant_force_scan_move = False
        self.routine_merchant_shop_target = None
        self.routine_healing_pan_route = []
        self.routine_healing_replay_index = 0
        self.routine_healing_scan_index = 0
        self.routine_healing_settle_checks = 0
        self.routine_healing_overlay_recovery_done = False
        self.routine_healing_saved_route_rejected = False
        self.routine_healing_search_started = False
        self.routine_healing_recenter_attempted = False
        self._clear_routine_coordinate_blocks(task)
        template_count = len(self.get_routine_templates(task, active_only=True))
        self.set_status_message(
            self.tr(
                'routine_task_started',
                name=self.get_routine_task_name(task),
                group=task.get("group", ""),
                count=template_count,
            ),
            force=True,
        )
        if routine_requires_settlement(task) and not self._is_settlement_screen_visible():
            # A restart can resume the ordered pointer while the game is still
            # on a radar, refinery, alliance, or other previous-task screen.
            # Matching the new task there produced false actions (for example a
            # radar marker was accepted as an alliance project).  Establish the
            # settlement before enabling this task's templates.
            if self._is_main_screen_visible():
                start_screen_ready = self._switch_to_settlement_screen()
            else:
                start_screen_ready = self._return_to_main_screen(
                    max_back_steps=5,
                    require_settlement=True,
                )
            if start_screen_ready:
                self.routine_last_action_time = time.time()
                logger.info(
                    "Routine %s start screen normalized to the settlement",
                    task.get("id"),
                )
        if task.get("id") == "game_login" and not self._launch_game_for_login():
            self._defer_current_routine_no_action(now)
            return None
        if task.get("id") in WORLD_SEARCH_TASK_IDS and self._prepare_world_search_screen():
            self.routine_completed_steps.add("world_search")
            self.routine_current_had_action = True
            self.routine_last_action_time = time.time()
        return task

    def _account_rotation_cycle_ready(self):
        """Allow a profile switch only after the saved task order wraps."""
        return bool(
            bool(getattr(self, "routine_pass_completed", False))
            and not getattr(self, "current_routine_task_id", None)
            and not bool(getattr(self, "routine_radar_return_hold", False))
            and not getattr(self, "routine_forced_task_queue", [])
        )

    def _account_rotation_switch_due(self, now):
        """Switch immediately after a complete pass, independent of session age."""
        return bool(
            self.account_rotation_enabled
            and self.routine_only_task_id is None
            and not self.routine_forced_task_queue
            and int(getattr(self, "account_switch_failure_count", 0) or 0) == 0
            and self._account_rotation_cycle_ready()
            and float(now) >= float(getattr(self, "account_switch_retry_at", 0.0) or 0.0)
        )

    def _reset_account_pass_clock(self, now=None):
        """Start one restart-stable task budget for the selected account."""
        now = time.time() if now is None else float(now)
        self.account_pass_started_at = now
        self.account_pass_account_id = str(
            getattr(self, "current_account_id", "") or ""
        )
        self.account_session_deadline = now + ACCOUNT_PASS_TASK_HARD_SECONDS
        self.routine_research_budget_started_at = 0.0
        return self.account_session_deadline

    def _ensure_account_pass_clock(self, now=None):
        """Resume the saved clock without extending it after autostart."""
        now = time.time() if now is None else float(now)
        started_at = float(
            getattr(self, "account_pass_started_at", 0.0) or 0.0
        )
        clock_account_id = str(
            getattr(self, "account_pass_account_id", "") or ""
        )
        if (
            started_at <= 0.0
            or started_at > now + 60.0
            or clock_account_id
            != str(getattr(self, "current_account_id", "") or "")
        ):
            return self._reset_account_pass_clock(now)
        self.account_session_deadline = (
            started_at + ACCOUNT_PASS_TASK_HARD_SECONDS
        )
        return self.account_session_deadline

    def _account_pass_soft_due(self, now=None):
        now = time.time() if now is None else float(now)
        started_at = float(
            getattr(self, "account_pass_started_at", 0.0) or 0.0
        )
        return bool(
            started_at > 0.0
            and str(getattr(self, "account_pass_account_id", "") or "")
            == str(getattr(self, "current_account_id", "") or "")
            and now >= started_at + ACCOUNT_PASS_SOFT_SECONDS
        )

    def _account_pass_remaining(self, now=None):
        now = time.time() if now is None else float(now)
        started_at = float(
            getattr(self, "account_pass_started_at", 0.0) or 0.0
        )
        if (
            started_at <= 0.0
            or str(getattr(self, "account_pass_account_id", "") or "")
            != str(getattr(self, "current_account_id", "") or "")
        ):
            return float("inf")
        return max(
            0.0,
            started_at + ACCOUNT_PASS_TASK_HARD_SECONDS - now,
        )

    def _research_watchdog_due(self, now=None):
        """Return true once unconfirmed research exhausts its cumulative slot."""
        if str(getattr(self, "current_routine_task_id", "") or "") != "research":
            return False
        now = time.time() if now is None else float(now)
        started_at = float(
            getattr(self, "routine_research_budget_started_at", 0.0) or 0.0
        )
        # The account-pass soft target is diagnostic only.  Research often
        # appears after radar and donations, so a healthy long pass can reach
        # this task after that target.  Cutting the research watchdog short in
        # that case used to close a freshly opened tree before its first visual
        # inspection.  Only the task's own restart-stable budget may defer it.
        return bool(
            started_at > 0.0
            and now - started_at >= RESEARCH_UNCONFIRMED_BUDGET_SECONDS
        )

    def _drain_expired_account_pass(self, now=None):
        """Keep the saved-order pass running after its diagnostic target.

        The account clock is useful for detecting unexpectedly slow passes,
        but it must never make a working task skip every remaining ordered
        task.  Individual task watchdogs remain responsible for deferring a
        genuinely stalled task; rotation becomes eligible only after the
        pointer has naturally reached the end of the queue.
        """
        return False

    def _routine_idle_completion_ready(self, task):
        self.routine_idle_guard_visible = False
        if not task.get("complete_when_idle"):
            return False
        frame = None
        if self.uses_adb:
            frame = self._capture_adb_frame(force=True)
            black_ratio = float(np.mean(np.max(frame, axis=2) < 8))
            if black_ratio > 0.25:
                self.routine_idle_confirmation_count = 0
                logger.warning(
                    "Idle completion rejected: incomplete ADB frame, black ratio %.3f",
                    black_ratio,
                )
                return False
        guard_uid = str(task.get("idle_completion_guard_uid") or "")
        if not guard_uid:
            logger.warning("Routine %s has no idle completion guard", task.get("id"))
            return False
        guard_image = next(
            (image for image in self.search_images if str(image.get("uid") or "") == guard_uid),
            None,
        )
        if guard_image is None:
            logger.warning("Idle completion guard %s is missing", guard_uid)
            return False
        location, _bbox, _confidence = self._locate_image(guard_image)
        if location is None:
            self.routine_idle_confirmation_count = 0
            return False
        self.routine_idle_guard_visible = True
        for image in self.search_images:
            if (
                image.get("group") != effective_task_group(task)
                or not image.get("prevents_idle_completion")
                or not self._is_active(image)
            ):
                continue
            blocker_location, blocker_bbox, _blocker_confidence = self._locate_image(image)
            if blocker_location is not None:
                blocker_valid, reject_reason = self._validate_detected_match(
                    image,
                    blocker_bbox,
                )
                if not blocker_valid:
                    logger.info(
                        "Idle completion ignores rejected template %s: %s",
                        image.get("description"),
                        reject_reason,
                    )
                    continue
                if is_radar_task_id(task.get("id")):
                    if frame is None:
                        frame, _frame_origin = self._capture_screen_bgr(force=True)
                    if (
                        radar_marker_requires_notification(image, task.get("id"))
                        and not radar_marker_has_notification(frame, blocker_bbox)
                    ):
                        logger.info(
                            "Idle completion ignores radar-like shape without notification: %s",
                            image.get("description"),
                        )
                        continue
                if (
                    is_radar_task_id(task.get("id"))
                    and radar_marker_was_confirmed(
                        image.get("uid"),
                        blocker_location.x,
                        blocker_location.y,
                        self.routine_radar_confirmed_marker_keys,
                    )
                ):
                    logger.info(
                        "Idle completion ignores confirmed radar marker %s",
                        image.get("description"),
                    )
                    continue
                self.routine_idle_confirmation_count = 0
                logger.info(
                    "Idle completion blocked by visible template %s",
                    image.get("description"),
                )
                return False
        required = max(1, int(task.get("idle_confirmations", 1) or 1))
        self.routine_idle_confirmation_count += 1
        logger.info(
            "Idle completion confirmation %s/%s for %s",
            self.routine_idle_confirmation_count,
            required,
            task.get("id"),
        )
        return self.routine_idle_confirmation_count >= required

    def _routine_runtime_completion_ready(self, task):
        required_step = str(task.get("completion_runtime_step") or "")
        return not required_step or required_step in self.routine_completed_steps

    def _synchronize_radar_cycle_deadlines(self, now):
        radar_task_ids = [
            task["id"]
            for task in self.routine_tasks
            if is_radar_task_id(task.get("id"))
            and is_task_effectively_enabled(task)
        ]
        if not radar_task_ids:
            return
        deadlines = {
            task_id: float(self.routine_next_run.get(task_id, 0.0) or 0.0)
            for task_id in radar_task_ids
        }
        # Other due categories still belong to the current radar pass.
        if any(deadline <= float(now) for deadline in deadlines.values()):
            return
        next_cycle = min(deadlines.values())
        for task_id in radar_task_ids:
            self.routine_next_run[task_id] = next_cycle

    def _queue_post_radar_followups(self, task, now):
        """Keep post-radar checks due without moving them out of saved order."""
        if (
            str(task.get("id") or "") != "radar_marches"
            or self.routine_only_task_id is not None
        ):
            return False
        followups = []
        for task_id in ("radar_rewards", "completed_tasks"):
            candidate = self.get_routine_task(task_id)
            if not candidate or not is_task_effectively_enabled(candidate):
                continue
            if not self.groups.get(effective_task_group(candidate), True):
                continue
            followups.append(task_id)
            self.routine_next_run[task_id] = float(now)
        self.routine_forced_task_queue = []
        self.routine_forced_task_active_id = None
        self.routine_forced_task_return_index = None
        if followups:
            logger.info(
                "Post-radar checks remain due at their saved positions: %s",
                ", ".join(followups),
            )
        return False

    def _advance_routine_after_outcome(self, task, now):
        """Advance normally, except while completing the atomic radar block."""
        task_id = str(task.get("id") or "")
        if task_id == "research":
            self.routine_research_budget_started_at = 0.0
        if (
            task_id == "radar_marches"
            and bool(getattr(self, "routine_radar_in_progress_seen", False))
            and not bool(task.get("settings", {}).get("dispatch_until_full", False))
            and self.routine_forced_task_active_id != task_id
        ):
            # An active/returning radar squad belongs to the current radar
            # block. Keep the visible queue on radar_marches until its short
            # retry confirms that the squad is home; gathering must not start
            # while that radar action is still in flight.
            logger.info(
                "Radar march is active or returning; ordered queue remains on radar_marches"
            )
            self.routine_radar_return_hold = True
            self.routine_radar_return_active_seen = False
            self.routine_radar_return_observed_peak = 0
            return
        if self.routine_forced_task_active_id == task_id:
            # A mandatory post-radar task can also have its own later position
            # in the saved order.  If that position is still ahead before the
            # queue reaches radar_marches again, keep it due so its configured
            # slot cannot stop the rest of the pass on the new cooldown.
            if self.routine_forced_task_return_index is not None and self.routine_tasks:
                return_index = int(self.routine_forced_task_return_index) % len(
                    self.routine_tasks
                )
                task_index = next(
                    (
                        index
                        for index, candidate in enumerate(self.routine_tasks)
                        if candidate.get("id") == task_id
                    ),
                    None,
                )
                radar_index = next(
                    (
                        index
                        for index, candidate in enumerate(self.routine_tasks)
                        if candidate.get("id") == "radar_marches"
                    ),
                    None,
                )
                if task_index is not None and radar_index is not None:
                    task_distance = (task_index - return_index) % len(self.routine_tasks)
                    radar_distance = (radar_index - return_index) % len(self.routine_tasks)
                    if task_distance < radar_distance:
                        self.routine_next_run[task_id] = 0.0
                        logger.info(
                            "Forced post-radar task %s remains due at its later saved position",
                            task_id,
                        )
            if self.routine_forced_task_queue and self.routine_forced_task_queue[0] == task_id:
                self.routine_forced_task_queue.pop(0)
            self.routine_forced_task_active_id = None
            if self.routine_forced_task_queue:
                next_id = self.routine_forced_task_queue[0]
                next_index = next(
                    (
                        index
                        for index, candidate in enumerate(self.routine_tasks)
                        if candidate.get("id") == next_id
                    ),
                    None,
                )
                if next_index is not None:
                    self.current_routine_index = next_index
                    return
            if self.routine_forced_task_return_index is not None:
                self.current_routine_index = int(self.routine_forced_task_return_index)
            else:
                self.current_routine_index = (
                    self.current_routine_index + 1
                ) % len(self.routine_tasks)
            self.routine_forced_task_return_index = None
            return
        if self._queue_post_radar_followups(task, now):
            first_id = self.routine_forced_task_queue[0]
            first_index = next(
                (
                    index
                    for index, candidate in enumerate(self.routine_tasks)
                    if candidate.get("id") == first_id
                ),
                None,
            )
            if first_index is not None:
                self.current_routine_index = first_index
                return
        previous_index = int(self.current_routine_index or 0) % len(self.routine_tasks)
        self.current_routine_index = (previous_index + 1) % len(self.routine_tasks)
        if self.current_routine_index == 0 and self.routine_only_task_id is None:
            self.routine_pass_completed = True
            logger.info("Saved routine pass completed; account rotation is due now")

    def _release_radar_return_hold(self, active_marches, now):
        """Retry radar after a confirmed return, with a timed safety fallback."""
        if not bool(getattr(self, "routine_radar_return_hold", False)):
            return False
        radar_task = self.get_routine_task("radar_marches")
        if radar_task and bool(
            radar_task.get("settings", {}).get("dispatch_until_full", False)
        ):
            self.routine_radar_return_hold = False
            self.routine_radar_return_active_seen = False
            self.routine_radar_return_observed_peak = 0
            self.routine_next_run["radar_marches"] = float(now)
            self.save_config()
            logger.info(
                "Legacy radar return hold released; dispatch-until-full resumes immediately"
            )
            return True
        retry_at = float(self.routine_next_run.get("radar_marches", now) or now)
        active_count = int(active_marches or 0)
        observed_peak = max(
            0,
            int(
                getattr(self, "routine_radar_return_observed_peak", 0)
                or 0
            ),
        )
        active_seen = bool(
            getattr(self, "routine_radar_return_active_seen", False)
            or observed_peak > 0
        )
        if (
            active_count > observed_peak
            and float(now) < retry_at
        ):
            observed_peak = active_count
            self.routine_radar_return_observed_peak = observed_peak
            # Persist the post-dispatch counter so an autostart restart can
            # still recognize its later decrease instead of waiting for the
            # full five-minute safety interval.
            self.save_config()
        if active_count > 0:
            self.routine_radar_return_active_seen = True
            active_seen = True
        return_confirmed = bool(
            active_seen
            and (
                active_count == 0
                or (
                    observed_peak > 0
                    and active_count < observed_peak
                )
            )
        )
        if not return_confirmed and float(now) < retry_at:
            return False
        if not radar_task or not is_task_effectively_enabled(radar_task):
            self.routine_radar_return_hold = False
            self.routine_radar_return_active_seen = False
            self.routine_radar_return_observed_peak = 0
            return False
        dispatched_this_pass = bool(
            getattr(self, "routine_radar_dispatched_this_pass", False)
        )
        if dispatched_this_pass:
            # The pass is allowed to send exactly one radar squad.  The return
            # check above completes the atomic block; do not reopen the radar
            # and accidentally dispatch a second card five minutes later.
            self.routine_next_run["radar_marches"] = next_run_after_radar_pass(
                radar_task,
                float(now),
                has_in_progress=False,
            )
        else:
            # A squad that was already active before this pass still requires
            # one immediate radar check once it comes home.
            self.routine_next_run["radar_marches"] = float(now)
        self.routine_radar_return_hold = False
        self.routine_radar_return_active_seen = False
        self.routine_radar_return_observed_peak = 0
        if dispatched_this_pass:
            self.routine_radar_dispatched_this_pass = False
            self._queue_post_radar_followups(radar_task, float(now))
            previous_index = int(self.current_routine_index or 0) % len(
                self.routine_tasks
            )
            self.current_routine_index = (previous_index + 1) % len(
                self.routine_tasks
            )
            if self.current_routine_index == 0 and self.routine_only_task_id is None:
                self.routine_pass_completed = True
            self.save_config()
        logger.info(
            (
                "Radar squad return confirmed; the single dispatch is complete and the ordered queue can continue"
                if return_confirmed and dispatched_this_pass
                else (
                    "Radar safety interval elapsed; the single dispatch is complete and the ordered queue can continue"
                    if dispatched_this_pass
                    else (
                        "Radar squad return confirmed; radar_marches is due now before the ordered queue can continue"
                        if return_confirmed
                        else "Radar return-check interval elapsed; radar_marches is due now before the ordered queue can continue"
                    )
                )
            )
        )
        return True

    def _finish_current_routine(self, now=None, completion_clicked=False):
        now = time.time() if now is None else float(now)
        task = self.get_routine_task(self.current_routine_task_id)
        if not task:
            self.current_routine_task_id = None
            return

        if task.get("id") == "__account_switch__":
            target_account_id = task.get("settings", {}).get("target_account_id")
            probe_only = bool(task.get("settings", {}).get("probe_only", False))
            switch_error = self.account_switch_error
            switch_confirmed = self.account_switch_confirmed
            self.current_routine_task_id = None
            self.routine_current_had_action = False
            self.account_switch_task = None
            self.account_switch_error = switch_error
            self.account_switch_selected_at = 0.0
            self.account_switch_confirmed = bool(switch_confirmed and not switch_error)
            self.account_switch_probe_ready = False
            self.account_switch_auto_login_attempted = False
            self.routine_only_task_id = None
            switch_failed = False
            if switch_error:
                self.account_switch_failure_count = max(
                    1,
                    int(getattr(self, "account_switch_failure_count", 0) or 0),
                )
                switch_failed = True
                self.account_switch_last_result = switch_error
                self.set_status_message(switch_error, force=True)
            elif probe_only:
                count = len(self.account_switch_candidates)
                self.account_switch_last_result = f"Найдено аккаунтов Google: {count}"
                self.set_status_message(self.account_switch_last_result, force=True)
            elif target_account_id and switch_confirmed:
                self.select_account_profile(
                    target_account_id,
                    start_fresh_pass=True,
                )
                profile = find_account(self.account_profiles, target_account_id)
                self.account_switch_last_result = (
                    f"Аккаунт переключён: {profile.get('name')}" if profile else "Аккаунт переключён"
                )
                self.set_status_message(self.account_switch_last_result, force=True)
            else:
                self.account_switch_failure_count = max(
                    1,
                    int(getattr(self, "account_switch_failure_count", 0) or 0),
                )
                switch_failed = True
                self.account_switch_last_result = "Переключение не подтверждено главным экраном"
                self.set_status_message(self.account_switch_last_result, force=True)
            if switch_failed:
                logger.error(
                    "Account switch failed after one bounded attempt; automatic retry is blocked"
                )
                self.save_config()
            if switch_failed or not self.account_rotation_enabled:
                self.routine_mode = False
                self.stop_event.set()
            return

        completion_uid = task.get("completion_uid") or ""
        march_completion_step = str(task.get("march_completion_runtime_step") or "")
        should_count_march = bool(
            task.get("uses_march")
            and task.get("id") != "radar_marches"
            and self.routine_current_had_action
            and (completion_clicked or not completion_uid)
            and (
                not march_completion_step
                or march_completion_step in self.routine_completed_steps
            )
        )
        if should_count_march:
            self.routine_deployment_blocked_until = 0.0
            self._register_routine_march(task, now)

        if should_count_march and task.get("id") in {
            "food",
            "wood",
            "metal",
            "oil",
            "zombie_hunt",
            "collective_mind",
        }:
            self._interruptible_sleep(1.5)
            self._return_to_main_screen(max_back_steps=3)

        if task.get("id") in {
            "alliance_donations",
            "gathering_boost",
            "mail_rewards",
            "completed_tasks",
            "vip_rewards",
            "research",
            "heal",
            "train_infantry",
            "train_riders",
            "train_shooters",
            "train_vehicles",
            "processing_factory",
            "processing_contest",
            "wasteland_exploration",
        }:
            self._return_to_main_screen(
                require_settlement=routine_requires_settlement(task)
            )
        elif is_radar_task_id(task.get("id")) and not task.get("manual_screen_required", False):
            self._return_to_main_screen(require_settlement=True)

        radar_has_in_progress = bool(
            is_radar_task_id(task.get("id")) and self.routine_radar_in_progress_seen
        )
        if task.get("id") == "prize_hunt" and task.get("settings", {}).get("repeat_until_stopped", True):
            self.routine_next_run[task["id"]] = now
        elif is_radar_task_id(task.get("id")):
            self.routine_next_run[task["id"]] = next_run_after_radar_pass(
                task,
                now,
                has_in_progress=radar_has_in_progress,
            )
        elif task.get("id") == "gathering_boost":
            active_until = gathering_boost_active_until(task, now)
            if "use" in self.routine_completed_steps:
                duration_hours = gathering_boost_duration_hours(
                    self.routine_completed_steps,
                    task.get("settings", {}).get("boost_hours", 8.0),
                )
                active_until = now + duration_hours * 3600.0
                task.setdefault("settings", {})["active_until"] = active_until
            self.routine_next_run[task["id"]] = max(
                next_run_after_finish(task, now),
                active_until,
            )
            if active_until:
                self.save_config()
        elif (
            task.get("id") == "wasteland_exploration"
            and "stamina_empty" in self.routine_completed_steps
        ):
            try:
                retry_minutes = float(
                    task.get("settings", {}).get("stamina_retry_minutes", 12) or 12
                )
            except (TypeError, ValueError):
                retry_minutes = 12.0
            self.routine_next_run[task["id"]] = now + max(1.0, retry_minutes) * 60.0
        else:
            self.routine_next_run[task["id"]] = next_run_after_finish(task, now)
        if is_radar_task_id(task.get("id")):
            self._synchronize_radar_cycle_deadlines(now)
        next_run_minutes = max(
            1,
            int(
                (
                    max(0.0, self.routine_next_run[task["id"]] - now)
                    + 59.999
                )
                // 60.0
            ),
        )
        if task.get("id") == "heal":
            repeat_seconds = max(
                1,
                int(healing_repeat_delay(task) + 0.999),
            )
            self.set_status_message(
                f"Задача «{self.get_routine_task_name(task)}» завершена | "
                f"следующий запуск через {repeat_seconds} сек",
                force=True,
            )
        elif radar_has_in_progress:
            self.set_status_message(
                f"Радар: проход «{self.get_routine_task_name(task)}» завершён, "
                f"повтор через {next_run_minutes} мин",
                force=True,
            )
        else:
            self.set_status_message(
                self.tr(
                    'routine_completed',
                    name=self.get_routine_task_name(task),
                    minutes=(
                        next_run_minutes
                        if is_radar_task_id(task.get("id"))
                        or task.get("id") == "gathering_boost"
                        or task.get("id") == "wasteland_exploration"
                        else float(task.get("interval_minutes", 1.0))
                    ),
                ),
                force=True,
            )
        self.routine_last_outcome = {
            "task_id": str(task.get("id") or ""),
            "outcome": "completed",
            "completed_steps": sorted(self.routine_completed_steps),
            "actions": int(self.routine_current_action_count),
        }
        self._advance_routine_after_outcome(task, now)
        self.current_routine_task_id = None
        self.routine_current_had_action = False
        self.routine_current_action_count = 0
        self.routine_action_counts = {}
        self.routine_completed_steps = set()
        self.routine_action_failure_reason = ""
        self.routine_idle_confirmation_count = 0
        self.routine_home_recovery_attempted = False
        self.routine_login_restart_count = 0
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.routine_radar_in_progress_seen = False
        self.save_config()
        if self.routine_only_task_id == str(task.get("id") or ""):
            # A standalone task is a bounded one-shot run.  Its normal repeat
            # interval belongs to scheduled passes and must not look like a
            # hang (or repeat purchases) after a confirmed diagnostic result.
            completed_task_id = self.routine_only_task_id
            self.routine_only_task_id = None
            self.routine_mode = False
            self.stop_event.set()
            self._set_state(BotState.STOPPED)
            logger.info(
                "Standalone routine %s completed; one-shot run stopped",
                completed_task_id,
            )

    def _try_recover_current_routine_home(self, task):
        self.routine_home_recovery_attempted = True
        logger.info(
            "Routine %s found no first action; attempting one-time return to the main screen",
            task.get("id"),
        )
        self.set_status_message(self.tr('routine_recovering_home'), force=True)
        if not self._return_to_main_screen(
            max_back_steps=4,
            require_settlement=routine_requires_settlement(task),
        ):
            return False
        self.blocked_coords.clear()
        self.routine_last_action_time = time.time()
        return True

    def _try_recover_current_routine_idle_screen(self, task):
        self.routine_idle_recovery_attempted = True
        logger.info(
            "Routine %s is stuck outside its completion screen; returning home once",
            task.get("id"),
        )
        self.set_status_message(
            f"{self.get_routine_task_name(task)}: возвращаюсь из постороннего окна",
            force=True,
        )
        returned = self._return_to_main_screen(
            max_back_steps=5,
            require_settlement=routine_requires_settlement(task),
        )
        if not returned:
            # A world-to-settlement transition can finish just after the
            # first bounded recovery probe. Recheck once before treating the
            # card as a hard failure; the retry is still confirmation-gated.
            self._interruptible_sleep(0.8)
            returned = self._return_to_main_screen(
                max_back_steps=2,
                require_settlement=routine_requires_settlement(task),
            )
        if not returned:
            return False
        if is_radar_task_id(task.get("id")):
            marker_key = self.routine_radar_pending_marker_key
            if marker_key is not None:
                _marker_uid, marker_x, marker_y = marker_key
                retry_key = (round(float(marker_x) / 32.0), round(float(marker_y) / 32.0))
                failure_counts = getattr(self, "routine_radar_marker_failure_counts", None)
                if not isinstance(failure_counts, dict):
                    failure_counts = {}
                    self.routine_radar_marker_failure_counts = failure_counts
                failure_count = failure_counts.get(retry_key, 0) + 1
                failure_counts[retry_key] = failure_count
                if failure_count >= 2:
                    self._confirm_pending_radar_marker()
                    logger.warning(
                        "Radar marker did not produce a supported action twice; deferred: %s",
                        marker_key,
                    )
                    self.set_status_message(
                        "Радар: карточка дважды не ответила, перехожу к следующей",
                        force=True,
                    )
                else:
                    logger.info("Radar marker will receive one controlled retry: %s", marker_key)
                    self.routine_radar_pending_marker_key = None
            self.routine_completed_steps.clear()
        self.blocked_coords.clear()
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_last_action_time = time.time()
        return True

    def _retry_current_resource_search(self, task):
        if not resource_search_retry_due(
            task,
            self.routine_completed_steps,
            self.routine_resource_retry_count,
        ):
            return False

        self.routine_resource_retry_count += 1
        attempt = self.routine_resource_retry_count
        display = self.get_display_profile() if self.uses_adb else make_display_profile(1280, 720)
        swipes = (
            ((930, 360), (350, 360)),
            ((350, 360), (930, 360)),
            ((640, 560), (640, 260)),
        )
        swipe_from, swipe_to = swipes[(attempt - 1) % len(swipes)]
        from_x = int(round(swipe_from[0] * display.scale_x))
        from_y = int(round(swipe_from[1] * display.scale_y))
        to_x = int(round(swipe_to[0] * display.scale_x))
        to_y = int(round(swipe_to[1] * display.scale_y))

        self.set_status_message(
            f"\u0420\u0435\u0441\u0443\u0440\u0441 \u0437\u0430\u043d\u044f\u0442 \u0438\u043b\u0438 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d: \u0438\u0449\u0443 \u0434\u0440\u0443\u0433\u0443\u044e \u043a\u043b\u0435\u0442\u043a\u0443 ({attempt}/3)",
            force=True,
        )
        try:
            if self.uses_adb:
                self.adb_client.keyevent(4)
            else:
                pyautogui.press("escape")
            self._invalidate_capture()
            self._interruptible_sleep(0.6)
            if self.uses_adb:
                self.adb_client.swipe(from_x, from_y, to_x, to_y, 500)
            else:
                pyautogui.moveTo(from_x, from_y)
                pyautogui.dragTo(to_x, to_y, duration=0.5, button="left")
            self._invalidate_capture()
            self._interruptible_sleep(0.8)
            if not self._prepare_world_search_screen():
                logger.warning("Resource search retry %s could not reopen world search", attempt)
                return False
        except Exception:
            logger.exception("Resource search retry %s failed", attempt)
            return False

        self.routine_completed_steps = {"world_search"}
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.blocked_coords.clear()
        logger.info(
            "Resource search retry %s/3 prepared for %s without attacking",
            attempt,
            task.get("id"),
        )
        return True

    def _confirm_pending_radar_marker(self):
        self.routine_radar_in_progress_seen = True
        marker_key = self.routine_radar_pending_marker_key
        if marker_key is None:
            return
        self.routine_radar_confirmed_marker_keys.add(marker_key)
        _marker_uid, marker_x, marker_y = marker_key
        self.routine_radar_confirmed_marker_keys.add(("*", marker_x, marker_y))
        retry_key = (round(float(marker_x) / 32.0), round(float(marker_y) / 32.0))
        getattr(self, "routine_radar_marker_failure_counts", {}).pop(retry_key, None)
        if self.anti_loop_enabled:
            self.blocked_coords[marker_key] = time.time() + 900.0
        logger.info("Radar marker deferred for the current pass: %s", marker_key)
        self.routine_radar_pending_marker_key = None

    def _template_uid_is_visible(self, uid):
        image = next(
            (item for item in self.search_images if str(item.get("uid") or "") == str(uid)),
            None,
        )
        if image is None:
            return False
        location, bbox, _confidence = self._locate_image(image)
        if location is None or bbox is None:
            return False
        is_valid, _reason = self._validate_detected_match(image, bbox)
        return is_valid

    def _tap_radar_fallback(self, target, label, runtime_step, marker=False):
        target_x, target_y = map(int, target)
        coord_key = (
            "radar_dynamic" if marker else f"radar_dynamic_{runtime_step}",
            target_x,
            target_y,
        )
        if coord_key in self.blocked_coords:
            return False
        if marker and radar_marker_was_confirmed(
            coord_key[0],
            coord_key[1],
            coord_key[2],
            self.routine_radar_confirmed_marker_keys,
        ):
            return False

        try:
            if self.uses_adb:
                self.adb_client.tap(target_x, target_y)
            else:
                pyautogui.click(target_x, target_y)
        except Exception:
            logger.exception("Radar fallback click failed: %s", label)
            return False

        self._invalidate_capture()
        self.blocked_coords[coord_key] = time.time() + (8.0 if marker else 5.0)
        if marker:
            self.routine_radar_pending_marker_key = coord_key
        self.routine_completed_steps.add(runtime_step)
        if runtime_step == "radar_open":
            self.routine_idle_outside_since = 0.0
            self.routine_idle_recovery_attempted = False
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        self.set_status_message(f"Радар: {label} @ ({target_x}, {target_y})", force=True)
        logger.info("Radar fallback: %s @ (%s, %s)", label, target_x, target_y)
        self._interruptible_sleep(1.0)
        return True

    def _try_radar_in_progress_card_fallback(self, task):
        """Close a running radar card before any task template can reuse it."""
        # Rewards cards may legitimately contain time-like text while their
        # claim action is available. Let the reward templates inspect those
        # cards; this guard is only for task categories that must skip an
        # already-running march.
        if str(task.get("id") or "") not in {"radar_quick", "radar_marches"}:
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Radar countdown guard could not capture the screen")
            return False
        if (
            detect_radar_card_action_target(frame) is None
            or not radar_card_has_active_countdown(frame)
        ):
            return False

        self.routine_radar_in_progress_seen = True
        self._confirm_pending_radar_marker()
        try:
            if self.uses_adb:
                self.adb_client.keyevent(4)
            else:
                pyautogui.press("escape")
        except Exception:
            logger.exception("Could not close the radar card with an active countdown")
            return False
        self._invalidate_capture()
        self.routine_completed_steps.clear()
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.set_status_message(
            "Радар: активный таймер подтверждён, проверяю следующую карточку",
            force=True,
        )
        logger.info(
            "Active radar countdown confirmed; the running card was deferred before template actions"
        )
        self._interruptible_sleep(0.6)
        return True

    def _try_radar_visual_fallback(self, task):
        if (
            not is_radar_task_id(task.get("id"))
            or not task.get("settings", {}).get("visual_fallback", False)
        ):
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Radar fallback could not capture the screen")
            return False

        purchase_cancel_target = None
        if "radar_open" in self.routine_completed_steps:
            purchase_cancel_target = detect_radar_pass_purchase_cancel_target(frame)
        if purchase_cancel_target is not None:
            try:
                if self.uses_adb:
                    self.adb_client.tap(*purchase_cancel_target)
                else:
                    pyautogui.click(*purchase_cancel_target)
            except Exception:
                logger.exception("Radar pass purchase dialog could not be cancelled")
                return False
            self._invalidate_capture()
            self._interruptible_sleep(0.6)
            now = time.time()
            next_cycle = next_run_after_radar_pass(task, now, has_in_progress=False)
            self.routine_radar_in_progress_seen = False
            self._finish_current_routine(now=now)
            for radar_task in self.routine_tasks:
                if is_radar_task_id(radar_task.get("id")) and is_task_effectively_enabled(radar_task):
                    self.routine_next_run[radar_task["id"]] = next_cycle
            self.save_config()
            self.set_status_message(
                "Радар: покупка пропуска отменена, следующий проход по расписанию",
                force=True,
            )
            logger.warning(
                "Radar pass purchase dialog cancelled; all radar tasks deferred until %.0f",
                next_cycle,
            )
            return True

        radar_guard_uid = str(
            uuid.uuid5(
                PROFILE_NAMESPACE,
                f"{task.get('id')}:radar_screen_guard",
            )
        )
        radar_guard_visible = (
            self._template_uid_is_visible(radar_guard_uid)
            or radar_overview_is_visible(frame)
        )
        deployment_target = detect_radar_deployment_prompt_target(frame)
        if deployment_target is not None:
            task_id = str(task.get("id") or "")
            if task_id == "radar_marches":
                # Reaching this prompt proves the preceding world action was
                # accepted, even when its transient button was missed.
                self.routine_completed_steps.add("radar_action")
                if self._tap_radar_fallback(
                    deployment_target,
                    "создаю отряд для задания",
                    "radar_squad",
                ):
                    return True
            else:
                # Rewards and quick tasks must never deploy a squad. Defer the
                # marker for this pass, return home and continue with another.
                self._confirm_pending_radar_marker()
                self.set_status_message(
                    "Радар: карточка требует отряд, безопасно пропускаю",
                    force=True,
                )
                returned = self._return_to_main_screen(
                    max_back_steps=6,
                    require_settlement=True,
                )
                if returned:
                    self.routine_completed_steps.clear()
                    self.routine_last_action_time = time.time()
                    self.routine_idle_confirmation_count = 0
                    self.routine_current_had_action = True
                    return True
                return False

        squad_march_target = detect_radar_squad_march_target(frame)
        if (
            squad_march_target is not None
            and str(task.get("id") or "") == "radar_marches"
            and "radar_action" in self.routine_completed_steps
        ):
            # Reaching the populated squad panel proves that the create-squad
            # transition completed even when its short-lived template was not
            # visible.  Do not count the dispatch until the March panel itself
            # disappears after the click.
            self.routine_completed_steps.add("radar_squad")
            if self._tap_radar_fallback(
                squad_march_target,
                "отправляю сформированный радарный отряд",
                "radar_march",
            ):
                try:
                    after, _after_origin = self._capture_screen_bgr(force=True)
                except Exception:
                    logger.exception("Radar march confirmation could not capture the screen")
                    self.routine_completed_steps.discard("radar_march")
                    return True
                if (
                    detect_radar_squad_march_target(after) is not None
                    or not self._world_map_visible_in_frame(after)
                ):
                    self.routine_completed_steps.discard("radar_march")
                    logger.warning(
                        "Radar March button did not produce a confirmed world-map transition"
                    )
                    return True
                self.routine_completed_steps.update({"radar_squad", "radar_march"})
                self.routine_radar_dispatched_this_pass = True
                self.routine_radar_in_progress_seen = True
                self._confirm_pending_radar_marker()
                action_counts = getattr(self, "routine_action_counts", None)
                if not isinstance(action_counts, dict):
                    action_counts = {}
                    self.routine_action_counts = action_counts
                dispatches = int(action_counts.get("radar_dispatches", 0) or 0) + 1
                action_counts["radar_dispatches"] = dispatches
                self.set_status_message(
                    f"Радар: отправлено отрядов {dispatches}; ищу следующий свободный поход",
                    force=True,
                )
                logger.info(
                    "Radar squad dispatch %s confirmed; continuing until every march slot is full",
                    dispatches,
                )
                self._return_to_main_screen(max_back_steps=6, require_settlement=True)
                reset_radar_card_runtime_steps(self.routine_completed_steps)
                self.routine_last_action_time = time.time()
                self.routine_idle_confirmation_count = 0
                self.save_config()
                return True

        card_target = detect_radar_card_action_target(frame)
        if (
            task.get("id") == "radar_rewards"
            and card_target is not None
            and "radar_marker" in self.routine_completed_steps
        ):
            # Known reward templates are evaluated before this fallback. A
            # remaining Forward button therefore belongs to an unfinished or
            # wrong-category card and must not be opened by the rewards pass.
            self._confirm_pending_radar_marker()
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Radar rewards could not close a deferred card")
                return False
            self._invalidate_capture()
            self.routine_completed_steps.clear()
            self.routine_last_action_time = time.time()
            self.routine_idle_confirmation_count = 0
            self.routine_current_had_action = True
            self.set_status_message(
                "Радар: карточка не завершена, проверяю следующую",
                force=True,
            )
            self._interruptible_sleep(0.6)
            return True
        if (
            not radar_guard_visible
            and self.routine_completed_steps.issubset({"radar_open"})
            and self._is_settlement_screen_visible()
            and self._is_main_screen_visible()
        ):
            height, width = frame.shape[:2]
            open_target = (
                int(round(width * 110 / 1280.0)),
                int(round(height * 448 / 720.0)),
            )
            if self._tap_radar_fallback(
                open_target,
                "открываю радар с главного экрана",
                "radar_open",
            ):
                return True

        if task.get("id") == "radar_rewards":
            card_target = None
        if (
            card_target
            and "radar_marker" in self.routine_completed_steps
            and self._tap_radar_fallback(
                card_target,
                "нажата доступная кнопка карточки",
                "radar_forward",
            )
        ):
            return True

        if radar_guard_visible:
            for marker_target in detect_radar_notification_targets(frame):
                if self._tap_radar_fallback(
                    marker_target,
                    "выбрано новое задание по красной метке",
                    "radar_marker",
                    marker=True,
                ):
                    return True

        if (
            task.get("id") != "radar_rewards"
            and "radar_forward" in self.routine_completed_steps
        ):
            action_target = detect_radar_world_action_target(frame)
            if action_target and self._tap_radar_fallback(
                action_target,
                "нажата доступная кнопка задания",
                "radar_action",
            ):
                return True
        return False

    def _try_equipment_report_overlay(self, frame, context):
        """Collect upper free milestones and close the paid report overlay."""
        reward_target = detect_equipment_report_free_reward_target(frame)
        if reward_target is not None:
            if not self._tap_routine_fallback(
                reward_target,
                ("equipment_report_free_reward", context, *reward_target),
                "Вход в игру: забираю бесплатную награду отчёта",
            ):
                return False
            try:
                after, _origin = self._capture_screen_bgr(force=True)
            except Exception:
                logger.exception("Equipment report reward could not be verified")
                return True
            next_target = detect_equipment_report_free_reward_target(after)
            if next_target == reward_target:
                logger.warning(
                    "Equipment report free reward was not confirmed at %s; keeping the overlay open",
                    reward_target,
                )
            else:
                logger.info(
                    "Equipment report free reward confirmed at %s; next=%s",
                    reward_target,
                    next_target or "none",
                )
            return True

        close_target = detect_equipment_report_close_target(frame)
        if close_target is None:
            return False
        if not self._tap_routine_fallback(
            close_target,
            ("equipment_report_close", context, *close_target),
            "Вход в игру: бесплатные награды собраны, закрываю отчёт",
        ):
            return False
        logger.info(
            "Equipment report has no claimable free rewards; paid area skipped and overlay closed"
        )
        return True

    def _try_game_login_visual_fallback(self, task):
        if task.get("id") != "game_login":
            return False
        game_surface_visible = False
        if self.uses_adb and self.adb_client is not None:
            try:
                ui_xml = self.adb_client.ui_xml()
                saved_ids = extract_igg_id_targets(ui_xml)
                game_surface_visible = (
                    "unitySurfaceView" in ui_xml or 'content-desc="Game view"' in ui_xml
                )
            except (AdbError, OSError):
                saved_ids = []
            if saved_ids:
                target = tuple(saved_ids[0]["center"])
                if self._tap_routine_fallback(
                    target,
                    ("login_saved_igg_id", *target),
                    "Вход в игру: выбираю сохранённый IGG ID",
                ):
                    logger.info("Game login fallback selected the saved IGG ID row")
                    return True
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Game login fallback could not capture the screen")
            return False

        session_expired_target = detect_login_session_expired_ok_target(frame)
        if session_expired_target is not None and self._tap_routine_fallback(
            session_expired_target,
            ("login_session_expired", *session_expired_target),
            "Вход в игру: подтверждаю истёкшую сессию",
        ):
            logger.info("Game login fallback dismissed the expired session dialog")
            return True

        saved_account_target = detect_login_saved_account_continue_target(frame)
        if saved_account_target is not None and self._tap_routine_fallback(
            saved_account_target,
            ("login_saved_account_continue", *saved_account_target),
            "Вход в игру: подтверждаю сохранённый IGG Account",
        ):
            logger.info("Game login fallback confirmed the saved IGG account")
            return True

        # The visual event-overlay detector can be confused by bright event
        # icons on the normal settlement screen.  Once the home marker is
        # visible, leave the frame untouched so the stable-screen check below
        # can complete game_login instead of opening an event again.
        if self._is_main_screen_visible():
            return False

        if self._try_equipment_report_overlay(frame, "game_login"):
            return True

        overlay_target = detect_game_event_overlay_close_target(frame)
        if overlay_target is not None and self._tap_routine_fallback(
            overlay_target,
            ("game_login_event_overlay", *overlay_target),
            "Вход в игру: закрываю игровой баннер",
        ):
            logger.info("Game login fallback closed a blocking game event overlay")
            return True

        recovery_now = time.time()
        recovery_due = (
            not self.routine_home_recovery_attempted
            or recovery_now - self.routine_last_action_time >= 20.0
        )
        if (
            game_surface_visible
            and recovery_due
            and recovery_now - self.routine_task_started_at >= 45.0
        ):
            self.routine_home_recovery_attempted = True
            # A promo can open another Unity screen (for example the event
            # calendar) immediately after the first return. Throttle retries,
            # but do not make the first recovery the only possible recovery.
            self.routine_last_action_time = recovery_now
            self.set_status_message(
                "Вход в игру: закрываю внутренний экран и возвращаюсь домой",
                force=True,
            )
            if self._return_to_main_screen(max_back_steps=5):
                self.routine_last_action_time = time.time()
                logger.info("Game login recovered from an inner Unity screen")
                return True

        login_templates = (
            (
                "93b0417c-c8ce-5636-8f2d-8716f6c52bad",
                0.82,
                "Вход в игру: продолжаю последний вход IGG",
            ),
            (
                "6d4f72d8-c3fa-55c2-b175-f866fd14edf0",
                None,
                "Вход в игру: выбираю сохранённый вход Google",
            ),
            (
                "9d212722-ffc1-570c-8086-25a7f59e7fd4",
                None,
                "Вход в игру: выбираю сохранённый аккаунт Google",
            ),
        )
        images_by_uid = {
            str(image.get("uid") or ""): image
            for image in self.search_images
        }
        for uid, confidence_override, status_message in login_templates:
            image = images_by_uid.get(uid)
            if image is None:
                continue
            try:
                match_image = image
                if confidence_override is not None:
                    match_image = dict(image)
                    match_image["confidence"] = min(
                        float(image.get("confidence", confidence_override)),
                        confidence_override,
                    )
                location, bbox, _score = self._locate_image(match_image)
                if location is None or bbox is None:
                    continue
                is_valid, _reason = self._validate_detected_match(match_image, bbox)
                if not is_valid:
                    continue
                if image.get("action") == "google_account_select":
                    self._execute_action(image, location)
                    self.routine_last_action_time = time.time()
                    self.routine_idle_confirmation_count = 0
                    self.click_count += 1
                    logger.info("Game login fallback selected the first Google account")
                    return True
                if self._tap_routine_fallback(
                    (location.x, location.y),
                    ("game_login", uid),
                    status_message,
                ):
                    logger.info("Game login fallback selected saved sign-in: %s", uid)
                    return True
            except Exception:
                logger.exception("Game login fallback template failed: %s", uid)

        target = detect_blank_webview_close_target(frame)
        if target is None:
            return False
        if time.time() - self.routine_last_action_time < GAME_LOGIN_WEBVIEW_GRACE_SECONDS:
            return False
        target_x, target_y = map(int, target)
        coord_key = ("login_blank_webview", target_x, target_y)
        if coord_key in self.blocked_coords:
            return False
        try:
            if self.uses_adb:
                self.adb_client.tap(target_x, target_y)
            else:
                pyautogui.click(target_x, target_y)
        except Exception:
            logger.exception("Game login fallback could not close the blank webview")
            return False

        self._invalidate_capture()
        self.blocked_coords[coord_key] = time.time() + 5.0
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        self.set_status_message("Вход в игру: закрываю пустое окно авторизации", force=True)
        logger.info("Game login fallback closed blank webview at (%s, %s)", target_x, target_y)
        self._interruptible_sleep(2.0)
        return True

    def _try_account_switch_connection_recovery(self, task):
        """Dismiss an interrupted-session dialog and restart account navigation."""
        if task.get("id") != "__account_switch__":
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Account switch recovery could not capture the screen")
            return False

        target = detect_login_session_expired_ok_target(frame)
        if target is None:
            return False

        # Previous navigation coordinates must not block the retry.
        self.blocked_coords.clear()
        if not self._tap_routine_fallback(
            target,
            ("account_switch_connection_recovery", *target),
            "Соединение прервано: переподключаю аккаунт",
        ):
            return False

        completed_steps = set(getattr(self, "routine_completed_steps", ()))
        selected_igg_profile = (
            task.get("settings", {}).get("login_method") == "igg"
            and "account_switch_igg_id_selected" in completed_steps
        )
        if selected_igg_profile:
            # IGG can report an expired/interrupted session immediately after
            # accepting the saved ID even though the game has already switched
            # to that profile.  Preserve the verified navigation steps and
            # reopen the game so the main-screen check can confirm the target
            # instead of submitting the same credentials forever.
            self.account_switch_selected_at = time.time()
            self.account_switch_auto_login_attempted = True
            self.account_switch_error = ""
            self.routine_current_had_action = False
            self.routine_last_action_time = time.time()
            self.routine_completed_steps.add(
                "account_switch_igg_interrupted_after_selection"
            )
            try:
                if self.uses_adb:
                    self.adb_client.launch_package(GAME_PACKAGE)
            except AdbError:
                logger.exception(
                    "Account switch could not reopen the game after an interrupted IGG session"
                )
            logger.warning(
                "Interrupted IGG session followed saved-ID selection; reopening the game to verify the selected profile"
            )
            self._interruptible_sleep(10.0)
            return True

        self.account_switch_selected_at = 0.0
        self.account_switch_auto_login_attempted = False
        self.account_switch_error = ""
        self.routine_completed_steps = {
            step for step in self.routine_completed_steps
            if not str(step).startswith("account_switch_")
        }
        self.routine_current_had_action = False
        self.routine_last_action_time = time.time()
        logger.warning("Interrupted game session dismissed; account switch will retry")
        self._interruptible_sleep(5.0)
        return True

    def _try_account_switch_igg_game_confirmation(self, task):
        if task.get("id") != "__account_switch__":
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("IGG game confirmation could not capture the screen")
            return False

        target = detect_igg_game_login_ok_target(frame)
        login_progressed = (
            "account_switch_igg_game_confirmed" in self.routine_completed_steps
            or {
                "account_switch_igg_login_submitted",
                "account_switch_igg_id_selected",
            }.issubset(self.routine_completed_steps)
        )
        if target is None and login_progressed:
            if self._is_main_screen_visible():
                return False
            if self._try_equipment_report_overlay(frame, "account_switch_post_login"):
                self._interruptible_sleep(1.0)
                return True
            overlay_target = detect_game_event_overlay_close_target(frame)
            if overlay_target is not None and self._tap_routine_fallback(
                overlay_target,
                ("account_switch_post_login_overlay", *overlay_target),
                "Вход IGG завершён: закрываю игровой баннер",
            ):
                logger.info("Account switch closed a post-login game event overlay")
                self._interruptible_sleep(3.0)
                return True
        if target is None or not self._tap_routine_fallback(
            target,
            ("account_switch_igg_game_confirm", *target),
            (
                "IGG ID выбран: подтверждаю вход в игру"
                if task.get("settings", {}).get("login_method") == "igg"
                else "Закрываю отложенное подтверждение IGG"
            ),
        ):
            return False
        if task.get("settings", {}).get("login_method") != "igg":
            self.account_switch_selected_at = 0.0
            self.account_switch_auto_login_attempted = False
            self.routine_completed_steps = {
                step for step in self.routine_completed_steps
                if not str(step).startswith("account_switch_")
            }
            logger.info("Delayed IGG confirmation cleared before another login method")
            self._interruptible_sleep(8.0)
            return True
        self.routine_completed_steps.add("account_switch_igg_id_selected")
        self.routine_completed_steps.add("account_switch_igg_game_confirmed")
        self.account_switch_selected_at = time.time()
        logger.info("Final IGG game login confirmation accepted at %s", target)
        self._interruptible_sleep(8.0)
        return True

    def _account_switch_main_screen_confirmed(self, task):
        if not self.account_switch_selected_at or not self._is_main_screen_visible():
            return False
        settings = task.get("settings", {})
        if settings.get("login_method") == "igg":
            if "account_switch_igg_game_confirmed" in self.routine_completed_steps:
                return True
            if (
                "account_switch_igg_interrupted_after_selection"
                in self.routine_completed_steps
            ):
                return True
            return {
                "account_switch_igg_login_submitted",
                "account_switch_igg_id_selected",
            }.issubset(self.routine_completed_steps)
        return True

    def _try_account_switch_igg_rejected_login(self, task):
        if (
            task.get("id") != "__account_switch__"
            or task.get("settings", {}).get("login_method") != "igg"
            or not self.uses_adb
        ):
            return False
        try:
            target = extract_igg_unregistered_cancel_target(self.adb_client.ui_xml())
        except AdbError:
            return False
        if target is None:
            return False

        repeated = "account_switch_igg_rejection_dismissed" in self.routine_completed_steps
        if not self._tap_routine_fallback(
            target,
            ("account_switch_igg_rejection", *target),
            "IGG отклонил логин: закрываю сообщение",
        ):
            return False
        self.account_switch_selected_at = 0.0
        self.account_switch_auto_login_attempted = False
        self.routine_completed_steps.add("account_switch_igg_rejection_dismissed")
        if repeated:
            self.account_switch_error = "IGG отклонил логин: адрес не зарегистрирован"
            logger.warning("IGG rejected the account login twice; account switch stopped")
        else:
            logger.warning("IGG rejected the previous login; retrying the current profile once")
        self._interruptible_sleep(2.0)
        return True

    def _try_account_switch_visual_fallback(self, task):
        if task.get("id") != "__account_switch__" or self.account_switch_selected_at:
            return False
        if self.uses_adb:
            try:
                foreground = self.adb_client.current_foreground_package()
                if foreground != GAME_PACKAGE:
                    self.adb_client.launch_package(GAME_PACKAGE)
                    task.setdefault("settings", {})["_game_launch_at"] = time.time()
                    self._invalidate_capture()
                    self.routine_last_action_time = time.time()
                    self.set_status_message(
                        "Переключение аккаунта: запускаю Doomsday",
                        force=True,
                    )
                    logger.info(
                        "Account switch launched game from foreground package %s",
                        foreground or "unknown",
                    )
                    self._interruptible_sleep(10.0)
                    return True
            except AdbError:
                logger.exception("Account switch could not launch the game package")
                return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Account switch fallback could not capture the screen")
            return False

        # Promotional overlays can appear immediately after package launch,
        # before any IGG navigation step exists.  Previously the 90-second
        # loading grace returned early and left the bot staring at a visible
        # close button.  Handle the strictly recognised event overlay first.
        if self._try_equipment_report_overlay(frame, "account_switch_startup"):
            task.get("settings", {}).pop("_game_launch_at", None)
            self._interruptible_sleep(1.0)
            return True
        overlay_target = detect_game_event_overlay_close_target(frame)
        if overlay_target is not None and self._tap_routine_fallback(
            overlay_target,
            ("account_switch_startup_overlay", *overlay_target),
            "Переключение аккаунта: закрываю стартовый игровой баннер",
        ):
            logger.info("Account switch closed a startup game event overlay")
            task.get("settings", {}).pop("_game_launch_at", None)
            self._interruptible_sleep(2.0)
            return True

        # A reconnect can return to Doomsday's title screen instead of the
        # settlement.  Continue the already saved IGG sign-in from there;
        # Android Back would leave the game and restart the same loop.
        settings = task.get("settings", {})
        if (
            settings.get("login_method") == "igg"
            and "account_switch_navigation_started"
            not in getattr(self, "routine_completed_steps", ())
        ):
            title_login = next(
                (
                    image
                    for image in getattr(self, "search_images", ())
                    if str(image.get("uid") or "")
                    == "93b0417c-c8ce-5636-8f2d-8716f6c52bad"
                ),
                None,
            )
            if title_login is not None:
                try:
                    match_image = dict(title_login)
                    match_image["confidence"] = min(
                        float(title_login.get("confidence", 0.82)),
                        0.82,
                    )
                    location, bbox, _score = self._locate_image(match_image)
                    valid = False
                    if location is not None and bbox is not None:
                        valid, _reason = self._validate_detected_match(
                            match_image,
                            bbox,
                        )
                    if valid and self._tap_routine_fallback(
                        (location.x, location.y),
                        ("account_switch_title_igg",),
                        "Переключение аккаунта: продолжаю последний вход IGG",
                    ):
                        self.routine_completed_steps.add(
                            "account_switch_navigation_started"
                        )
                        settings.pop("_game_launch_at", None)
                        logger.info(
                            "Account switch resumed saved IGG sign-in from the title screen"
                        )
                        self._interruptible_sleep(4.0)
                        return True
                except Exception:
                    logger.exception(
                        "Account switch title-screen IGG recovery failed"
                    )
        main_screen_visible = self._is_main_screen_visible()
        settlement_visible = (
            self._is_settlement_screen_visible()
            if main_screen_visible
            else False
        )
        if not main_screen_visible or not settlement_visible:
            # Once account navigation has started, non-main screens are expected
            # (profile, settings and the IGG web view). Do not back out of them.
            if "account_switch_navigation_started" in getattr(
                self,
                "routine_completed_steps",
                (),
            ):
                return False
            game_launch_at = float(
                task.get("settings", {}).get("_game_launch_at", 0.0) or 0.0
            )
            if game_launch_at and time.time() - game_launch_at < 90.0:
                self.set_status_message(
                    "Переключение аккаунта: жду загрузку Doomsday",
                    force=True,
                )
                return False
            self.set_status_message(
                "Переключение аккаунта: возвращаюсь на главный экран",
                force=True,
            )
            if self._return_to_main_screen(max_back_steps=6, require_settlement=True):
                self.routine_last_action_time = time.time()
                logger.info("Account switch recovered from an inner game screen")
                return True
            return False
        scale_x = frame.shape[1] / 1280.0
        scale_y = frame.shape[0] / 720.0
        target = (int(round(48 * scale_x)), int(round(48 * scale_y)))
        if not self._tap_routine_fallback(
            target,
            ("account_switch_profile", *target),
            "Переключение аккаунта: открываю профиль командира",
        ):
            return False
        logger.info("Account switch fallback opened commander profile at %s", target)
        self._interruptible_sleep(1.0)
        return True

    def _try_account_switch_google_chooser(self, task):
        if (
            task.get("id") != "__account_switch__"
            or self.account_switch_selected_at
            or not self.uses_adb
            or task.get("settings", {}).get("login_method") != "google"
        ):
            return False
        try:
            if self.adb_client.current_foreground_package() != "com.google.android.gms":
                return False
            targets = extract_google_account_targets(self.adb_client.ui_xml())
        except AdbError:
            return False
        if not targets:
            return False

        candidates = [
            {"chooser_index": item["chooser_index"], "email": item["email"]}
            for item in targets
        ]
        self.account_switch_candidates = candidates
        settings = task.get("settings", {})
        if settings.get("probe_only", False):
            self.account_switch_probe_ready = True
            labels = ", ".join(
                f"№{item['chooser_index']} {mask_google_account(item['email'])}"
                for item in candidates
            )
            self.account_switch_last_result = f"Найдено аккаунтов Google: {len(candidates)}"
            message = self.account_switch_last_result
            if labels:
                message = f"{message} ({labels})"
            self.set_status_message(message, force=True)
            logger.info("Google account XML probe: %s", message)
            return True

        target_account_id = str(settings.get("target_account_id") or "")
        expected_login = self.get_account_login(target_account_id, "google").casefold()
        target = next(
            (item for item in targets if item["email"].casefold() == expected_login),
            None,
        ) if expected_login else None
        if expected_login and target is None:
            self.account_switch_error = "Нужный Google-аккаунт не найден в LDPlayer"
            self.set_status_message(self.account_switch_error, force=True)
            return False

        chooser_index = min(20, max(1, int(settings.get("chooser_index", 1))))
        if target is None and chooser_index > len(targets):
            self.account_switch_error = (
                f"Аккаунт Google №{chooser_index} не найден; доступно: {len(targets)}"
            )
            self.set_status_message(self.account_switch_error, force=True)
            return False

        target = target or targets[chooser_index - 1]
        chooser_index = int(target["chooser_index"])
        self.adb_client.tap(*target["center"])
        self._invalidate_capture()
        self.account_switch_selected_at = time.time()
        self.routine_last_action_time = time.time()
        self.click_count += 1
        self.set_status_message(
            f"Выбран аккаунт Google №{chooser_index}: {mask_google_account(target['email'])}",
            force=True,
        )
        logger.info(
            "Google account XML row %s selected at %s",
            chooser_index,
            target["center"],
        )
        self._interruptible_sleep(8.0)
        return True

    def _try_account_switch_saved_password(self, task):
        if (
            task.get("id") != "__account_switch__"
            or not self.account_switch_selected_at
            or self.account_switch_auto_login_attempted
            or not self.uses_adb
            or task.get("settings", {}).get("login_method") != "google"
        ):
            return False
        try:
            package = self.adb_client.current_foreground_package()
        except AdbError:
            return False
        if package not in {"com.google.android.gms", "com.google.android.gsf.login"}:
            return False

        try:
            ui_xml = self.adb_client.ui_xml()
            if not requires_google_reauthentication(ui_xml):
                return False
        except AdbError:
            return False

        if requires_manual_google_verification(ui_xml):
            self.account_switch_auto_login_attempted = True
            self.account_switch_error = (
                "Google требует разовую ручную проверку reCAPTCHA в LDPlayer"
            )
            self.set_status_message(self.account_switch_error, force=True)
            return True

        self.account_switch_auto_login_attempted = True
        account_id = str(task.get("settings", {}).get("target_account_id") or "")
        profile = find_account(self.account_profiles, account_id)
        if not profile or not profile.get("auto_login", False):
            self.account_switch_error = "Google требует подтверждение; автозаполнение отключено"
            return True
        if not self.account_has_saved_password(account_id):
            self.account_switch_error = "Google требует подтверждение; пароль профиля не сохранён"
            return True
        if not self.fill_google_credential(account_id, "password"):
            self.account_switch_error = "Автоматический ввод пароля Google не выполнен безопасно"
            return True

        self.account_switch_selected_at = time.time()
        self.routine_last_action_time = time.time()
        self.set_status_message("Пароль Google введён; проверяю главный экран", force=True)
        return True

    def _pause_for_manual_account_verification(self, task):
        if task.get("id") != "__account_switch__" or not self.uses_adb:
            return False
        try:
            ui_xml = self.adb_client.ui_xml()
        except AdbError:
            return False
        if not requires_manual_google_verification(ui_xml):
            return False

        self.account_switch_auto_login_attempted = True
        self.account_switch_error = (
            "Обнаружена CAPTCHA или проверка безопасности. "
            "Пройдите её вручную и нажмите «Продолжить»."
        )
        logger.warning("Manual account verification detected; automation paused")
        self.pause()
        self.set_status_message(self.account_switch_error, force=True)
        return True

    def _try_account_switch_igg_login(self, task):
        settings = task.get("settings", {})
        if (
            task.get("id") != "__account_switch__"
            or settings.get("login_method") != "igg"
            or self.account_switch_selected_at
            or self.account_switch_auto_login_attempted
            or not self.uses_adb
        ):
            return False
        try:
            if self.adb_client.current_foreground_package() != GAME_PACKAGE:
                return False
            form = extract_igg_login_form(self.adb_client.ui_xml())
        except AdbError:
            return False
        if not form:
            return False

        self.account_switch_auto_login_attempted = True
        account_id = str(settings.get("target_account_id") or "")
        profile = find_account(self.account_profiles, account_id)
        if not profile or not profile.get("auto_login", False):
            self.account_switch_error = "Автоматический вход IGG отключён для профиля"
            self.set_status_message(self.account_switch_error, force=True)
            return True
        try:
            self.fill_igg_credentials(account_id, form=form)
        except (AdbError, CredentialError, OSError, ValueError) as exc:
            logger.warning("Безопасный ввод IGG не выполнен: %s", exc)
            self.account_switch_error = str(exc)
            self.set_status_message(self.account_switch_error, force=True)
            return True

        self.account_switch_selected_at = time.time()
        self.routine_last_action_time = time.time()
        self.click_count += 1
        if not hasattr(self, "routine_completed_steps"):
            self.routine_completed_steps = set()
        self.routine_completed_steps.add("account_switch_igg_login_submitted")
        logger.info("IGG credentials submitted for account profile %s", account_id)
        self._interruptible_sleep(4.0)
        return True

    def _try_account_switch_igg_confirmation(self, task):
        settings = task.get("settings", {})
        if (
            task.get("id") != "__account_switch__"
            or settings.get("login_method") != "igg"
            or not self.uses_adb
        ):
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("IGG account confirmation fallback could not capture the screen")
            return False

        target = detect_login_saved_account_continue_target(frame)
        if target is None:
            return False

        if not self.account_switch_auto_login_attempted:
            other_target = (
                int(round(frame.shape[1] * 640 / 1280.0)),
                int(round(frame.shape[0] * 412 / 720.0)),
            )
            if not self._tap_routine_fallback(
                other_target,
                ("account_switch_igg_other", *other_target),
                "Выбираю вход в другой IGG Account",
            ):
                return False
            logger.info("IGG other-account form requested at %s", other_target)
            self._interruptible_sleep(3.0)
            return True

        if not self._tap_routine_fallback(
            target,
            ("account_switch_igg_continue", *target),
            "IGG подтвердил целевой аккаунт; продолжаю вход в игру",
        ):
            return False

        # Give the game a fresh loading window after the intermediate IGG page.
        self.account_switch_selected_at = time.time()
        logger.info("IGG account confirmation accepted at %s", target)
        self._interruptible_sleep(4.0)
        return True

    def _try_account_switch_igg_id_selection(self, task):
        settings = task.get("settings", {})
        if (
            task.get("id") != "__account_switch__"
            or settings.get("login_method") != "igg"
            or not self.uses_adb
        ):
            return False
        chooser_index = min(20, max(1, int(settings.get("chooser_index", 1))))
        try:
            targets = extract_igg_id_targets(self.adb_client.ui_xml())
        except AdbError:
            targets = []

        if targets:
            available_count = len(targets)
            target = targets[chooser_index - 1]["center"] if chooser_index <= available_count else None
        else:
            try:
                frame, _origin = self._capture_screen_bgr(force=True)
            except Exception:
                logger.exception("IGG ID selection fallback could not capture the screen")
                return False
            visual_target = detect_igg_id_selection_target(frame)
            available_count = 1 if visual_target else 0
            target = visual_target if chooser_index == 1 else None

        if not available_count:
            return False
        if target is None:
            self.account_switch_error = (
                f"IGG ID №{chooser_index} не найден; доступно: {available_count}"
            )
            self.set_status_message(self.account_switch_error, force=True)
            return False

        if not self._tap_routine_fallback(
            target,
            ("account_switch_igg_id", chooser_index, *target),
            f"Выбран сохранённый IGG ID №{chooser_index}; загружаю игру",
        ):
            return False
        self.routine_completed_steps.add("account_switch_igg_id_selected")
        self.account_switch_selected_at = time.time()
        logger.info("Saved IGG ID row %s selected at %s", chooser_index, target)
        self._interruptible_sleep(6.0)
        return True

    def _try_account_switch_return_to_main(self, task):
        if (
            task.get("id") != "__account_switch__"
            or "account_switch_igg_id_selected" not in self.routine_completed_steps
            or not self.account_switch_selected_at
        ):
            return False
        login_progressed = bool(
            {
                "account_switch_igg_login_submitted",
                "account_switch_igg_game_confirmed",
            }
            & self.routine_completed_steps
        )
        # A runner can be resumed while the saved-ID chooser is already open.
        # Selecting its only row may take noticeably longer to reveal the IGG
        # confirmation page.  Returning after the ordinary eight-second grace
        # abandons that page and leaves the switch permanently half-complete.
        return_grace = 8.0 if login_progressed else 30.0
        if time.time() - self.account_switch_selected_at < return_grace:
            return False
        if self._is_main_screen_visible():
            return False

        self.set_status_message(
            "Аккаунт выбран; возвращаюсь на главный экран",
            force=True,
        )
        if not self._return_to_main_screen(max_back_steps=8, require_settlement=True):
            return False
        if not login_progressed:
            self.account_switch_selected_at = 0.0
            self.account_switch_auto_login_attempted = False
            self.routine_completed_steps = {
                step
                for step in self.routine_completed_steps
                if not str(step).startswith("account_switch_")
            }
            self.routine_current_had_action = False
            self.routine_last_action_time = time.time()
            logger.warning(
                "Saved IGG chooser did not advance; account navigation will restart"
            )
            return True
        self.routine_completed_steps.update(
            {
                "account_switch_login_methods_closed",
                "account_switch_details_closed",
                "account_switch_settings_closed",
                "account_switch_profile_closed",
            }
        )
        self.account_switch_selected_at = time.time()
        logger.info("Account switch returned to the main screen through Android Back")
        return True

    def _tap_routine_fallback(self, target, coord_key, status_message):
        target_x, target_y = map(int, target)
        if coord_key in self.blocked_coords:
            return False
        try:
            if self.uses_adb:
                self.adb_client.tap(target_x, target_y)
            else:
                pyautogui.click(target_x, target_y)
        except Exception:
            logger.exception("Routine fallback click failed: %s", coord_key)
            return False

        self._invalidate_capture()
        self.blocked_coords[coord_key] = time.time() + 1.0
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        self.set_status_message(status_message, force=True)
        self._interruptible_sleep(1.2)
        return True

    def _dismiss_truck_arrival_overlay(self):
        """Close the truck arrival result without opening an item tooltip."""
        try:
            if self.uses_adb:
                self.adb_client.keyevent(4)
            else:
                pyautogui.press("esc")
        except Exception:
            logger.exception("Truck arrival overlay dismissal failed")
            return False

        attempts = int(
            getattr(self, "routine_truck_arrival_dismiss_attempts", 0) or 0
        ) + 1
        self.routine_truck_arrival_dismiss_attempts = attempts
        self._invalidate_capture()
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        self.set_status_message(
            f"Грузовики: закрываю окно награды, попытка {attempts}/3",
            force=True,
        )
        self._interruptible_sleep(1.2)
        return True

    def _try_mail_visual_fallback(self, task):
        if (
            task.get("id") != "mail_rewards"
            or "open_mail" in self.routine_completed_steps
            or not self._is_main_screen_visible()
        ):
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Mail fallback could not capture the main screen")
            return False

        height, width = frame.shape[:2]
        target = (
            int(round(width * 1241 / 1280.0)),
            int(round(height * 592 / 720.0)),
        )
        if not self._tap_routine_fallback(
            target,
            ("mail_open_fallback", *target),
            "\u041f\u043e\u0447\u0442\u0430: \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u044e \u043a\u043d\u043e\u043f\u043a\u0443 \u0441 \u0433\u043b\u0430\u0432\u043d\u043e\u0433\u043e \u044d\u043a\u0440\u0430\u043d\u0430",
        ):
            return False
        self.routine_completed_steps.add("open_mail")
        logger.info("Mail fallback opened the inbox at (%s, %s)", *target)
        return True

    def _try_fence_survivors_visual_fallback(self, task):
        """Sweep the shelter before confirming that the fence is empty."""
        if task.get("id") != "fence_survivors":
            return False
        if not self._is_settlement_screen_visible():
            return False

        scan_index = int(
            getattr(self, "routine_fence_survivor_scan_index", 0) or 0
        )
        if scan_index >= len(FENCE_SURVIVOR_SCAN_PATTERN):
            self.set_status_message(
                "Выжившие у забора: вся зона проверена, доступных наград нет",
                force=True,
            )
            logger.info(
                "Fence survivor scan completed after %s camera moves; no rewards remain",
                scan_index,
            )
            self._finish_current_routine(time.time())
            return True

        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Fence survivor scan could not capture the shelter")
            return False

        height, width = frame.shape[:2]
        swipes = {
            "left": ((980, 420), (360, 420)),
            "right": ((360, 420), (980, 420)),
            "up": ((640, 570), (640, 250)),
            "down": ((640, 250), (640, 570)),
        }
        direction = FENCE_SURVIVOR_SCAN_PATTERN[scan_index]
        (from_x, from_y), (to_x, to_y) = swipes[direction]
        from_x = int(round(from_x * width / 1280.0))
        from_y = int(round(from_y * height / 720.0))
        to_x = int(round(to_x * width / 1280.0))
        to_y = int(round(to_y * height / 720.0))
        try:
            if self.uses_adb:
                self.adb_client.swipe(from_x, from_y, to_x, to_y, 300)
            else:
                pyautogui.moveTo(from_x, from_y, duration=0.05)
                pyautogui.dragTo(to_x, to_y, duration=0.3, button="left")
        except Exception:
            logger.exception("Fence survivor camera movement failed")
            return False

        self.routine_fence_survivor_scan_index = scan_index + 1
        self._invalidate_capture()
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        self.set_status_message(
            "Выжившие у забора: осматриваю зону забора",
            force=True,
        )
        self._interruptible_sleep(0.45)
        logger.info(
            "Fence survivor camera moved %s (step %s/%s)",
            direction,
            self.routine_fence_survivor_scan_index,
            len(FENCE_SURVIVOR_SCAN_PATTERN),
        )
        return True

    def _try_processing_factory_visual_fallback(self, task):
        """Move the settlement camera until a processing factory is visible."""
        task_id = str(task.get("id") or "")
        if task_id not in {"processing_factory", "processing_contest"}:
            return False
        if "pan_north" not in self.routine_completed_steps:
            return False
        # Once the refinery header has been positively confirmed, navigation
        # is finished.  Re-entering the camera fallback here used to click a
        # stale settlement coordinate while the factory/contest screen was
        # already open, producing a tight loop instead of collecting rewards.
        if "open_refinery" in self.routine_completed_steps:
            return False
        if "select_refinery" in self.routine_completed_steps:
            selected_at = float(
                getattr(
                    self,
                    "routine_processing_factory_dynamic_selected_at",
                    0.0,
                )
                or 0.0
            )
            dynamic_target = getattr(
                self,
                "routine_processing_factory_dynamic_target",
                None,
            )
            if selected_at <= 0.0:
                # A calibrated settlement template can confirm
                # ``select_refinery`` without going through the dynamic
                # detector above.  Previously that left selected_at at zero,
                # so this branch returned forever while waiting for a radial
                # action that never appeared.  Give the expected radial menu
                # a short window, then reject the selection and resume the
                # bounded camera scan.
                selected_at = time.time()
                self.routine_processing_factory_dynamic_selected_at = selected_at
                logger.info(
                    "Processing factory template selection awaiting radial confirmation"
                )
            if (
                selected_at > 0.0
                and dynamic_target is not None
                and not getattr(
                    self,
                    "routine_processing_factory_radial_attempted",
                    False,
                )
                and time.time() - selected_at >= 0.8
            ):
                radial_target = (
                    int(dynamic_target[0]) - 58,
                    int(dynamic_target[1]) + 76,
                )
                self.routine_processing_factory_radial_attempted = True
                if not self._tap_routine_fallback(
                    radial_target,
                    ("processing_factory_dynamic_radial", *radial_target),
                    "Завод по обработке: открываю выбранное здание",
                ):
                    return False

                confirmation_image = next(
                    (
                        image
                        for image in self.search_images
                        if str(image.get("uid") or "")
                        == "152e2db2-317c-53cf-91a1-eb1dca8f3f30"
                    ),
                    None,
                )
                if confirmation_image is not None:
                    guard_location, guard_bbox, _score = self._locate_image(
                        confirmation_image
                    )
                    if guard_location is not None and guard_bbox is not None:
                        is_valid, _reason = self._validate_detected_match(
                            confirmation_image,
                            guard_bbox,
                        )
                        if is_valid:
                            self.routine_completed_steps.add("open_refinery")
                            self.routine_processing_factory_dynamic_selected_at = 0.0
                            logger.info(
                                "Processing factory dynamic radial opening confirmed at %s",
                                radial_target,
                            )
                            return True
                logger.warning(
                    "Processing factory dynamic radial opening was not confirmed at %s",
                    radial_target,
                )
                return True
            if time.time() - selected_at < 4.0:
                return False
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Could not close unexpected factory selection screen")
                return False
            self.routine_completed_steps.discard("select_refinery")
            self.routine_processing_factory_dynamic_selected_at = 0.0
            self.routine_processing_factory_dynamic_target = None
            self.routine_processing_factory_radial_attempted = False
            self._invalidate_capture()
            self.routine_last_action_time = time.time()
            logger.warning(
                "Dynamic processing factory selection was not confirmed; continuing camera scan"
            )
            self._interruptible_sleep(0.8)
            return True
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Processing factory scan could not capture the shelter")
            return False

        cancel_target = detect_back_confirmation_cancel_target(frame)
        if cancel_target is not None:
            if self._tap_routine_fallback(
                cancel_target,
                ("processing_factory_exit_cancel", *cancel_target),
                "Завод по обработке: закрываю окно выхода",
            ):
                logger.info("Processing factory closed the game-exit confirmation")
                return True

        if not self._is_settlement_screen_visible():
            return False

        scan_index = int(
            getattr(self, "routine_processing_factory_scan_index", 0) or 0
        )
        if scan_index >= len(PROCESSING_FACTORY_SCAN_PATTERN):
            self._defer_current_routine_unavailable(
                "завод не найден после полного обзора убежища",
                time.time(),
            )
            return True

        target = detect_processing_factory_target(frame)
        if target is not None:
            coord_key = (
                "processing_factory_dynamic",
                int(round(target[0] / 12.0)),
                int(round(target[1] / 12.0)),
            )
            if self._tap_routine_fallback(
                target,
                coord_key,
                "Завод по обработке: здание найдено, открываю",
            ):
                self.routine_completed_steps.add("select_refinery")
                self.routine_processing_factory_dynamic_selected_at = time.time()
                self.routine_processing_factory_dynamic_target = target
                self.routine_processing_factory_radial_attempted = False
                self.routine_processing_factory_scan_index = scan_index + 1
                logger.info(
                    "Processing factory selected by furnace cluster at %s",
                    target,
                )
                return True

        if scan_index % 12 == 0:
            self._save_routine_calibration_frame(
                task_id,
                f"scan_{scan_index:02d}",
                frame,
            )

        height, width = frame.shape[:2]
        swipes = {
            "left": ((980, 420), (360, 420)),
            "right": ((360, 420), (980, 420)),
            "up": ((640, 570), (640, 250)),
            "down": ((640, 250), (640, 570)),
        }
        direction = PROCESSING_FACTORY_SCAN_PATTERN[scan_index]
        (from_x, from_y), (to_x, to_y) = swipes[direction]
        from_x = int(round(from_x * width / 1280.0))
        from_y = int(round(from_y * height / 720.0))
        to_x = int(round(to_x * width / 1280.0))
        to_y = int(round(to_y * height / 720.0))
        try:
            if self.uses_adb:
                self.adb_client.swipe(from_x, from_y, to_x, to_y, 300)
            else:
                pyautogui.moveTo(from_x, from_y, duration=0.05)
                pyautogui.dragTo(to_x, to_y, duration=0.3, button="left")
        except Exception:
            logger.exception("Processing factory camera movement failed")
            return False

        self.routine_processing_factory_scan_index = scan_index + 1
        self._invalidate_capture()
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        self.set_status_message(
            "Завод по обработке: ищу здание по всему убежищу",
            force=True,
        )
        self._interruptible_sleep(0.55)
        logger.info(
            "Processing factory camera moved %s (scan step %s/%s)",
            direction,
            self.routine_processing_factory_scan_index,
            len(PROCESSING_FACTORY_SCAN_PATTERN),
        )
        return True

    def _save_routine_calibration_frame(self, task_id, stage, frame):
        """Persist one local screen for bot-only calibration of a new flow."""
        try:
            diagnostic_dir = Path(RUNTIME_DIR) / "live_diagnostics"
            diagnostic_dir.mkdir(parents=True, exist_ok=True)
            account_id = str(getattr(self, "current_account_id", "account") or "account")
            safe_account = "".join(
                char if char.isalnum() or char in "-_" else "_"
                for char in account_id
            )
            path = diagnostic_dir / f"{task_id}_{safe_account}_{stage}.png"
            cv2.imwrite(str(path), frame)
            logger.info(
                "Saved %s calibration frame for %s: %s",
                stage,
                task_id,
                path,
            )
            return path
        except Exception:
            logger.exception("Could not save %s calibration frame for %s", stage, task_id)
            return None

    def _try_trucks_visual_fallback(self, task):
        if task.get("id") != "trucks":
            return False
        settings = task.setdefault("settings", {})
        if "trucks_open" not in self.routine_completed_steps:
            if not (
                self._is_main_screen_visible()
                or self._is_settlement_screen_visible()
            ):
                return False
            try:
                frame, _origin = self._capture_screen_bgr(force=True)
            except Exception:
                logger.exception("Truck fallback could not capture the main screen")
                return False
            height, width = frame.shape[:2]
            target = (
                int(round(width * 184 / 1280.0)),
                int(round(height * 445 / 720.0)),
            )
            if not self._tap_routine_fallback(
                target,
                ("trucks_open_fallback", *target),
                "Грузовики: открываю центр отправки",
            ):
                return False
            self.routine_completed_steps.add("trucks_open")
            logger.info("Truck fallback opened the truck center at (%s, %s)", *target)
            return True

        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Truck fallback could not inspect the truck center")
            return False
        if (
            "truck_detail_check_open" in self.routine_completed_steps
            and "truck_dispatch_pending_verification"
            not in self.routine_completed_steps
            and truck_arrival_reward_is_visible(frame)
        ):
            # A coordinate tap can either miss the panel or open an item
            # tooltip.  Android Back closes both the tooltip and the result
            # overlay without triggering another gameplay action.
            self.routine_truck_arrival_dismiss_attempts = 0
            if not self._dismiss_truck_arrival_overlay():
                return False
            self.routine_truck_pending_kind = "occupied"
            self.routine_truck_pending_started_at = time.time()
            self.routine_truck_overview_confirmations = 0
            self.routine_completed_steps.add("truck_dispatch_pending_verification")
            logger.info("Arrived personal truck reward overlay collected")
            return True
        # The escort picker also has a red counter and no overview tabs, so it
        # can resemble Alliance Escort.  Preserve this more specific state
        # before applying the broad Alliance Escort rejection guard.
        if "truck_escort_selection_requested" in self.routine_completed_steps:
            self._save_routine_calibration_frame("trucks", "escort_selection", frame)
            if "truck_saved_formation_requested" not in self.routine_completed_steps:
                height, width = frame.shape[:2]
                formation_index = max(
                    1,
                    min(
                        2,
                        int(getattr(self, "routine_truck_formation_index", 1) or 1),
                    ),
                )
                formation_target = (
                    int(round(width * 1183 / 1280.0)),
                    int(round(height * (164 + (formation_index - 1) * 50) / 720.0)),
                )
                if not self._tap_routine_fallback(
                    formation_target,
                    (
                        "truck_select_saved_formation",
                        formation_index,
                        *formation_target,
                    ),
                    f"Грузовики: загружаю сохранённое построение {formation_index}",
                ):
                    return False
                self.routine_completed_steps.add("truck_saved_formation_requested")
                logger.info(
                    "Personal truck saved escort formation %s requested at (%s, %s)",
                    formation_index,
                    *formation_target,
                )
                return True
            self._save_routine_calibration_frame("trucks", "formation_selected", frame)
            target = detect_truck_escort_confirmation_target(frame)
            if target is None:
                self._defer_current_routine_unavailable(
                    "экран выбора сопровождения не подтверждён",
                    time.time(),
                    retry_delay=60.0,
                )
                return True
            if not self._tap_routine_fallback(
                target,
                ("truck_confirm_escort_selection", *target),
                "Грузовики: подтверждаю выбранное сопровождение",
            ):
                return False
            self.routine_completed_steps.discard("truck_escort_selection_requested")
            self.routine_completed_steps.discard("truck_saved_formation_requested")
            self.routine_completed_steps.add("truck_escort_selected")
            logger.info("Personal truck escort formation confirmed at (%s, %s)", *target)
            return True
        if truck_alliance_escort_is_visible(frame):
            if "truck_escort_selected" in self.routine_completed_steps:
                self._save_routine_calibration_frame(
                    "trucks", "escort_confirmation_unconfirmed", frame
                )
                formation_index = max(
                    1,
                    int(getattr(self, "routine_truck_formation_index", 1) or 1),
                )
                if formation_index < 2:
                    # A saved formation can consist entirely of heroes that are
                    # already riding in another truck.  The game then leaves the
                    # empty escort picker open after confirmation.  Try the
                    # second saved formation before safely deferring the task.
                    self.routine_truck_formation_index = formation_index + 1
                    self.routine_completed_steps.discard("truck_escort_selected")
                    self.routine_completed_steps.add("truck_escort_selection_requested")
                    self.routine_completed_steps.discard(
                        "truck_saved_formation_requested"
                    )
                    self.routine_last_action_time = time.time()
                    self.set_status_message(
                        "Грузовики: построение 1 занято, проверяю построение 2",
                        force=True,
                    )
                    logger.info(
                        "Personal truck formation %s did not close the empty escort picker; trying formation %s",
                        formation_index,
                        formation_index + 1,
                    )
                    return True
                self._defer_current_routine_unavailable(
                    "сохранённые построения заняты другими грузовиками",
                    time.time(),
                    retry_delay=60.0,
                )
                return True
            height, width = frame.shape[:2]
            target = (
                int(round(width * 42 / 1280.0)),
                int(round(height * 42 / 720.0)),
            )
            if not self._tap_routine_fallback(
                target,
                ("truck_leave_alliance_escort", *target),
                "Грузовики: возвращаюсь из сопровождения альянса к личным отправкам",
            ):
                return False
            self.routine_completed_steps.discard("truck_personal_slot_open")
            logger.warning(
                "Truck fallback rejected Alliance Escort; personal dispatch was not confirmed"
            )
            return True

        if "truck_dispatch_pending_verification" in self.routine_completed_steps:
            pending_kind = getattr(self, "routine_truck_pending_kind", "dispatch")
            if pending_kind == "occupied" and truck_arrival_reward_is_visible(frame):
                attempts = int(
                    getattr(self, "routine_truck_arrival_dismiss_attempts", 0) or 0
                )
                if attempts < 3:
                    if not self._dismiss_truck_arrival_overlay():
                        return False
                    logger.info(
                        "Truck arrival overlay still visible; Back dismissal retry %s/3",
                        attempts + 1,
                    )
                    return True
            if (
                truck_express_overview_is_visible(frame)
                and detect_truck_active_detail_back_target(frame) is None
            ):
                confirmations = int(
                    getattr(self, "routine_truck_overview_confirmations", 0) or 0
                ) + 1
                self.routine_truck_overview_confirmations = confirmations
                if confirmations < 2:
                    self.routine_last_action_time = time.time()
                    self._invalidate_capture()
                    self._interruptible_sleep(0.6)
                    logger.info("Truck overview confirmation 1/2")
                    return True
                counter_key = "max_collections" if pending_kind == "occupied" else "max_dispatches"
                actions = self.routine_action_counts.get(counter_key, 0) + 1
                self.routine_action_counts[counter_key] = actions
                self.routine_completed_steps.discard("truck_personal_slot_open")
                self.routine_completed_steps.discard("truck_detail_check_open")
                self.routine_completed_steps.discard("truck_dispatch_pending_verification")
                if pending_kind != "occupied":
                    # Escort state belongs to one truck only.  Keeping it after
                    # a confirmed dispatch made the next free slot press Start
                    # with an empty formation, so passes stopped at 1/4 even
                    # when two or three personal slots were available.
                    self.routine_completed_steps.discard("truck_escort_selected")
                    self.routine_completed_steps.discard(
                        "truck_escort_selection_requested"
                    )
                    self.routine_completed_steps.discard(
                        "truck_saved_formation_requested"
                    )
                    self.routine_truck_formation_index = 1
                self.routine_truck_overview_confirmations = 0
                self.routine_truck_arrival_dismiss_attempts = 0
                logger.info(
                    "Personal truck %s confirmed by return to overview (%s/%s)",
                    "collection/status action" if pending_kind == "occupied" else "dispatch",
                    actions,
                    int(settings.get(counter_key, 8 if pending_kind == "occupied" else 4) or 1),
                )
                if pending_kind == "occupied":
                    checked = set(getattr(self, "routine_truck_checked_slots", set()))
                    checked.add(int(getattr(self, "routine_truck_current_slot", -1)))
                    self.routine_truck_checked_slots = checked
                if (
                    pending_kind != "occupied"
                    and actions >= int(settings.get("max_dispatches", 4) or 4)
                ):
                    self.routine_completed_steps.add("trucks_complete")
                    self._finish_current_routine(time.time())
                return True
            self.routine_truck_overview_confirmations = 0
            pending_started_at = float(
                getattr(self, "routine_truck_pending_started_at", time.time()) or time.time()
            )
            if time.time() - pending_started_at < 8.0:
                self.routine_last_action_time = time.time()
                self._invalidate_capture()
                self._interruptible_sleep(0.8)
                logger.info("Waiting for personal truck action to return to overview")
                return True
            self._save_routine_calibration_frame("trucks", "dispatch_unconfirmed", frame)
            self._defer_current_routine_unavailable(
                "личная отправка не подтверждена",
                time.time(),
                retry_delay=60.0,
            )
            return True

        if "truck_detail_check_open" in self.routine_completed_steps:
            detail_opened_at = float(
                getattr(self, "routine_truck_detail_opened_at", time.time()) or time.time()
            )
            detail_age = time.time() - detail_opened_at
            if detail_age < 4.0:
                self.routine_last_action_time = time.time()
                self._invalidate_capture()
                self._interruptible_sleep(0.8)
                logger.info("Waiting for personal truck detail screen to stabilise")
                return True
            active_back_target = detect_truck_active_detail_back_target(frame)
            if active_back_target is not None:
                collect_target = detect_truck_ready_collection_target(frame)
                if collect_target is not None:
                    if not self._tap_routine_fallback(
                        collect_target,
                        ("truck_collect_ready", *collect_target),
                        "Грузовики: собираю готовый личный грузовик",
                    ):
                        return False
                    self.routine_truck_pending_kind = "occupied"
                    self.routine_truck_pending_started_at = time.time()
                    self.routine_truck_overview_confirmations = 0
                    self.routine_completed_steps.add("truck_dispatch_pending_verification")
                    logger.info(
                        "Ready personal truck collection requested at (%s, %s)",
                        *collect_target,
                    )
                    return True
                if not self._tap_routine_fallback(
                    active_back_target,
                    ("truck_active_detail_back", *active_back_target),
                    "Грузовики: личный грузовик ещё в пути",
                ):
                    return False
                checked = set(getattr(self, "routine_truck_checked_slots", set()))
                checked.add(int(getattr(self, "routine_truck_current_slot", -1)))
                self.routine_truck_checked_slots = checked
                self.routine_completed_steps.discard("truck_detail_check_open")
                logger.info("Active personal truck confirmed by world-map timer panel")
                return True
            if detail_age < 8.0:
                self.routine_last_action_time = time.time()
                self._invalidate_capture()
                self._interruptible_sleep(0.8)
                logger.info("Waiting for personal truck detail panel")
                return True
            self._save_routine_calibration_frame("trucks", "detail_unconfirmed", frame)
            self._defer_current_routine_unavailable(
                "карточка личного грузовика не подтверждена",
                time.time(),
                retry_delay=60.0,
            )
            return True

        if "truck_personal_slot_open" not in self.routine_completed_steps:
            self._save_routine_calibration_frame("trucks", "overview", frame)
            if not truck_express_overview_is_visible(frame):
                active_back_target = detect_truck_active_detail_back_target(frame)
                if active_back_target is not None:
                    if not self._tap_routine_fallback(
                        active_back_target,
                        ("truck_unexpected_detail_back", *active_back_target),
                        "Грузовики: закрываю карточку активного грузовика",
                    ):
                        return False
                    logger.info("Unexpected active truck detail panel closed safely")
                    return True
                return False
            checked = set(getattr(self, "routine_truck_checked_slots", set()))
            occupied = detect_truck_occupied_slot_targets(frame)
            for slot_index, occupied_target in enumerate(occupied):
                if slot_index in checked:
                    continue
                if not self._tap_routine_fallback(
                    occupied_target,
                    ("truck_check_occupied_slot", slot_index, *occupied_target),
                    "Грузовики: проверяю личный грузовик на готовность к сбору",
                ):
                    return False
                self.routine_truck_current_slot = slot_index
                self.routine_truck_detail_opened_at = time.time()
                self.routine_completed_steps.add("truck_detail_check_open")
                logger.info(
                    "Truck fallback opened occupied personal slot %s at (%s, %s)",
                    slot_index,
                    *occupied_target,
                )
                return True
            target = detect_truck_personal_slot_target(frame)
            if target is None:
                retry_minutes = min(
                    1440.0,
                    max(1.0, float(settings.get("retry_minutes", 60) or 60)),
                )
                self._defer_current_routine_unavailable(
                    "нет свободного личного слота грузовика",
                    time.time(),
                    retry_delay=retry_minutes * 60.0,
                )
                return True
            if not self._tap_routine_fallback(
                target,
                ("truck_personal_slot_fallback", *target),
                "Грузовики: открываю свободный слот личной отправки",
            ):
                return False
            self.routine_completed_steps.add("truck_personal_slot_open")
            logger.info("Truck fallback opened a personal shipment slot at (%s, %s)", *target)
            return True

        self._save_routine_calibration_frame("trucks", "personal_dispatch", frame)
        target = detect_truck_start_dispatch_target(frame)
        if target is not None:
            if "truck_escort_selected" not in self.routine_completed_steps:
                height, width = frame.shape[:2]
                escort_target = (
                    int(round(width * 637 / 1280.0)),
                    int(round(height * 435 / 720.0)),
                )
                if not self._tap_routine_fallback(
                    escort_target,
                    ("truck_open_escort_selection", *escort_target),
                    "Грузовики: выбираю сопровождение",
                ):
                    return False
                self.routine_completed_steps.add("truck_escort_selection_requested")
                logger.info("Personal truck escort selection requested at (%s, %s)", *escort_target)
                return True
            if not self._tap_routine_fallback(
                target,
                ("truck_start_personal_dispatch", *target),
                "Грузовики: отправляю личный грузовик",
            ):
                return False
            self.routine_completed_steps.add("truck_dispatch_pending_verification")
            self.routine_truck_pending_kind = "dispatch"
            self.routine_truck_pending_started_at = time.time()
            logger.info("Personal truck start requested at (%s, %s); awaiting overview confirmation", *target)
            return True
        retry_minutes = min(
            1440.0,
            max(1.0, float(settings.get("retry_minutes", 60) or 60)),
        )
        self._defer_current_routine_unavailable(
            "нужна калибровка экрана грузовиков",
            time.time(),
            retry_delay=retry_minutes * 60.0,
        )
        return True

    def _try_mysterious_merchant_visual_fallback(self, task):
        if task.get("id") != "mysterious_merchant":
            return False
        settings = task.setdefault("settings", {})
        task["timeout_seconds"] = max(180.0, float(task.get("timeout_seconds", 0) or 0))
        # Premium currency is blocked even if a legacy profile stored False.
        settings["avoid_gems"] = True
        if "merchant_absent_dialog_acknowledged" in self.routine_completed_steps:
            retry_minutes = min(
                1440.0,
                max(1.0, float(settings.get("arrival_retry_minutes", 60) or 60)),
            )
            self._defer_current_routine_unavailable(
                "merchant_absent",
                time.time(),
                retry_delay=retry_minutes * 60.0,
            )
            return True
        try:
            dialog_frame, _dialog_origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Merchant fallback could not inspect the away dialog")
            dialog_frame = None
        absent_target = detect_mysterious_merchant_absent_ok_target(dialog_frame)
        if absent_target is not None:
            if not self._tap_routine_fallback(
                absent_target,
                ("merchant_absent_dialog_ok", *absent_target),
                "Таинственный торговец отсутствует: закрываю уведомление",
            ):
                return False
            self.routine_completed_steps.add("merchant_absent_dialog_acknowledged")
            logger.info(
                "Mysterious Merchant away dialog acknowledged at (%s, %s)",
                *absent_target,
            )
            return True
        if "merchant_build_menu_open" not in self.routine_completed_steps:
            requested_at = float(
                getattr(self, "routine_merchant_build_menu_requested_at", 0.0)
                or 0.0
            )
            if requested_at > 0.0:
                try:
                    requested_frame, _requested_origin = self._capture_screen_bgr(
                        force=True
                    )
                except Exception:
                    logger.exception("Merchant fallback could not confirm the building list")
                    return False
                if settlement_building_catalogue_is_visible(requested_frame):
                    self.routine_completed_steps.add("merchant_build_menu_open")
                    self.routine_merchant_build_menu_requested_at = 0.0
                    logger.info("Merchant building catalogue opening confirmed")
                    return True
                if time.time() - requested_at < 2.5:
                    return False
                self.routine_merchant_build_menu_requested_at = 0.0
                logger.warning(
                    "Merchant building catalogue did not open; retrying the menu button"
                )
            if not (
                self._is_main_screen_visible()
                or self._is_settlement_screen_visible()
            ):
                return False
            try:
                frame, _origin = self._capture_screen_bgr(force=True)
            except Exception:
                logger.exception("Merchant fallback could not capture the main screen")
                return False
            height, width = frame.shape[:2]
            target = (
                int(round(width * 45 / 1280.0)),
                int(round(height * 445 / 720.0)),
            )
            if not self._tap_routine_fallback(
                target,
                ("merchant_build_menu_fallback", *target),
                "Таинственный торговец: открываю список сооружений",
            ):
                return False
            self.routine_merchant_build_menu_requested_at = time.time()
            logger.info("Merchant fallback requested the building list at (%s, %s)", *target)
            return True

        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Merchant fallback could not inspect the store building")
            return False
        merchant_screen_visible = mysterious_merchant_screen_is_visible(frame)
        if merchant_screen_visible and (
            self._is_main_screen_visible() or self._is_settlement_screen_visible()
        ):
            # The settlement shares enough of the merchant palette to look like
            # an offer grid.  Never turn its resource/HUD regions into purchase
            # targets after closing the building catalogue; open Shop first.
            merchant_screen_visible = False
            logger.info(
                "Merchant offer-grid false positive rejected on the settlement main screen"
            )
        if (
            merchant_screen_visible
            and "merchant_shop_open_requested" not in self.routine_completed_steps
        ):
            # A restart can leave another Shop subsection open.  Its dark
            # card grid can resemble the merchant page and yield zero
            # candidates, which must not be reported as a successful pass.
            merchant_screen_visible = False
            logger.info(
                "Merchant offer grid ignored until the verified Shop action is opened"
            )
        if merchant_screen_visible:
            targets = detect_mysterious_merchant_non_gem_offer_targets(frame)
            pending = getattr(self, "routine_merchant_pending_target", None)
            if pending is not None:
                still_present = any(
                    float(np.hypot(target[0] - pending[0], target[1] - pending[1])) <= 45.0
                    for target in targets
                )
                if still_present:
                    self._save_routine_calibration_frame(
                        "mysterious_merchant", "purchase_confirmation_unresolved", frame
                    )
                    self._defer_current_routine_unavailable(
                        "покупка за обычные ресурсы не подтверждена; диалог не нажимаю",
                        time.time(),
                        retry_delay=60.0,
                    )
                    return True
                purchases = self.routine_action_counts.get("max_purchases", 0) + 1
                self.routine_action_counts["max_purchases"] = purchases
                self.routine_merchant_pending_target = None
                logger.info(
                    "Non-gem merchant purchase confirmed (%s/%s)",
                    purchases,
                    int(settings.get("max_purchases", 20) or 20),
                )
                targets = detect_mysterious_merchant_non_gem_offer_targets(frame)
            purchases = self.routine_action_counts.get("max_purchases", 0)
            maximum = max(1, min(20, int(settings.get("max_purchases", 20) or 20)))
            if purchases >= maximum or not targets:
                self.routine_completed_steps.add("merchant_complete")
                logger.info(
                    "Mysterious Merchant complete: %s non-gem purchases; gem offers skipped",
                    purchases,
                )
                self._finish_current_routine(time.time())
                return True
            target = targets[0]
            if not self._tap_routine_fallback(
                target,
                ("merchant_non_gem_purchase", purchases, *target),
                "Таинственный торговец: покупаю предложение за обычные ресурсы",
            ):
                return False
            self.routine_merchant_pending_target = target
            logger.info("Requested strictly non-gem merchant offer at (%s, %s)", *target)
            return True

        if "merchant_shop_open_requested" in self.routine_completed_steps:
            if self.routine_only_task_id == "mysterious_merchant":
                # Diagnostic mode is outcome-driven: do not convert a failed
                # screen verification into a one-hour schedule wait.
                if not (
                    self._is_main_screen_visible()
                    or self._is_settlement_screen_visible()
                ):
                    try:
                        if self.uses_adb:
                            self.adb_client.keyevent(4)
                        else:
                            pyautogui.press("escape")
                    except Exception:
                        logger.exception("Merchant diagnostic could not close an unverified screen")
                        return False
                    self._invalidate_capture()
                    self._interruptible_sleep(0.7)
                self.routine_completed_steps.discard("merchant_shop_open_requested")
                self.routine_merchant_scan_index = 0
                logger.warning(
                    "Merchant screen was not verified; retrying immediately in merchant-only mode"
                )
                return True
            self._defer_current_routine_unavailable(
                "Таинственный торговец сейчас не доступен в магазине",
                time.time(),
                retry_delay=max(60.0, float(settings.get("arrival_retry_minutes", 60) or 60) * 60.0),
            )
            return True
        if (
            "merchant_shop_card_tapped" not in self.routine_completed_steps
            and not settlement_building_catalogue_is_visible(frame)
        ):
            # Never swipe the settlement or match a building card on the main
            # screen when the menu tap was ignored or the catalogue closed.
            self.routine_completed_steps.difference_update(
                {
                    "merchant_build_menu_open",
                    "merchant_catalog_economy_selected",
                    "merchant_catalog_reset",
                    "merchant_catalog_scrolled",
                }
            )
            self.routine_merchant_build_menu_requested_at = 0.0
            logger.warning(
                "Merchant catalogue disappeared before Shop selection; reopening it"
            )
            return True
        self._save_routine_calibration_frame("mysterious_merchant", "building_list_0", frame)
        height, width = frame.shape[:2]
        if "merchant_catalog_economy_selected" not in self.routine_completed_steps:
            # The game remembers the previous catalogue tab.  Explicitly
            # select Economy so a remembered Decorations tab can never be
            # mistaken for the Shop list.
            target = (
                int(round(width * 70 / 1280.0)),
                int(round(height * 255 / 720.0)),
            )
            if not self._tap_routine_fallback(
                target,
                ("merchant_catalog_economy", *target),
                "Таинственный торговец: выбираю экономические здания",
            ):
                return False
            self.routine_completed_steps.add("merchant_catalog_economy_selected")
            logger.info("Merchant catalogue Economy tab selected at (%s, %s)", *target)
            return True
        if "merchant_catalog_reset" not in self.routine_completed_steps:
            from_x = int(round(width * 1080 / 1280.0))
            to_x = int(round(width * 260 / 1280.0))
            y = int(round(height * 500 / 720.0))
            try:
                # The game remembers this list's old horizontal position.
                # Rewind it fully before using an account-independent route.
                for _attempt in range(6):
                    if self.input_backend == "adb" and self.adb_client:
                        self.adb_client.swipe(to_x, y, from_x, y, 350)
                    else:
                        pyautogui.moveTo(to_x, y, duration=0.05)
                        pyautogui.dragTo(from_x, y, duration=0.35, button="left")
                    self._invalidate_capture()
                    self._interruptible_sleep(0.25)
                self.routine_completed_steps.add("merchant_catalog_reset")
                logger.info("Merchant fallback reset the economic building list to its left edge")
                return True
            except Exception:
                logger.exception("Merchant building list could not reset to its left edge")
                return False

        if "merchant_catalog_scrolled" not in self.routine_completed_steps:
            from_x = int(round(width * 1080 / 1280.0))
            to_x = int(round(width * 260 / 1280.0))
            y = int(round(height * 500 / 720.0))
            try:
                # One full-width swipe places Shop/Supply Station on the
                # stable centre card.  A second swipe overshoots to the next
                # economic/event building and makes the map search start from
                # the wrong structure.
                for _attempt in range(1):
                    if self.input_backend == "adb" and self.adb_client:
                        self.adb_client.swipe(from_x, y, to_x, y, 450)
                    else:
                        pyautogui.moveTo(from_x, y, duration=0.05)
                        pyautogui.dragTo(to_x, y, duration=0.45, button="left")
                    self._invalidate_capture()
                    self._interruptible_sleep(0.6)
                self.routine_completed_steps.add("merchant_catalog_scrolled")
                logger.info("Merchant fallback scrolled the economic building list to Shop")
                return True
            except Exception:
                logger.exception("Merchant building list could not scroll to Shop")
                return False

        if "merchant_shop_card_tapped" not in self.routine_completed_steps:
            # The card spacing changes with the remembered list offset.  The
            # old fixed centre tap selected Police Station on a live account,
            # which sent the subsequent settlement scan to the wrong building.
            # Locate the SHOP sign inside the catalogue card itself instead.
            sign_template = cv2.imread(
                str(IMG_DIR / "system" / "merchant_shop_sign.jpg"),
                cv2.IMREAD_COLOR,
            )
            target = None
            sign_score = -1.0
            expected_shop_target = (
                int(round(width * 955 / 1280.0)),
                int(round(height * 415 / 720.0)),
            )
            if sign_template is not None and sign_template.size:
                target, sign_score = detect_merchant_shop_building_target(
                    frame,
                    sign_template,
                    min_score=0.33,
                    # After the explicit rewind and one full swipe, Shop is the
                    # fourth visible Economy card.  Restrict matching to that
                    # slot so the POLICE roof on the previous card cannot win.
                    search_bounds=(820, 280, 1120, 520),
                )
            logger.info(
                "Merchant catalogue Shop card match score=%.3f target=%s",
                sign_score,
                target,
            )
            if target is None:
                # Live IGG 6 proved the old whole-row weak match could select
                # Police Station at x=660.  The catalogue is already normalised
                # here, so the fourth card centre is a safer deterministic
                # fallback than additional carousel swipes.
                target = expected_shop_target
                logger.info(
                    "Merchant catalogue Shop sign was weak; using the verified "
                    "fourth Economy card at (%s, %s)",
                    *target,
                )
            if not self._tap_routine_fallback(
                target,
                ("merchant_shop_card", *target),
                "Таинственный торговец: нахожу здание магазина через каталог",
            ):
                return False
            self.routine_completed_steps.add("merchant_shop_card_tapped")
            logger.info(
                "Merchant fallback selected Shop from the building catalogue at (%s, %s)",
                *target,
            )
            return True

        self._save_routine_calibration_frame("mysterious_merchant", "shop_selected", frame)

        if "merchant_build_menu_closed" not in self.routine_completed_steps:
            target = (
                int(round(width * 34 / 1280.0)),
                int(round(height * 34 / 720.0)),
            )
            if not self._tap_routine_fallback(
                target,
                ("merchant_close_build_menu", *target),
                "Таинственный торговец: возвращаюсь к найденному зданию магазина",
            ):
                return False
            self.routine_completed_steps.add("merchant_build_menu_closed")
            return True

        if "merchant_catalog_selection_marker_checked" not in self.routine_completed_steps:
            # When an already-built Shop is selected from the catalogue, the
            # game marks the actual building with a unique gold diamond.  It
            # survives arbitrary account layouts and is the authoritative
            # target; tap the building immediately below it.
            selection_template = cv2.imread(
                str(IMG_DIR / "system" / "merchant_catalog_selection_marker.jpg"),
                cv2.IMREAD_COLOR,
            )
            selection_target = None
            selection_score = -1.0
            if selection_template is not None and selection_template.size:
                selection_target, selection_score = detect_merchant_shop_building_target(
                    frame,
                    selection_template,
                    min_score=0.65,
                    search_bounds=(180, 70, 1180, 500),
                )
            logger.info(
                "Merchant catalogue selection marker score=%.3f target=%s",
                selection_score,
                selection_target,
            )
            self.routine_completed_steps.add("merchant_catalog_selection_marker_checked")
            if selection_target is not None:
                if not self._tap_routine_fallback(
                    selection_target,
                    ("merchant_catalog_selection_marker", *selection_target),
                    "Таинственный торговец: открываю отмеченное здание магазина",
                ):
                    self.routine_completed_steps.discard(
                        "merchant_catalog_selection_marker_checked"
                    )
                    return False
                self.routine_merchant_shop_target = selection_target
                self.routine_completed_steps.add("merchant_shop_building_tapped")
                logger.info(
                    "Merchant selected Shop building at (%s, %s)",
                    *selection_target,
                )
                return True

        if (
            "merchant_shop_building_tapped" not in self.routine_completed_steps
            and "merchant_arrival_marker_checked" not in self.routine_completed_steps
        ):
            # Selecting Shop in the catalogue leaves the arrived merchant's
            # portrait marker above the correct building.  This is much more
            # stable than the tiny SHOP roof lettering and is independent of
            # where each account placed its buildings.
            marker_template = cv2.imread(
                str(IMG_DIR / "system" / "merchant_arrival_marker.jpg"),
                cv2.IMREAD_COLOR,
            )
            marker_target = None
            marker_score = -1.0
            if marker_template is not None and marker_template.size:
                marker_target, marker_score = detect_merchant_shop_building_target(
                    frame,
                    marker_template,
                    min_score=0.65,
                    search_bounds=(300, 70, 1240, 430),
                )
            logger.info(
                "Merchant arrival marker match score=%.3f target=%s",
                marker_score,
                marker_target,
            )
            self.routine_completed_steps.add("merchant_arrival_marker_checked")
            if marker_target is not None:
                if not self._tap_routine_fallback(
                    marker_target,
                    ("merchant_arrival_marker", *marker_target),
                    "Таинственный торговец: открываю найденный маркер торговца",
                ):
                    self.routine_completed_steps.discard("merchant_arrival_marker_checked")
                    return False
                self.routine_merchant_shop_target = marker_target
                self.routine_completed_steps.add("merchant_shop_building_tapped")
                logger.info(
                    "Merchant arrival marker selected at (%s, %s)",
                    *marker_target,
                )
                return True

        if (
            "merchant_shop_building_tapped" not in self.routine_completed_steps
            and "merchant_event_panel_checked" not in self.routine_completed_steps
        ):
            self.routine_completed_steps.add("merchant_event_panel_checked")
            event_panel_target = detect_settlement_event_panel_collapse_target(frame)
            if event_panel_target is not None:
                if not self._tap_routine_fallback(
                    event_panel_target,
                    ("merchant_event_panel_collapse", *event_panel_target),
                    "Таинственный торговец: скрываю панель событий над магазином",
                ):
                    self.routine_completed_steps.discard("merchant_event_panel_checked")
                    return False
                self._invalidate_capture()
                self._interruptible_sleep(0.6)
                logger.info(
                    "Merchant search collapsed the settlement event panel at (%s, %s)",
                    *event_panel_target,
                )
                return True

        if (
            "merchant_shop_building_tapped" not in self.routine_completed_steps
            and "merchant_selected_building_revealed" not in self.routine_completed_steps
        ):
            # The catalogue positions the selected building in the narrow map
            # strip above its cards.  Once the catalogue is closed it therefore
            # remains under the HUD.  Move map contents down exactly once so the
            # Shop sign and its radial actions become fully visible.
            from_x = int(round(width * 640 / 1280.0))
            from_y = int(round(height * 235 / 720.0))
            to_x = int(round(width * 640 / 1280.0))
            to_y = int(round(height * 565 / 720.0))
            try:
                if self.uses_adb:
                    self.adb_client.swipe(from_x, from_y, to_x, to_y, 350)
                else:
                    pyautogui.moveTo(from_x, from_y, duration=0.05)
                    pyautogui.dragTo(to_x, to_y, duration=0.35, button="left")
            except Exception:
                logger.exception("Merchant selected Shop could not be revealed")
                return False
            self.routine_completed_steps.add("merchant_selected_building_revealed")
            self._invalidate_capture()
            self.routine_last_action_time = time.time()
            self.routine_current_had_action = True
            self.click_count += 1
            self._interruptible_sleep(0.6)
            logger.info("Merchant selected Shop moved below the settlement HUD")
            return True

        if "merchant_shop_building_tapped" not in self.routine_completed_steps:
            # Never interpret a world-map HUD control as the Shop sign.  A
            # borderline sign match used to select the bottom-left Region
            # button, which moved the routine out of the settlement and made
            # every following camera correction useless.
            if not self._is_settlement_screen_visible():
                if not self._switch_to_settlement_screen():
                    return False
                self.routine_merchant_scan_index = 0
                self.routine_merchant_force_scan_move = False
                logger.info("Merchant search restored the settlement before locating Shop")
                return True
            sign_template = cv2.imread(
                str(IMG_DIR / "system" / "merchant_shop_sign.jpg"),
                cv2.IMREAD_COLOR,
            )
            building_template = cv2.imread(
                str(IMG_DIR / "system" / "merchant_shop_building.jpg"),
                cv2.IMREAD_COLOR,
            )
            building_target = None
            building_score = -1.0
            shop_marker_target = None
            feature_inliers = 0
            if building_template is not None and building_template.size:
                building_target, feature_inliers = detect_merchant_shop_feature_target(
                    frame,
                    building_template,
                    min_inliers=10,
                    search_bounds=(80, 75, 1210, 620),
                )
                logger.info(
                    "Merchant Shop feature match inliers=%s target=%s",
                    feature_inliers,
                    building_target,
                )
                if building_target is not None:
                    marker_template = cv2.imread(
                        str(IMG_DIR / "system" / "merchant_catalog_selection_marker.jpg"),
                        cv2.IMREAD_COLOR,
                    )
                    shop_marker_target = detect_shop_selection_marker_target(
                        frame,
                        building_target,
                        marker_template,
                    )
                    logger.info(
                        "Merchant Shop feature marker target=%s",
                        shop_marker_target,
                    )
                    if shop_marker_target is None:
                        # The bundled full-building reference is visually close
                        # to Equipment Repair on several accounts.  A high ORB
                        # count alone is therefore not authority to click it;
                        # require the catalogue selection marker or continue to
                        # the dedicated SHOP roof-sign detector below.
                        logger.info(
                            "Merchant feature candidate rejected without the "
                            "catalogue marker (%s inliers)",
                            feature_inliers,
                        )
                        building_target = None
            if building_target is None and building_template is not None and building_template.size:
                building_target, building_score = detect_merchant_shop_building_target(
                    frame,
                    building_template,
                    min_score=0.48,
                    search_bounds=(100, 80, 1200, 620),
                )
            logger.info(
                "Merchant full Shop building match score=%.3f target=%s",
                building_score,
                building_target,
            )
            if building_target is not None and shop_marker_target is not None:
                tap_target = shop_marker_target
                if not self._tap_routine_fallback(
                    tap_target,
                    ("merchant_full_shop_marker", *tap_target),
                    "Таинственный торговец: открываю найденный Магазин",
                ):
                    return False
                self.routine_completed_steps.add("merchant_shop_open_requested")
                logger.info(
                    "Merchant full Shop marker requested at (%s, %s)",
                    *shop_marker_target,
                )
                return True
            if sign_template is None or sign_template.size == 0:
                self._defer_current_routine_unavailable(
                    "не найден эталон вывески магазина",
                    time.time(),
                    retry_delay=60.0,
                )
                return True
            best_target, sign_score = detect_merchant_shop_building_target(
                frame,
                sign_template,
                # Alternate Shop levels have a different facade, but their
                # real roof word remains a strong 0.45 match.  Unrelated live
                # settlement signs stayed at 0.32 or below, so never restore
                # the old permissive action threshold.
                min_score=0.40,
                search_bounds=(180, 110, 1180, 590),
            )
            shop_match_confirmed = best_target is not None and sign_score >= 0.40
            if getattr(self, "routine_merchant_force_scan_move", False):
                self.routine_merchant_force_scan_move = False
                shop_match_confirmed = False
            logger.info(
                "Merchant Shop sign match score=%.3f target=%s",
                sign_score,
                best_target,
            )
            scan_index = int(getattr(self, "routine_merchant_scan_index", 0) or 0)
            self._save_routine_calibration_frame(
                "mysterious_merchant", f"shop_search_{scan_index:02d}", frame
            )
            if not shop_match_confirmed:
                scan_index = int(getattr(self, "routine_merchant_scan_index", 0) or 0)
                # Catalogue selection already centred Shop.  A short bounded
                # correction is sufficient; the old 96-step shelter snake only
                # hid bad catalogue coordinates and wasted several minutes.
                scan_pattern = (
                    "down",
                    "down",
                    "left",
                    "right",
                    "right",
                    "up",
                    "up",
                    "left",
                )
                if scan_index >= len(scan_pattern):
                    if self.routine_only_task_id == "mysterious_merchant":
                        self.routine_merchant_scan_index = 0
                        self.routine_completed_steps.difference_update(
                            {
                                "merchant_build_menu_open",
                                "merchant_catalog_reset",
                                "merchant_catalog_scrolled",
                                "merchant_shop_card_tapped",
                                "merchant_build_menu_closed",
                                "merchant_catalog_selection_marker_checked",
                                "merchant_arrival_marker_checked",
                                "merchant_event_panel_checked",
                                "merchant_selected_building_revealed",
                                "merchant_shop_building_tapped",
                            }
                        )
                        logger.warning(
                            "Merchant Shop was not found in one route; restarting the search immediately"
                        )
                        self._interruptible_sleep(0.7)
                        return True
                    self._defer_current_routine_unavailable(
                        "здание магазина не найдено после полного обхода убежища",
                        time.time(),
                        retry_delay=300.0,
                    )
                    return True
                direction = scan_pattern[scan_index]
                self.routine_merchant_scan_index = scan_index + 1
                swipes = {
                    "left": ((980, 420), (360, 420)),
                    "right": ((360, 420), (980, 420)),
                    "up": ((640, 570), (640, 250)),
                    "down": ((640, 250), (640, 570)),
                }
                (from_x, from_y), (to_x, to_y) = swipes[direction]
                from_x = int(round(from_x * width / 1280.0))
                from_y = int(round(from_y * height / 720.0))
                to_x = int(round(to_x * width / 1280.0))
                to_y = int(round(to_y * height / 720.0))
                try:
                    if self.uses_adb:
                        self.adb_client.swipe(from_x, from_y, to_x, to_y, 300)
                    else:
                        pyautogui.moveTo(from_x, from_y, duration=0.05)
                        pyautogui.dragTo(to_x, to_y, duration=0.3, button="left")
                except Exception:
                    logger.exception("Merchant Shop camera scan failed")
                    return False
                self._invalidate_capture()
                self.routine_last_action_time = time.time()
                self.routine_current_had_action = True
                self.click_count += 1
                self._interruptible_sleep(0.4)
                logger.info(
                    "Merchant Shop camera moved %s (step %s/%s)",
                    direction,
                    self.routine_merchant_scan_index,
                    len(scan_pattern),
                )
                return True
            if not self._tap_routine_fallback(
                best_target,
                ("merchant_shop_building", *best_target),
                "Таинственный торговец: открываю найденное здание магазина",
            ):
                return False
            self.routine_merchant_shop_target = best_target
            self.routine_completed_steps.add("merchant_shop_building_tapped")
            return True

        self._save_routine_calibration_frame("mysterious_merchant", "shop_actions", frame)
        if not self._is_settlement_screen_visible():
            # A false building tap must never strand the merchant-only run in
            # another feature screen. Return once and resume the bounded scan.
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Merchant search could not leave an unrelated screen")
                return False
            self.routine_completed_steps.discard("merchant_shop_building_tapped")
            self.routine_merchant_force_scan_move = True
            self._invalidate_capture()
            self.routine_last_action_time = time.time()
            self.routine_current_had_action = True
            logger.warning("Merchant candidate opened an unrelated screen; returned to settlement")
            self._interruptible_sleep(0.7)
            return True
        building_target = getattr(self, "routine_merchant_shop_target", None)
        action_target = detect_shop_radial_action_target(
            frame,
            building_target,
        )
        if action_target is not None:
            if not self._tap_routine_fallback(
                action_target,
                ("merchant_shop_radial_action", *action_target),
                "Таинственный торговец: открываю магазин",
            ):
                return False
            self.routine_completed_steps.add("merchant_shop_open_requested")
            logger.info("Merchant Shop radial action requested at (%s, %s)", *action_target)
            return True
        # A sign-like candidate without the two building actions is not Shop.
        # Continue the camera route instead of accepting a false positive.
        self.routine_completed_steps.discard("merchant_shop_building_tapped")
        self.routine_merchant_force_scan_move = True
        logger.info("Merchant Shop candidate had no radial actions; continuing camera scan")
        return True

    def _healing_camera_route_key(self):
        serial = (
            str(getattr(getattr(self, "adb_client", None), "serial", "") or "")
            if getattr(self, "input_backend", "") == "adb"
            else "desktop"
        )
        account_id = str(getattr(self, "current_account_id", "") or "default")
        return f"{serial or 'adb'}:{account_id}"

    def _remember_healing_camera_route(self, settings=None):
        route = list(getattr(self, "routine_healing_pan_route", ()))
        if not isinstance(settings, dict):
            settings = self._current_task_settings()
        changed = settings.pop("_overview_enabled", None) is not None
        if not route:
            if changed:
                self.save_config()
            return
        routes = settings.setdefault("_camera_routes", {})
        if settings.get("_camera_route_version") != HEALING_CAMERA_ROUTE_VERSION:
            routes.clear()
            settings["_camera_route_version"] = HEALING_CAMERA_ROUTE_VERSION
            changed = True
        route_key = self._healing_camera_route_key()
        # Keep the corner-anchoring moves at the start. Saving only the tail
        # makes the route relative to the previous camera position and can
        # strand the next run in an empty part of the shelter.
        remembered = route[:96]
        if routes.get(route_key) != remembered:
            routes[route_key] = remembered
            changed = True
        if changed:
            self.save_config()
        logger.info(
            "Healing camera route remembered for %s: %s",
            route_key,
            remembered,
        )

    def _finish_pending_healing_collection(self, settings, source):
        settings["_last_collection_attempt_at"] = time.time()
        settings["_collection_pending"] = False
        settings.pop("_pending_heal_count", None)
        settings.pop("_last_pending_camera_scan_at", None)
        settings.pop("_last_saved_hospital_attempt_at", None)
        settings["_hospital_target_failures"] = 0
        self.routine_healing_pan_route = []
        self.routine_healing_replay_index = 0
        self.routine_healing_scan_index = 0
        self.routine_healing_settle_checks = 0
        self.routine_healing_search_started = False
        self.routine_healing_saved_route_rejected = False
        self.save_config()
        self.set_status_message(
            "Вылеченные войска собраны",
            force=True,
        )
        logger.info("Finished healing collection confirmed through %s", source)

    def _remember_healing_hospital_target(self, settings, target, save=True):
        target_x, target_y = map(int, target)
        settings["_hospital_target"] = [target_x, target_y]
        settings["_hospital_target_failures"] = 0
        settings.pop("_last_saved_hospital_attempt_at", None)
        if save:
            self.save_config()
        logger.info(
            "Healing hospital target remembered at (%s, %s)",
            target_x,
            target_y,
        )

    def _healing_start_control_visible(self):
        for image in getattr(self, "search_images", ()):
            if (
                image.get("enabled", True)
                and image.get("runtime_step") == "start_healing"
            ):
                location, bbox, _score = self._locate_image(image)
                if location is not None and bbox is not None:
                    return True
        return False

    def _try_healing_troop_form(self, task, frame):
        if not healing_troop_form_is_visible(frame):
            return False

        settings = task.setdefault("settings", {})
        if settings.get("_collection_pending", False):
            if healing_selection_is_empty(frame):
                self._finish_pending_healing_collection(
                    settings,
                    "idle hospital troop form",
                )
                return True
            elif self._healing_start_control_visible():
                # The game can auto-select a small wounded batch as soon as an
                # idle hospital form opens. A visible ordinary Heal button
                # proves the previous batch is no longer running, so clear the
                # stale pending state and configure the requested amount below.
                self._finish_pending_healing_collection(
                    settings,
                    "idle auto-filled hospital troop form",
                )
            else:
                try:
                    retry_delay = float(
                        settings.get("collection_delay_seconds", 2) or 2
                    )
                except (TypeError, ValueError):
                    retry_delay = 2.0
                retry_delay = max(1.0, min(5.0, retry_delay))
                self._defer_current_routine_unavailable(
                    "текущее лечение ещё не завершено",
                    time.time(),
                    retry_delay=retry_delay,
                )
                return True

        start_image = next(
            (
                image
                for image in getattr(self, "search_images", ())
                if image.get("enabled", True)
                and image.get("action") == "heal_troops"
                and image.get("group") == task.get("group")
            ),
            None,
        )
        if start_image is None:
            logger.warning("Healing troop form is open but its action is missing")
            return False

        scale_x = frame.shape[1] / 1280.0
        scale_y = frame.shape[0] / 720.0
        ordinary_heal = pyautogui.Point(
            int(round(1028 * scale_x)),
            int(round(617 * scale_y)),
        )
        if self._execute_action(start_image, ordinary_heal) is False:
            return False

        image_path = start_image.get("path")
        if image_path:
            self.stats[image_path] = self.stats.get(image_path, 0) + 1
        self.click_count += 1
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.routine_completed_steps.update(
            completed_runtime_steps_for_image(start_image)
        )
        logger.info(
            "Healing troop form started directly; completed steps=%s",
            sorted(self.routine_completed_steps),
        )
        return True

    def _try_healing_visual_fallback(self, task, remembered_only=False):
        if task.get("id") != "heal":
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Healing fallback could not capture the screen")
            return False

        if healing_troop_form_is_visible(frame):
            return self._try_healing_troop_form(task, frame)

        if not self._is_main_screen_visible():
            return False
        settlement_visible = self._is_settlement_screen_visible()
        continuing_confirmed_scan = bool(
            getattr(self, "routine_healing_search_started", False)
            and getattr(self, "routine_healing_pan_route", ())
            and not task.get("settings", {}).get("_collection_pending", False)
        )
        if not settlement_visible and not continuing_confirmed_scan:
            self.set_status_message(
                "Лечение: возвращаюсь с карты мира в убежище",
                force=True,
            )
            if not self._switch_to_settlement_screen():
                logger.warning(
                    "Healing search paused because the settlement screen "
                    "could not be confirmed"
                )
                return False
            self.routine_healing_pan_route = []
            self.routine_healing_replay_index = 0
            self.routine_healing_scan_index = 0
            self.routine_healing_settle_checks = 0
            self.routine_healing_search_started = False
            logger.info("Healing search returned from the world map to the settlement")
            return True
        if not settlement_visible and continuing_confirmed_scan:
            # Chat text and notifications can cover the bottom-left shelter
            # marker after a camera pan. This route only uses map swipes, so it
            # remains safe to continue the already-confirmed settlement scan.
            logger.info(
                "Healing settlement marker is covered; continuing confirmed "
                "camera route at step %s",
                len(self.routine_healing_pan_route),
            )

        height, width = frame.shape[:2]
        settings = task.setdefault("settings", {})
        collection_pending = bool(settings.get("_collection_pending", False))
        try:
            collection_delay = max(
                1.0,
                min(
                    3600.0,
                    float(settings.get("collection_delay_seconds", 2) or 2),
                ),
            )
        except (TypeError, ValueError):
            collection_delay = 2.0
        if collection_pending:
            last_started_at = float(
                settings.get("_last_heal_started_at", time.time()) or time.time()
            )
            now = time.time()
            remaining = collection_delay - (now - last_started_at)
            if remaining > 0:
                remaining_seconds = max(1, int(remaining + 0.999))
                logger.info(
                    "Healing collection is waiting for the configured delay: "
                    "%s seconds remaining",
                    remaining_seconds,
                )
                self._defer_current_routine_unavailable(
                    f"сбор вылеченных через {remaining_seconds} сек",
                    now,
                    retry_delay=remaining,
                )
                return True

        saved_target = settings.get("_hospital_target")
        saved_target_route = []
        configured_routes = settings.get("_camera_routes")
        if (
            saved_target is not None
            and settings.get("_camera_route_version")
            == HEALING_CAMERA_ROUTE_VERSION
            and isinstance(configured_routes, dict)
            and configured_routes
        ):
            route_key = self._healing_camera_route_key()
            saved_target_route = list(configured_routes.get(route_key, ()))
        saved_target_route_pending = bool(
            saved_target_route
            and not settings.get("_hospital_target_camera_fresh", False)
            and (
                not getattr(self, "routine_healing_search_started", False)
                or self.routine_healing_replay_index < len(saved_target_route)
            )
        )
        if saved_target is not None and not saved_target_route_pending:
            if (
                isinstance(saved_target, (list, tuple))
                and len(saved_target) == 2
            ):
                try:
                    target_x = int(saved_target[0])
                    target_y = int(saved_target[1])
                except (TypeError, ValueError):
                    settings.pop("_hospital_target", None)
                    settings.pop("_hospital_target_reopen_index", None)
                else:
                    fresh_target = bool(
                        settings.get("_hospital_target_camera_fresh", False)
                    )
                    fresh_reopen_index = 0
                    if fresh_target:
                        try:
                            fresh_reopen_index = int(
                                settings.get(
                                    "_hospital_target_reopen_index",
                                    0,
                                )
                                or 0
                            )
                        except (TypeError, ValueError):
                            fresh_reopen_index = 0
                        fresh_reopen_index = max(
                            0,
                            min(
                                fresh_reopen_index,
                                len(HEALING_HOSPITAL_REOPEN_OFFSETS) - 1,
                            ),
                        )
                        offset_x, offset_y = (
                            HEALING_HOSPITAL_REOPEN_OFFSETS[
                                fresh_reopen_index
                            ]
                        )
                        target_x += int(round(offset_x * width / 1280.0))
                        target_y += int(round(offset_y * height / 720.0))
                        target_x = max(230, min(width - 181, target_x))
                        target_y = max(121, min(height - 201, target_y))
                    retry_delay = max(1.0, min(5.0, collection_delay))
                    last_attempt_at = float(
                        settings.get("_last_saved_hospital_attempt_at", 0.0)
                        or 0.0
                    )
                    now = time.time()
                    if now - last_attempt_at < retry_delay:
                        self._defer_current_routine_unavailable(
                            (
                                "жду завершения лечения"
                                if collection_pending
                                else "повторно открываю найденный госпиталь"
                            ),
                            now,
                            retry_delay=retry_delay - (now - last_attempt_at),
                        )
                        return True
                    if self._tap_routine_fallback(
                        (target_x, target_y),
                        (
                            "healing_saved_hospital_collect"
                            if collection_pending
                            else "healing_saved_hospital_reopen",
                            target_x,
                            target_y,
                        ),
                        (
                            "Лечение: собираю войска в сохранённом госпитале"
                            if collection_pending
                            else "Лечение: повторно открываю найденный госпиталь"
                        ),
                    ):
                        settings["_last_saved_hospital_attempt_at"] = time.time()
                        opened_frame = None
                        try:
                            opened_frame, _origin = self._capture_screen_bgr(
                                force=True
                            )
                        except Exception:
                            logger.exception(
                                "Healing saved target could not verify the "
                                "hospital troop form"
                            )
                        if (
                            opened_frame is not None
                            and healing_troop_form_is_visible(opened_frame)
                        ):
                            settings.pop("_hospital_target_camera_fresh", None)
                            settings.pop("_hospital_target_reopen_index", None)
                            form_is_empty = healing_selection_is_empty(
                                opened_frame
                            )
                            self._remember_healing_hospital_target(
                                settings,
                                (target_x, target_y),
                                save=not form_is_empty,
                            )
                            return self._try_healing_troop_form(
                                task,
                                opened_frame,
                            )
                        if self._healing_start_control_visible():
                            settings.pop("_hospital_target_camera_fresh", None)
                            settings.pop("_hospital_target_reopen_index", None)
                            self._remember_healing_hospital_target(
                                settings,
                                (target_x, target_y),
                                save=False,
                            )
                            if collection_pending:
                                self._finish_pending_healing_collection(
                                    settings,
                                    "remembered hospital target",
                                )
                            else:
                                self.save_config()
                                logger.info(
                                    "Remembered healing hospital reopened; "
                                    "waiting for the start-healing action"
                                )
                            return True
                        if fresh_target:
                            next_reopen_index = fresh_reopen_index + 1
                            if next_reopen_index < len(
                                HEALING_HOSPITAL_REOPEN_OFFSETS
                            ):
                                settings["_hospital_target_reopen_index"] = (
                                    next_reopen_index
                                )
                                self.save_config()
                                if not self._is_main_screen_visible():
                                    self._return_to_main_screen(
                                        max_back_steps=2,
                                        require_settlement=True,
                                    )
                                logger.info(
                                    "Fresh healing marker reopen candidate "
                                    "%s/%s at (%s, %s) did not open the "
                                    "hospital; trying the building below",
                                    fresh_reopen_index + 1,
                                    len(HEALING_HOSPITAL_REOPEN_OFFSETS),
                                    target_x,
                                    target_y,
                                )
                                self._defer_current_routine_unavailable(
                                    "проверяю здание под собранным маркером",
                                    time.time(),
                                    retry_delay=retry_delay,
                                )
                                return True
                            settings.pop(
                                "_hospital_target_camera_fresh",
                                None,
                            )
                            settings.pop(
                                "_hospital_target_reopen_index",
                                None,
                            )
                        failures = int(
                            settings.get("_hospital_target_failures", 0) or 0
                        ) + 1
                        settings["_hospital_target_failures"] = failures
                        self.save_config()
                        if failures < 2:
                            self._defer_current_routine_unavailable(
                                (
                                    "лечение ещё не завершено"
                                    if collection_pending
                                    else "проверяю найденный госпиталь"
                                ),
                                time.time(),
                                retry_delay=retry_delay,
                            )
                            return True
                        logger.warning(
                            "Remembered healing hospital target was not "
                            "confirmed after %s attempts",
                            failures,
                        )
                        settings.pop("_hospital_target", None)
                        settings.pop("_hospital_target_camera_fresh", None)
                        settings.pop("_hospital_target_reopen_index", None)
                        settings.pop("_last_saved_hospital_attempt_at", None)
                        settings["_hospital_target_failures"] = 0
                        self.save_config()
                        self.set_status_message(
                            "Госпиталь сместился: ищу новое положение",
                            force=True,
                        )
                        if remembered_only:
                            return False

        if remembered_only:
            return False

        event_panel_target = detect_settlement_event_panel_collapse_target(frame)
        if event_panel_target is not None:
            if not self._tap_routine_fallback(
                event_panel_target,
                ("healing_event_panel_collapse", *event_panel_target),
                "Лечение: скрываю панель событий для поиска госпиталя",
            ):
                return False
            self._invalidate_capture()
            self._interruptible_sleep(0.6)
            logger.info(
                "Healing search collapsed the settlement event panel at (%s, %s)",
                *event_panel_target,
            )
            return True

        collection_target = (
            detect_finished_healing_target(frame)
            if settings.get("collect_finished", True)
            else None
        )
        if collection_target is not None:
            if not self._tap_routine_fallback(
                collection_target,
                ("healing_collect_visual", *collection_target),
                "Лечение: собираю готовых бойцов",
            ):
                return False
            settings["_last_collection_attempt_at"] = time.time()
            try:
                frame_after, _origin = self._capture_screen_bgr(force=True)
            except Exception:
                logger.exception(
                    "Healing fallback could not verify the collection marker"
                )
                return True
            if detect_finished_healing_target(frame_after) is None:
                # The collection marker identifies the hospital even when the
                # building itself has no calibrated template.  Persist the
                # anchored camera route before collection cleanup clears the
                # in-memory path, so the next batch can reopen the same
                # building autonomously.
                self._remember_healing_camera_route(settings)
                if healing_troop_form_is_visible(frame_after):
                    form_is_empty = healing_selection_is_empty(frame_after)
                    self._remember_healing_hospital_target(
                        settings,
                        collection_target,
                        save=not form_is_empty,
                    )
                    return self._try_healing_troop_form(task, frame_after)
                if not self._is_main_screen_visible():
                    if not collection_pending:
                        logger.info(
                            "Healing portrait opened the hospital; continuing "
                            "with a new treatment batch"
                        )
                        return True
                    if self._healing_start_control_visible():
                        self._remember_healing_hospital_target(
                            settings,
                            collection_target,
                            save=False,
                        )
                        self._finish_pending_healing_collection(
                            settings,
                            "idle hospital screen",
                        )
                        return True
                    logger.info(
                        "Healing portrait opened the hospital before the batch "
                        "was ready; collection remains pending"
                    )
                    self.save_config()
                    self._defer_current_routine_unavailable(
                        "текущее лечение ещё не завершено",
                        time.time(),
                        retry_delay=collection_delay,
                    )
                    return True
                self._remember_healing_hospital_target(
                    settings,
                    collection_target,
                    save=False,
                )
                self._finish_pending_healing_collection(
                    settings,
                    f"map marker at {collection_target}",
                )
                # The first marker click collected the finished batch without
                # moving the camera.  On the next iteration click the exact
                # coordinate once more before any pan/replay can invalidate it.
                settings["_hospital_target_camera_fresh"] = True
                settings["_hospital_target_reopen_index"] = 0
                self.save_config()
                self.set_status_message(
                    "Вылеченные войска собраны",
                    force=True,
                )
                logger.info(
                    "Finished healing collected through generic portrait "
                    "marker at (%s, %s)",
                    *collection_target,
                )
            else:
                self.save_config()
                logger.warning(
                    "Finished healing marker remained after generic "
                    "collection click at (%s, %s)",
                    *collection_target,
                )
            return True

        if settings.get("_collection_pending", False):
            last_started_at = float(
                settings.get("_last_heal_started_at", time.time()) or time.time()
            )
            now = time.time()
            if now - last_started_at < 12 * 3600.0:
                last_scan_at = float(
                    settings.get("_last_pending_camera_scan_at", 0.0) or 0.0
                )
                if now - last_scan_at >= 60.0:
                    logger.info(
                        "Healing batch is pending and no marker is visible; "
                        "searching the remembered hospital route"
                    )
                else:
                    logger.info(
                        "Healing batch is still pending; waiting for the fixed "
                        "collection marker before the next camera scan"
                    )
                    self._defer_current_routine_unavailable(
                        "текущее лечение ещё не завершено",
                        now,
                    )
                    return True
            else:
                settings["_collection_pending"] = False
                settings.pop("_pending_heal_count", None)
                settings.pop("_last_pending_camera_scan_at", None)
                self.save_config()
                logger.info("Stale healing collection state was cleared")

        if not getattr(self, "routine_healing_search_started", False):
            self.routine_healing_search_started = True
            self.routine_last_action_time = time.time()
            self.set_status_message(
                "Лечение: ищу госпиталь или завершённую партию на карте убежища",
                force=True,
            )
            logger.info("Healing camera search started")
            return True

        route_key = self._healing_camera_route_key()
        saved_routes = settings.setdefault("_camera_routes", {})
        if settings.get("_camera_route_version") != HEALING_CAMERA_ROUTE_VERSION:
            saved_routes.clear()
            settings["_camera_route_version"] = HEALING_CAMERA_ROUTE_VERSION
            self.save_config()
        saved_route = list(saved_routes.get(route_key, ()))
        replay_index = self.routine_healing_replay_index
        if replay_index < len(saved_route):
            direction = saved_route[replay_index]
            self.routine_healing_replay_index += 1
            route_label = "запомненный маршрут"
        else:
            if (
                saved_route
                and not getattr(
                    self,
                    "routine_healing_saved_route_rejected",
                    False,
                )
            ):
                saved_routes.pop(route_key, None)
                self.routine_healing_saved_route_rejected = True
                self.save_config()
                logger.info(
                    "Healing camera route rejected after replay for %s",
                    route_key,
                )
            scan_pattern = HEALING_CAMERA_SCAN_PATTERN
            scan_index = self.routine_healing_scan_index
            if scan_index >= len(scan_pattern):
                settle_checks = getattr(
                    self,
                    "routine_healing_settle_checks",
                    0,
                )
                if settle_checks < 2:
                    self.routine_healing_settle_checks = settle_checks + 1
                    self.set_status_message(
                        "Лечение: жду загрузку значков госпиталя",
                        force=True,
                    )
                    self._invalidate_capture()
                    self._interruptible_sleep(1.5)
                    logger.info(
                        "Healing camera scan finished; waiting for hospital "
                        "markers to render (%s/2)",
                        self.routine_healing_settle_checks,
                    )
                    return True
                if not getattr(
                    self,
                    "routine_healing_recenter_attempted",
                    True,
                ):
                    # Returning through the world map asks the game to center
                    # the shelter again.  This gives marker recognition one
                    # clean pass after a scan that began at an inherited edge
                    # position, without advancing the ordered queue.
                    self.routine_healing_recenter_attempted = True
                    target_x = int(round(width * 65 / 1280.0))
                    target_y = int(round(height * 655 / 720.0))
                    self.set_status_message(
                        "Лечение: заново центрирую убежище для поиска госпиталя",
                        force=True,
                    )
                    try:
                        if self.uses_adb:
                            self.adb_client.tap(target_x, target_y)
                        else:
                            pyautogui.click(target_x, target_y)
                    except Exception:
                        logger.exception("Healing shelter recenter failed")
                    else:
                        self._invalidate_capture()
                        self._interruptible_sleep(1.2)
                        if self._switch_to_settlement_screen():
                            self.routine_healing_pan_route = []
                            self.routine_healing_replay_index = 0
                            self.routine_healing_scan_index = 0
                            self.routine_healing_settle_checks = 0
                            self.routine_healing_search_started = False
                            self.routine_healing_saved_route_rejected = False
                            logger.info(
                                "Healing search recentered the shelter through "
                                "the world map; restarting marker scan"
                            )
                            return True
                        logger.warning(
                            "Healing search could not confirm the shelter after "
                            "the recenter attempt"
                        )
                if settings.get("_collection_pending", False):
                    settings["_last_pending_camera_scan_at"] = time.time()
                    self.save_config()
                logger.warning(
                    "Healing hospital was not found after %s camera moves",
                    len(self.routine_healing_pan_route),
                )
                self._defer_current_routine_unavailable(
                    "госпиталь не найден после полного обхода карты",
                    time.time(),
                    retry_delay=max(300.0, healing_repeat_delay(task)),
                )
                return True
            direction = scan_pattern[scan_index]
            self.routine_healing_scan_index += 1
            route_label = "поиск"

        swipes = {
            "left": ((980, 420), (360, 420)),
            "right": ((360, 420), (980, 420)),
            "up": ((640, 570), (640, 250)),
            "down": ((640, 250), (640, 570)),
        }
        swipe = swipes.get(direction)
        if swipe is None:
            return False
        (from_x, from_y), (to_x, to_y) = swipe
        from_x = int(round(from_x * width / 1280.0))
        from_y = int(round(from_y * height / 720.0))
        to_x = int(round(to_x * width / 1280.0))
        to_y = int(round(to_y * height / 720.0))
        try:
            if self.uses_adb:
                self.adb_client.swipe(from_x, from_y, to_x, to_y, 400)
            else:
                pyautogui.moveTo(from_x, from_y)
                pyautogui.dragTo(to_x, to_y, duration=0.4, button="left")
        except Exception:
            logger.exception("Healing camera movement failed")
            return False

        self._invalidate_capture()
        self.routine_healing_pan_route.append(direction)
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        self.set_status_message(
            f"Лечение: двигаю карту ({route_label}), ищу госпиталь",
            force=True,
        )
        self._interruptible_sleep(0.6)
        logger.info(
            "Healing camera moved %s (%s, route step %s)",
            direction,
            route_label,
            len(self.routine_healing_pan_route),
        )
        return True

    def _try_collective_tutorial_fallback(self, task):
        if (
            task.get("id") != "collective_mind"
            or "search" not in self.routine_completed_steps
            or self.routine_collective_tutorial_taps >= 4
        ):
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Collective tutorial fallback could not capture the screen")
            return False

        target = detect_collective_tutorial_continue_target(frame)
        if target is None:
            return False
        if not self._tap_routine_fallback(
            target,
            ("collective_tutorial", self.routine_collective_tutorial_taps),
            "\u041a\u043e\u043b\u043b\u0435\u043a\u0442\u0438\u0432\u043d\u044b\u0439 \u0440\u0430\u0437\u0443\u043c: \u043f\u0440\u043e\u043f\u0443\u0441\u043a\u0430\u044e \u0438\u0433\u0440\u043e\u0432\u043e\u0435 \u043e\u0431\u0443\u0447\u0435\u043d\u0438\u0435",
        ):
            return False
        self.routine_collective_tutorial_taps += 1
        logger.info(
            "Collective tutorial fallback advanced page %s at (%s, %s)",
            self.routine_collective_tutorial_taps,
            *target,
        )
        return True

    def _try_prize_hunt_confirmation_fallback(self, task):
        if task.get("id") != "prize_hunt" or "enter" not in self.routine_completed_steps:
            return False
        try:
            frame, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Prize hunt confirmation fallback could not capture the screen")
            return False

        target = detect_prize_hunt_squad_confirmation_target(frame)
        if target is None:
            return False
        if not self._tap_routine_fallback(
            target,
            ("prize_hunt_squad_confirmation", *target),
            "Охота за призом: подтверждаю подбор сохранённого отряда",
        ):
            return False
        self.routine_completed_steps.add("squad_confirmation")
        # This dialog is the final confirmation when a deployed squad differs
        # from its preset. Accepting it enters the hunt directly.
        self.routine_completed_steps.add("deploy")
        logger.info("Prize hunt squad confirmation accepted at (%s, %s)", *target)
        return True

    @staticmethod
    def _research_reference_frame(frame):
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        if frame.shape[1] == 1280 and frame.shape[0] == 720:
            return frame
        return cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)

    def _research_tree_candidates(self, frame):
        """Find visible coloured research nodes in reference coordinates."""
        reference = self._research_reference_frame(frame)
        if reference is None or not research_tree_is_visible(reference):
            return []
        gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(reference, cv2.COLOR_BGR2HSV)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=70,
            param1=100,
            param2=40,
            minRadius=32,
            maxRadius=55,
        )
        if circles is None:
            return []
        points = []
        for x_value, y_value, radius in np.round(circles[0]).astype(int):
            # A selected technology opens a large detail card whose single
            # round illustration sits near x=320..340.  It is not a tree node,
            # but its size and saturation are deliberately very similar.  The
            # actionable frontier of both actual trees starts farther right;
            # excluding the card prevents the scanner from clicking it in a
            # loop instead of returning to the tree.
            if not (420 <= x_value <= 1168 and 90 <= y_value <= 650):
                continue
            top = max(0, int(y_value - radius * 0.75))
            bottom = min(reference.shape[0], int(y_value + radius * 0.75) + 1)
            left = max(0, int(x_value - radius * 0.75))
            right = min(reference.shape[1], int(x_value + radius * 0.75) + 1)
            roi = hsv[top:bottom, left:right]
            if roi.size == 0:
                continue
            yy, xx = np.ogrid[top:bottom, left:right]
            mask = (
                (xx - x_value) ** 2 + (yy - y_value) ** 2
                <= int(radius * 0.75) ** 2
            )
            saturation = float(roi[:, :, 1][mask].mean()) if np.any(mask) else 0.0
            if saturation >= 55.0:
                points.append((int(x_value), int(y_value)))
        return sorted(set(points), key=lambda point: (point[0], point[1]))

    def _tap_research_reference(self, x_value, y_value, display):
        target_x = int(round(float(x_value) * display.scale_x))
        target_y = int(round(float(y_value) * display.scale_y))
        if self.uses_adb:
            self.adb_client.tap(target_x, target_y)
        else:
            pyautogui.click(target_x, target_y)
        self._invalidate_capture()
        return target_x, target_y

    def _swipe_research_reference(self, start, end, display, duration_ms=450):
        start_x = int(round(float(start[0]) * display.scale_x))
        start_y = int(round(float(start[1]) * display.scale_y))
        end_x = int(round(float(end[0]) * display.scale_x))
        end_y = int(round(float(end[1]) * display.scale_y))
        if self.uses_adb:
            self.adb_client.swipe(start_x, start_y, end_x, end_y, duration_ms)
        else:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(
                end_x,
                end_y,
                duration=duration_ms / 1000.0,
                button="left",
            )
        self._invalidate_capture()

    def _research_press_back(self):
        if self.uses_adb:
            self.adb_client.keyevent(4)
        else:
            pyautogui.press("esc")
        self._invalidate_capture()

    @staticmethod
    def _research_page_signature(frame):
        reference = AutoClicker._research_reference_frame(frame)
        if reference is None:
            return b""
        gray = cv2.cvtColor(reference[100:650, 130:1160], cv2.COLOR_BGR2GRAY)
        compact = cv2.resize(gray, (48, 24), interpolation=cv2.INTER_AREA)
        return (compact // 16).astype(np.uint8).tobytes()

    def _try_research_tree_row(self, frame, row_y, display, branch, page_index):
        """Try one frontier row and restore the tree after a full node."""
        current = frame
        for tap_attempt in range(2):
            candidates = self._research_tree_candidates(current)
            same_row = [
                point for point in candidates if abs(int(point[1]) - int(row_y)) < 45
            ]
            if not same_row:
                return False, current
            node_x, node_y = max(same_row, key=lambda point: point[0])
            target = self._tap_research_reference(node_x, node_y, display)
            logger.info(
                "Research branch=%s page=%s row=%s tap=%s target=%s",
                branch,
                page_index + 1,
                row_y,
                tap_attempt + 1,
                target,
            )
            self._interruptible_sleep(0.9)
            current, _origin = self._capture_screen_bgr(force=True)
            post_tap_candidates = self._research_tree_candidates(current)
            if not post_tap_candidates and detect_research_action_target(current) is not None:
                logger.info(
                    "Research action confirmed for branch=%s page=%s row=%s",
                    branch,
                    page_index + 1,
                    row_y,
                )
                return True, current
            if not post_tap_candidates:
                # A node detail without an enabled gold action is already full
                # (or locked). Return to the tree before trying another row.
                self._research_press_back()
                self._interruptible_sleep(0.7)
                restored, _origin = self._capture_screen_bgr(force=True)
                logger.info(
                    "Research node branch=%s page=%s row=%s has no action; "
                    "returned to tree",
                    branch,
                    page_index + 1,
                    row_y,
                )
                return False, restored
        # Both taps left the tree visible, so the node was not opened. Do not
        # press Back here: that would leave the research screen entirely.
        return False, current

    def _reset_research_branch(self, branch, display):
        frame, _origin = self._capture_screen_bgr(force=True)
        a_branch_is_selected = any(
            research_branch_is_selected(frame, candidate)
            for candidate in ("economy", "war")
        )
        if (
            research_tree_is_visible(frame)
            and not a_branch_is_selected
            and not self._research_tree_candidates(frame)
            and detect_research_action_target(frame) is None
        ):
            self._research_press_back()
            self._interruptible_sleep(0.7)
            frame, _origin = self._capture_screen_bgr(force=True)
        branch_y = 165 if branch == "economy" else 300
        branch_confirmed = research_branch_is_selected(frame, branch)
        for attempt in range(2):
            if branch_confirmed:
                break
            self._tap_research_reference(70, branch_y, display)
            self._interruptible_sleep(0.7)
            frame, _origin = self._capture_screen_bgr(force=True)
            branch_confirmed = research_branch_is_selected(frame, branch)
            if branch_confirmed:
                logger.info(
                    "Research branch switch confirmed: %s (attempt %s)",
                    branch,
                    attempt + 1,
                )
        if not branch_confirmed:
            logger.warning(
                "Research branch switch was not confirmed: %s; "
                "not scanning a mislabeled branch",
                branch,
            )
            return None
        # Anchor the selected branch at its left edge. Each subsequent
        # right-to-left swipe then exposes one new page exactly once.
        for _ in range(7):
            self._swipe_research_reference((300, 500), (1000, 500), display)
            self._interruptible_sleep(0.12)
        frame, _origin = self._capture_screen_bgr(force=True)
        return frame

    def _scan_research_branch(self, branch, display, max_pages=6):
        frame = self._reset_research_branch(branch, display)
        if frame is None:
            return False
        seen_pages = set()
        for page_index in range(max(1, int(max_pages))):
            signature = self._research_page_signature(frame)
            if signature and signature in seen_pages:
                logger.info(
                    "Research branch=%s stopped at repeated page %s",
                    branch,
                    page_index + 1,
                )
                break
            if signature:
                seen_pages.add(signature)

            attempted_rows = []
            for _row_attempt in range(6):
                candidates = self._research_tree_candidates(frame)
                if not candidates:
                    break
                frontier_x = max(point[0] for point in candidates)
                frontier = [
                    point for point in candidates if point[0] >= frontier_x - 60
                ]
                available_rows = []
                for _node_x, node_y in sorted(
                    frontier,
                    key=lambda point: (abs(point[1] - 360), point[1]),
                ):
                    if all(abs(node_y - seen_y) >= 45 for seen_y in attempted_rows):
                        available_rows.append(int(node_y))
                if not available_rows:
                    break
                row_y = available_rows[0]
                attempted_rows.append(row_y)
                found, frame = self._try_research_tree_row(
                    frame,
                    row_y,
                    display,
                    branch,
                    page_index,
                )
                if found:
                    return True

            before_reference = self._research_reference_frame(frame)
            self._swipe_research_reference((1000, 500), (300, 500), display)
            self._interruptible_sleep(0.65)
            after, _origin = self._capture_screen_bgr(force=True)
            after_reference = self._research_reference_frame(after)
            if before_reference is None or after_reference is None:
                break
            page_change = float(
                cv2.absdiff(
                    before_reference[100:650, 130:1160],
                    after_reference[100:650, 130:1160],
                ).mean()
            )
            logger.info(
                "Research branch=%s advanced after page=%s, panel change %.2f",
                branch,
                page_index + 1,
                page_change,
            )
            frame = after
            if page_change < 0.65:
                break
        return False

    def _select_available_research(self):
        setting = str(self._current_task_settings().get("branch", "off") or "off")
        if setting == "off":
            return None
        branches = ("economy", "war") if setting == "any" else (setting,)
        display = self.get_display_profile()
        for branch in branches:
            self.set_status_message(
                f"Проверяю ветку исследования: "
                f"{'экономика' if branch == 'economy' else 'война'}",
                force=True,
            )
            if self._scan_research_branch(branch, display):
                return branch
        return None

    def _try_research_visual_fallback(self, task):
        """Collect a finished research or start the selected next research."""
        if task.get("id") != "research" or not {
            "lab",
            "select",
        }.intersection(self.routine_completed_steps):
            return False
        collected_waiting_for_selection = (
            "collect" in self.routine_completed_steps
            and "select" not in self.routine_completed_steps
        )
        try:
            before, _origin = self._capture_screen_bgr(force=True)
        except Exception:
            logger.exception("Research action fallback could not capture the screen")
            return False
        if research_tree_progress_is_active(before):
            now = time.time()
            self.routine_completed_steps.add("confirm")
            self.routine_current_had_action = True
            self.routine_last_action_time = now
            self.routine_idle_confirmation_count = 0
            self.routine_action_completes_task = True
            self.set_status_message(
                "Исследование уже выполняется: таймер в дереве подтверждён",
                force=True,
            )
            logger.info(
                "Active research countdown confirmed in the open tree; "
                "ordered queue can continue"
            )
            self._finish_current_routine(now, completion_clicked=False)
            return True
        tree_candidates = (
            self._research_tree_candidates(before)
            if research_tree_is_visible(before)
            else []
        )
        # Gold progress strips on visible tree nodes have the same palette as
        # the Collect/Start button.  Only look for the button after the tree
        # itself is no longer visible.
        target = None if tree_candidates else detect_research_action_target(before)
        if target is None:
            if (
                "select" not in self.routine_completed_steps
                and research_tree_is_visible(before)
            ):
                try:
                    branch = self._select_available_research()
                except Exception:
                    logger.exception("Dynamic research-tree scan failed")
                    branch = None
                if branch is None:
                    logger.warning(
                        "No enabled research action found after scanning all "
                        "configured branches and pages"
                    )
                    self._defer_current_routine_no_action(time.time())
                    return True
                self.routine_completed_steps.add("select")
                self.routine_current_had_action = True
                self.routine_last_action_time = time.time()
                self.routine_idle_confirmation_count = 0
                self.set_status_message(
                    f"Выбрано исследование: "
                    f"{'война' if branch == 'war' else 'экономика'}",
                    force=True,
                )
                logger.info(
                    "Research selection confirmed by dynamic tree scan in %s branch",
                    branch,
                )
                self.save_config()
                return True
            return False
        if collected_waiting_for_selection:
            # A completed result was already collected. A later unrelated gold
            # control must not be interpreted as a second Collect button; the
            # dynamic tree scanner above owns the next selection.
            return False
        selected_research = "select" in self.routine_completed_steps
        try:
            if self.uses_adb:
                self.adb_client.tap(*target)
            else:
                pyautogui.click(*target)
        except Exception:
            logger.exception("Research action fallback click failed")
            return False
        self._invalidate_capture()
        self._interruptible_sleep(1.4)
        after, _after_origin = self._capture_screen_bgr(force=True)
        if after.shape != before.shape:
            before = cv2.resize(
                before,
                (after.shape[1], after.shape[0]),
                interpolation=cv2.INTER_LINEAR,
            )
        screen_change = float(cv2.absdiff(before, after).mean())
        active_after = (
            research_progress_bar_is_active(after)
            or research_tree_progress_is_active(after)
        )
        button_still_visible = detect_research_action_target(after) is not None
        if screen_change < 2.0 and button_still_visible and not active_after:
            logger.warning(
                "Research action fallback was not confirmed (screen change %.2f)",
                screen_change,
            )
            return False
        self.routine_current_had_action = True
        self.routine_last_action_time = time.time()
        self.routine_idle_confirmation_count = 0
        self.click_count += 1
        if selected_research:
            self.routine_completed_steps.add("confirm")
            self.set_status_message(
                "Исследование запущено: подтверждение экрана получено",
                force=True,
            )
            logger.info(
                "Research start confirmed by visual fallback, screen change %.2f",
                screen_change,
            )
            self._finish_current_routine(
                self.routine_last_action_time,
                completion_clicked=True,
            )
        else:
            self.routine_completed_steps.add("collect")
            self.set_status_message(
                "Завершённое исследование собрано; выбираю следующее",
                force=True,
            )
            logger.info(
                "Finished research collected, screen change %.2f; continuing research task",
                screen_change,
            )
        return True

    def _defer_current_routine_no_action(self, now=None):
        now = time.time() if now is None else float(now)
        task = self.get_routine_task(self.current_routine_task_id)
        if not task:
            self.current_routine_task_id = None
            return

        retry_delay = no_action_retry_delay(task)
        if task.get("id") == "research":
            research_started_at = float(
                getattr(self, "routine_research_budget_started_at", 0.0)
                or 0.0
            )
            if research_started_at <= 0.0:
                research_started_at = float(
                    getattr(self, "routine_task_started_at", 0.0) or now
                )
                self.routine_research_budget_started_at = research_started_at
            research_elapsed = max(0.0, float(now) - research_started_at)
            retry_allowed = bool(
                research_elapsed < RESEARCH_UNCONFIRMED_BUDGET_SECONDS
            )
            retry_delay = min(float(retry_delay), 30.0)
            self._return_to_main_screen(
                max_back_steps=5,
                require_settlement=True,
            )
            if not retry_allowed:
                try:
                    diagnostic_frame, _diagnostic_origin = self._capture_screen_bgr(
                        force=True
                    )
                    self._save_routine_calibration_frame(
                        "research",
                        "unconfirmed",
                        diagnostic_frame,
                    )
                except Exception:
                    logger.exception(
                        "Could not capture the unconfirmed research screen"
                    )
                # Do not call _finish_current_routine here: no research start
                # was confirmed.  This is an explicit, auditable deferral that
                # advances exactly one saved-order slot.
                self.routine_next_run[task["id"]] = float(now) + 60.0
                self.set_status_message(
                    "Исследование не подтверждено за отведённое время: откладываю и продолжаю очередь",
                    force=True,
                )
                logger.warning(
                    "Routine research deferred after %.1f seconds without confirmed progress",
                    research_elapsed,
                )
                self.routine_last_outcome = {
                    "task_id": "research",
                    "outcome": "deferred_stalled",
                    "reason": "unconfirmed_research_budget",
                    "completed_steps": sorted(self.routine_completed_steps),
                    "actions": int(self.routine_current_action_count),
                }
                self._advance_routine_after_outcome(task, now)
                self.current_routine_task_id = None
                self.routine_current_had_action = False
                self.routine_current_action_count = 0
                self.routine_action_counts = {}
                self.routine_completed_steps = set()
                self.routine_action_failure_reason = ""
                self.routine_idle_confirmation_count = 0
                self.routine_home_recovery_attempted = False
                self.routine_idle_guard_visible = False
                self.routine_idle_outside_since = 0.0
                self.routine_idle_recovery_attempted = False
                self.save_config()
                return

            # One controlled retry remains inside the cumulative budget.  Do
            # not reset routine_task_started_at or the persisted research clock.
            self.routine_next_run[task["id"]] = float(now) + retry_delay
            self.set_status_message(
                "Исследование не подтверждено: повторяю эту же задачу",
                force=True,
            )
            logger.warning(
                "Routine research timed out without confirmed start; ordered queue remains on research"
            )
            self.routine_last_outcome = {
                "task_id": "research",
                "outcome": "retry_unconfirmed",
                "completed_steps": sorted(self.routine_completed_steps),
                "actions": int(self.routine_current_action_count),
            }
            self.routine_current_had_action = False
            self.routine_current_action_count = 0
            self.routine_action_counts = {}
            self.routine_completed_steps = set()
            self.routine_action_failure_reason = ""
            self.routine_idle_confirmation_count = 0
            self.routine_home_recovery_attempted = False
            self.routine_idle_guard_visible = False
            self.routine_idle_outside_since = 0.0
            self.routine_idle_recovery_attempted = False
            self.routine_last_action_time = time.time()
            self.save_config()
            self._interruptible_sleep(retry_delay)
            return
        self.routine_next_run[task["id"]] = now + retry_delay
        logger.warning(
            "Routine %s timed out without actions; retrying in %.0f seconds",
            task.get("id"),
            retry_delay,
        )
        # Keep standalone checkboxes independent: a partial or unavailable task
        # must not leave the next task trapped on its sub-screen.
        if not task.get("manual_screen_required", False):
            self._return_to_main_screen(
                max_back_steps=5,
                require_settlement=routine_requires_settlement(task),
            )
        self.set_status_message(
            self.tr(
                'routine_no_action',
                name=self.get_routine_task_name(task),
                seconds=max(1, int(retry_delay)),
            ),
            force=True,
        )
        self.routine_last_outcome = {
            "task_id": str(task.get("id") or ""),
            "outcome": "deferred_no_action",
            "completed_steps": sorted(self.routine_completed_steps),
            "actions": int(self.routine_current_action_count),
        }
        self._advance_routine_after_outcome(task, now)
        self.current_routine_task_id = None
        self.routine_current_had_action = False
        self.routine_current_action_count = 0
        self.routine_action_counts = {}
        self.routine_completed_steps = set()
        self.routine_idle_confirmation_count = 0
        self.routine_home_recovery_attempted = False
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.save_config()

    def _defer_current_routine_no_squad(self, now=None):
        now = time.time() if now is None else float(now)
        task = self.get_routine_task(self.current_routine_task_id)
        if not task:
            self.current_routine_task_id = None
            return

        if (
            str(task.get("id") or "") == "radar_marches"
            and bool(task.get("settings", {}).get("dispatch_until_full", False))
        ):
            self._hold_radar_marches_for_free_squad(
                "нет доступного отряда для задания радара",
                now,
            )
            return

        retry_delay = 60.0
        self.routine_next_run[task["id"]] = now + retry_delay
        logger.info(
            "Routine %s reached the squad screen while every squad is busy; retrying in %.0f seconds",
            task.get("id"),
            retry_delay,
        )
        self._return_to_main_screen(max_back_steps=3)
        self.set_status_message(
            "Все отряды заняты походами или лагерем. Повтор через 60 сек",
            force=True,
        )
        self.routine_last_outcome = {
            "task_id": str(task.get("id") or ""),
            "outcome": "deferred_no_squad",
            "completed_steps": sorted(self.routine_completed_steps),
            "actions": int(self.routine_current_action_count),
        }
        self._advance_routine_after_outcome(task, now)
        self.current_routine_task_id = None
        self.routine_current_had_action = False
        self.routine_current_action_count = 0
        self.routine_action_counts = {}
        self.routine_completed_steps = set()
        self.routine_idle_confirmation_count = 0
        self.routine_home_recovery_attempted = False
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.save_config()

    def _hold_radar_marches_for_free_squad(self, reason, now=None, retry_delay=15.0):
        """Confirm that radar has dispatched every currently available squad."""
        now = time.time() if now is None else float(now)
        task = self.get_routine_task(self.current_routine_task_id)
        if not task or str(task.get("id") or "") != "radar_marches":
            return False

        retry_delay = max(5.0, min(30.0, float(retry_delay)))
        settings = task.setdefault("settings", {})
        no_squad_confirmations = int(
            settings.get("_no_squad_confirmations", 0) or 0
        ) + 1
        settings["_no_squad_confirmations"] = no_squad_confirmations
        if no_squad_confirmations >= 2:
            settings.pop("_no_squad_confirmations", None)
            logger.info(
                "Radar reached squad capacity after two confirmations; "
                "the ordered queue can continue to radar_rewards"
            )
            self._return_to_main_screen(
                max_back_steps=6,
                require_settlement=True,
            )
            self.set_status_message(
                "Радар: свободных отрядов нет, отправка до отказа подтверждена",
                force=True,
            )
            self._queue_post_radar_followups(task, now)
            self._finish_current_routine(now, completion_clicked=True)
            return True

        self.routine_next_run["radar_marches"] = now + retry_delay
        logger.warning(
            "Radar squad capacity needs confirmation (%s); ordered queue remains on radar_marches and retries in %.0f seconds",
            reason,
            retry_delay,
        )
        self._return_to_main_screen(max_back_steps=6, require_settlement=True)
        self.set_status_message(
            "Радар: перепроверяю отсутствие свободного отряда через 15 сек",
            force=True,
        )
        self.routine_last_outcome = {
            "task_id": "radar_marches",
            "outcome": "retry_waiting_for_squad",
            "reason": str(reason),
            "completed_steps": sorted(self.routine_completed_steps),
            "actions": int(self.routine_current_action_count),
        }
        # The selected card was not dispatched. Do not remember it as
        # complete, and restart only that card flow after the short wait.
        self.routine_radar_pending_marker_key = None
        reset_radar_card_runtime_steps(self.routine_completed_steps)
        self.routine_action_failure_reason = ""
        self.routine_idle_confirmation_count = 0
        self.routine_home_recovery_attempted = False
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.routine_last_action_time = time.time()
        self.save_config()
        self._interruptible_sleep(retry_delay)
        return True

    def _defer_current_routine_unavailable(
        self,
        reason,
        now=None,
        retry_delay=None,
    ):
        now = time.time() if now is None else float(now)
        task = self.get_routine_task(self.current_routine_task_id)
        if not task:
            self.current_routine_task_id = None
            return

        reason = str(reason)
        display_reason = {
            "boost_item_unavailable": "нет подходящего усиления сбора на выбранное время",
            "max_queue_checks": "все очереди производства заняты",
            "max_lab_checks": "все очереди исследований заняты",
            "merchant_absent": "Таинственный торговец временно отсутствует",
        }.get(reason, reason)
        retry_delay = (
            unavailable_retry_delay(task)
            if retry_delay is None
            else max(1.0, float(retry_delay))
        )
        if (
            str(task.get("id") or "") == "radar_marches"
            and bool(task.get("settings", {}).get("dispatch_until_full", False))
            and (
                "нет доступного отряда" in reason.casefold()
                or "no squad" in reason.casefold()
            )
        ):
            self._hold_radar_marches_for_free_squad(
                reason,
                now,
                retry_delay=15.0,
            )
            return
        if task.get("id") == "heal":
            # Healing is ordered as one indivisible operation: collect the
            # previous batch when needed, prove the hospital is idle, and
            # start the next available batch.  Neither a missing marker nor a
            # stale saved coordinate is a successful outcome, so keep the
            # ordered pointer on heal and retry from a clean settlement view.
            # Keep short collection checks responsive, but honour the longer
            # cooldown requested after an exhaustive camera scan. Ignoring
            # retry_delay here made a failed 96-step scan restart every minute,
            # continuously growing LDPlayer memory until Windows exhausted it.
            healing_hold_delay = max(30.0, float(retry_delay))
            self.routine_next_run[task["id"]] = now + healing_hold_delay
            self._return_to_main_screen(
                max_back_steps=5,
                require_settlement=True,
            )
            self.set_status_message(
                "Лечение не подтверждено: очередь остаётся на heal",
                force=True,
            )
            logger.warning(
                "Healing was not fully confirmed (%s); ordered queue remains on heal",
                reason,
            )
            self.routine_last_outcome = {
                "task_id": "heal",
                "outcome": "retry_pending_collection",
                "reason": reason,
                "completed_steps": sorted(self.routine_completed_steps),
                "actions": int(self.routine_current_action_count),
            }
            self.routine_current_had_action = False
            self.routine_current_action_count = 0
            self.routine_action_counts = {}
            self.routine_completed_steps = set()
            self.routine_action_failure_reason = ""
            self.routine_idle_confirmation_count = 0
            self.routine_home_recovery_attempted = False
            self.routine_idle_guard_visible = False
            self.routine_idle_outside_since = 0.0
            self.routine_idle_recovery_attempted = False
            self.routine_healing_pan_route = []
            self.routine_healing_replay_index = 0
            self.routine_healing_scan_index = 0
            self.routine_healing_settle_checks = 0
            self.routine_healing_search_started = False
            self.routine_healing_saved_route_rejected = False
            self.routine_healing_recenter_attempted = False
            self.routine_task_started_at = time.time()
            self.routine_last_action_time = self.routine_task_started_at
            self.save_config()
            # Avoid a tight unavailable/recovery loop when the task's normal
            # repeat delay is only a couple of seconds, while preserving the
            # five-minute guard requested by a completed full-map scan.
            self._interruptible_sleep(healing_hold_delay)
            return
        self.routine_next_run[task["id"]] = now + retry_delay
        logger.info(
            "Routine %s is temporarily unavailable (%s); retrying in %.0f seconds",
            task.get("id"),
            reason,
            retry_delay,
        )
        if (
            reason != "merchant_absent"
            and not task.get("manual_screen_required", False)
        ):
            self._return_to_main_screen(
                max_back_steps=5,
                require_settlement=routine_requires_settlement(task),
            )
        self.set_status_message(
            f"{self.get_routine_task_name(task)}: {display_reason}. "
            f"Повтор через {max(1, int(retry_delay + 0.999))} сек",
            force=True,
        )
        self.routine_last_outcome = {
            "task_id": str(task.get("id") or ""),
            "outcome": "deferred_unavailable",
            "reason": str(reason),
            "completed_steps": sorted(self.routine_completed_steps),
            "actions": int(self.routine_current_action_count),
        }
        self._advance_routine_after_outcome(task, now)
        if task.get("id") == "processing_factory":
            # The contest is a follow-up to the refinery. Never open it after
            # the factory could not be found/verified: that would preserve the
            # labels' order while skipping the actual smelting collection.
            contest = self.get_routine_task("processing_contest")
            if (
                contest
                and is_task_effectively_enabled(contest)
                and self.routine_tasks
                and self.routine_tasks[
                    int(self.current_routine_index or 0) % len(self.routine_tasks)
                ].get("id")
                == "processing_contest"
            ):
                self.routine_next_run["processing_contest"] = now + retry_delay
                self._advance_routine_after_outcome(contest, now)
                logger.warning(
                    "Processing contest deferred because processing factory was not completed first"
                )
        self.current_routine_task_id = None
        self.routine_current_had_action = False
        self.routine_current_action_count = 0
        self.routine_action_counts = {}
        self.routine_completed_steps = set()
        self.routine_action_failure_reason = ""
        self.routine_idle_confirmation_count = 0
        self.routine_home_recovery_attempted = False
        self.routine_idle_guard_visible = False
        self.routine_idle_outside_since = 0.0
        self.routine_idle_recovery_attempted = False
        self.save_config()
        if self.routine_only_task_id == str(task.get("id") or ""):
            completed_task_id = self.routine_only_task_id
            self.routine_only_task_id = None
            self.routine_mode = False
            self.stop_event.set()
            self._set_state(BotState.STOPPED)
            self.set_status_message(
                f"{self.get_routine_task_name(task)}: {display_reason}. Разовый запуск остановлен",
                force=True,
            )
            logger.info(
                "Standalone routine %s is unavailable; one-shot run stopped",
                completed_task_id,
            )

    def start_normal(self):
        self.routine_mode = False
        self.current_routine_task_id = None
        self.routine_radar_return_hold = False
        self.routine_radar_return_active_seen = False
        self.routine_radar_return_observed_peak = 0
        self.routine_radar_dispatched_this_pass = False
        self.routine_forced_task_queue = []
        self.routine_forced_task_active_id = None
        self.routine_forced_task_return_index = None
        return self.start()

    def start_routines(self, resume=False):
        self.routine_only_task_id = None
        # The main-screen checkboxes are authoritative. Rebuild group states
        # before every run so an older profile cannot silently override them.
        for task in self.routine_tasks:
            group = effective_task_group(task)
            if group:
                self.groups[group] = bool(is_task_effectively_enabled(task))
        enabled_tasks = [
            task for task in self.routine_tasks
            if is_task_effectively_enabled(task)
        ]
        if not enabled_tasks:
            self._show_notification('warning', 'routine_no_enabled')
            return False
        if not any(
            task.get("id") == "game_login"
            or self.get_routine_templates(task, active_only=True)
            for task in enabled_tasks
        ):
            self.set_status_message(self.tr('routine_no_templates'), force=True)
            self._show_notification('warning', 'routine_no_templates')
            return False

        self.routine_mode = True
        for task in self.routine_tasks:
            self.routine_next_run.setdefault(task["id"], 0.0)
        recovering_forced_login = bool(
            getattr(self, "routine_forced_task_active_id", None) == "game_login"
            and getattr(self, "routine_forced_task_return_index", None) is not None
        )
        if resume or recovering_forced_login:
            # Autostart continues the saved ordered pass. Resetting here would
            # repeat completed tasks and reintroduce a long wait at account
            # wrap.  A manual Stop/Start while the launcher-recovery login is
            # running must preserve the same return slot for the same reason.
            self.current_routine_index = int(self.current_routine_index or 0) % len(
                self.routine_tasks
            )
        else:
            # A manual Start means "run the checked list now". Persisted timers
            # resume only after this ordered pass executes every selected task.
            reset_manual_run_deadlines(enabled_tasks, self.routine_next_run)
            self.current_routine_index = 0
            self.routine_pass_completed = False
        if not recovering_forced_login:
            self.routine_forced_task_queue = []
            self.routine_forced_task_active_id = None
            self.routine_forced_task_return_index = None
        # Radar fills every free march slot in one pass.  Never restore the old
        # five-minute single-dispatch hold after an autostart restart.
        self.routine_radar_return_hold = False
        self.routine_radar_return_active_seen = False
        self.routine_radar_return_observed_peak = 0
        self.current_routine_task_id = None
        self.routine_last_action_time = time.time()
        self.routine_current_had_action = False
        logger.info(
            "%s выбранных задач: %s",
            "Продолжение" if (resume or recovering_forced_login) else "Запуск",
            ", ".join(task.get("id", "") for task in enabled_tasks),
        )
        current_account = self.get_current_account()
        if current_account:
            clock_now = time.time()
            if (resume or recovering_forced_login) and not self.routine_pass_completed:
                self._ensure_account_pass_clock(clock_now)
            elif not (resume or recovering_forced_login):
                self._reset_account_pass_clock(clock_now)
            self.save_config()
        return self.start()

    def _running_emulator_targets(self):
        """Return every running LDPlayer that currently answers through ADB."""
        _ldconsole, instances = self._ldplayer_instances()
        running = [item for item in instances if item.running]
        if not running:
            return []
        probe = AdbClient(self.adb_path or None, "")
        try:
            devices = set(probe.list_devices())
        except AdbError as exc:
            logger.warning("Не удалось получить устройства для общего запуска: %s", exc)
            devices = set()

        targets = []
        for instance in running:
            candidates = [
                instance.adb_serial,
                tcp_serial_for_index(instance.index),
                bridged_adb_serial_for_index(instance.index),
            ]
            serial = next((item for item in candidates if item and item in devices), None)
            if serial is None:
                for candidate in candidates[1:]:
                    if not candidate:
                        continue
                    try:
                        probe.connect(candidate)
                        devices = set(probe.list_devices())
                    except AdbError:
                        continue
                    if candidate in devices:
                        serial = candidate
                        break
            if serial and AdbClient(self.adb_path or None, serial).is_responsive():
                targets.append((instance, serial))
            else:
                logger.warning(
                    "LDPlayer %s «%s» пропущен: ADB недоступен",
                    instance.index,
                    instance.name,
                )
        return targets

    def _write_multi_command(self, command):
        self.multi_emulator_command_sequence += 1
        for worker in self.multi_emulator_workers.values():
            try:
                write_worker_command(
                    worker["runtime_dir"],
                    command,
                    self.multi_emulator_command_sequence,
                )
            except OSError:
                logger.exception("Не удалось передать команду скрытому исполнителю")

    def _stop_multi_workers(self):
        if not self.multi_emulator_workers:
            self.multi_emulator_total = 1
            return
        self._write_multi_command("stop")
        workers = list(self.multi_emulator_workers.values())
        self.multi_emulator_workers = {}
        self.multi_emulator_total = 1
        for worker in workers:
            process = worker["process"]
            try:
                process.wait(timeout=2.5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()

    def start_all_emulators(self):
        if self.is_multi_worker:
            return self.start_routines()
        if self.is_running:
            return True

        targets = self._running_emulator_targets()
        if not targets:
            self.set_status_message("Нет доступных по ADB запущенных LDPlayer", force=True)
            self._show_notification('error', 'error', message="Нет доступных по ADB запущенных LDPlayer")
            return False

        current = self.get_current_account() or {}
        preferred_index = int(current.get("ldplayer_index", -1))
        if self.account_rotation_enabled:
            profile_counts = {
                instance.index: sum(
                    1
                    for profile in self.account_profiles
                    if profile.get("enabled", True)
                    and int(profile.get("ldplayer_index", -1)) == instance.index
                )
                for instance, _serial in targets
            }
            preferred_index = max(
                profile_counts,
                key=lambda index: (profile_counts[index], index == preferred_index),
            )
        primary = next((target for target in targets if target[0].index == preferred_index), targets[0])
        if int(current.get("ldplayer_index", -1)) != primary[0].index:
            primary_name = str(primary[0].name or "").casefold()
            matching_profiles = [
                profile
                for profile in self.account_profiles
                if profile.get("enabled", True)
                and int(profile.get("ldplayer_index", -1)) == primary[0].index
            ]
            primary_profile = next(
                (
                    profile
                    for profile in matching_profiles
                    if primary_name
                    and primary_name in {
                        str(profile.get("id") or "").casefold(),
                        str(profile.get("name") or "").casefold(),
                    }
                ),
                matching_profiles[0] if matching_profiles else None,
            )
            if primary_profile:
                self.select_account_profile(primary_profile["id"], save=False)
        self._adopt_adb_serial(primary[1], primary[0].index)
        self.player_index = primary[0].index
        self.player_name = primary[0].name
        self.player_width = primary[0].width or self.player_width
        self.player_height = primary[0].height or self.player_height

        self.save_config()
        source = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        self._stop_multi_workers()
        for instance, serial in targets:
            if instance.index == primary[0].index:
                continue
            runtime_dir = runtime_dir_for_instance(APP_DIR, instance.index)
            runtime_dir.mkdir(parents=True, exist_ok=True)
            worker_config = prepare_worker_config(
                source,
                serial=serial,
                index=instance.index,
                name=instance.name,
                width=instance.width,
                height=instance.height,
            )
            save_json_with_backup(
                runtime_dir / "config.json",
                worker_config,
                backup_dir=runtime_dir / "backups" / "config",
                keep_backups=3,
            )
            control_path = runtime_dir / "control.json"
            try:
                control_path.unlink()
            except FileNotFoundError:
                pass
            env = os.environ.copy()
            env["BUZZBOT_RUNTIME_DIR"] = str(runtime_dir)
            command = worker_launch_command(Path(__file__).resolve())
            kwargs = {
                "cwd": str(APP_DIR),
                "env": env,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(command, **kwargs)
            self.multi_emulator_workers[instance.index] = {
                "process": process,
                "runtime_dir": runtime_dir,
                "name": instance.name,
                "serial": serial,
            }
            logger.info(
                "Скрытый исполнитель запущен: LDPlayer %s «%s» | %s | PID %s",
                instance.index,
                instance.name,
                serial,
                process.pid,
            )

        started = self.start_routines()
        if not started:
            self._stop_multi_workers()
            return False
        self.multi_emulator_total = 1 + len(self.multi_emulator_workers)
        names = ", ".join(instance.name for instance, _serial in targets)
        self.set_status_message(
            f"Работают {self.multi_emulator_total} эмулятора: {names}",
            force=True,
        )
        return True

    def toggle_pause_all_emulators(self):
        if self.is_multi_worker:
            return self.toggle_pause()
        command = "resume" if self.is_paused else "pause"
        changed = self.toggle_pause()
        if changed:
            self._write_multi_command(command)
        return changed

    def stop_all_emulators(self):
        if self.is_multi_worker:
            self.stop()
            return
        self.stop()
        self._stop_multi_workers()

    def start_task_only(self, task_id):
        task = self.get_routine_task(task_id)
        if not task:
            return False
        if task_id == "gathering_boost":
            active_until = gathering_boost_active_until(task)
            if active_until:
                self.routine_next_run[task_id] = active_until
                remaining_minutes = max(1, int((active_until - time.time() + 59.999) // 60.0))
                self.set_status_message(
                    f"Усиление сбора уже активно: повтор через {remaining_minutes} мин",
                    force=True,
                )
                return False
        task["enabled"] = True
        self.groups[effective_task_group(task)] = True
        self.routine_only_task_id = task_id
        self.routine_mode = True
        self.routine_next_run[task_id] = 0.0
        self.routine_forced_task_queue = []
        self.routine_forced_task_active_id = None
        self.routine_forced_task_return_index = None
        self.routine_radar_return_hold = False
        self.routine_radar_return_active_seen = False
        self.routine_radar_return_observed_peak = 0
        self.current_routine_index = 0
        self.routine_pass_completed = False
        self.current_routine_task_id = None
        self.routine_last_action_time = time.time()
        self.routine_current_had_action = False
        return self.start()

    def start_prize_hunt_loop(self):
        return self.start_task_only("prize_hunt")

    def start(self):
        if not self.stop_event.is_set():
            return True
        running_thread = getattr(self, "_thread", None)
        if running_thread is not None and running_thread.is_alive():
            self.set_status_message("Ожидаю завершения предыдущего запуска", force=True)
            return False
        if self.uses_adb and not self.check_runtime_environment(notify=False, wait_seconds=8.0):
            self.set_status_message(self.tr('adb_required', serial=self.adb_serial), force=True)
            self._show_notification('error', 'adb_required', serial=self.adb_serial)
            return False
        if self.work_area_type == 'selected' and self._region is None:
            self._show_notification('warning', 'need_work_area')
            return False

        self.current_cycle_index = 0
        self.last_action_time = time.time()
        self.blocked_coords.clear()
        self.stop_hotkey_pressed = False

        def is_active(img):
            if not img["enabled"]:
                return False
            if img["group"] and img["group"] in self.groups:
                return self.groups[img["group"]]
            return True

        if self.routine_mode:
            routine_groups = {
                task.get("group") for task in self._scheduler_routine_tasks() if task.get("enabled")
            }
            routine_groups.add(SYSTEM_TEMPLATE_GROUP)
            active_images = [
                img for img in self.search_images
                if img.get("group") in routine_groups and is_active(img)
            ]
        else:
            active_images = [img for img in self.search_images if is_active(img)]
        if not active_images:
            self._show_notification('info', 'no_areas')
            return False

        missing = []
        for img in active_images:
            if (
                not os.path.exists(img["path"])
                and not self._missing_template_uses_visual_fallback(img)
            ):
                missing.append(img["description"])
        if missing:
            logger.error(f"Файлы не найдены: {missing}")
            self._show_notification('error', 'error', message=f"Файлы не найдены: {missing}")
            return False

        if self.uses_adb:
            lease = DeviceLease(
                self.adb_serial,
                ldplayer_index=self.player_index,
            )
            if not lease.acquire():
                message = f"Эмулятор {self.adb_serial} уже обслуживается другим BuZzbot"
                logger.warning(message)
                self.set_status_message(message, force=True)
                self._show_notification('warning', 'warning', message=message)
                return False
            self.device_lease = lease

        self.stop_event.clear()
        self._set_state(BotState.RUNNING)
        self.pause_started_at = None
        self.total_paused_duration = 0.0
        self.start_time = time.time()
        self.click_count = 0
        self.set_status_message(f"{self.tr('state_running')}: {self.tr('ready')}", force=True)

        if self.root and self.minimize_on_start:
            self.root.iconify()

        self._thread = threading.Thread(target=self._clicker_loop, daemon=True)
        self._thread.start()
        logger.info("Бот запущен")
        return True

    def stop(self):
        self.stop_event.set()
        self._set_state(BotState.STOPPED)
        self.pause_started_at = None
        self.routine_only_task_id = None
        self.account_switch_task = None
        if self.root and not self.is_multi_worker:
            self.root.deiconify()
        logger.info("Бот остановлен")
        self.set_status_message(self.tr('state_stopped'), force=True)

    def pause(self):
        if not self.is_running or self.is_paused:
            return False
        self._set_state(BotState.PAUSED)
        self.pause_started_at = time.time()
        if self.root and not self.is_multi_worker:
            self.root.deiconify()
        logger.info("Бот поставлен на паузу")
        self.set_status_message(self.tr('state_paused'), force=True)
        return True

    def resume(self):
        if not self.is_running or not self.is_paused:
            return False
        now = time.time()
        paused_for = 0.0
        if self.pause_started_at is not None:
            paused_for = now - self.pause_started_at
            self.total_paused_duration += paused_for
        self.pause_started_at = None
        self._set_state(BotState.RUNNING)
        self.last_action_time = now
        if self.routine_mode:
            self.routine_last_action_time = now
            self.routine_march_deadlines = [
                deadline + paused_for for deadline in self.routine_march_deadlines
            ]
            self.routine_next_run = {
                task_id: deadline + paused_for
                for task_id, deadline in self.routine_next_run.items()
            }
        logger.info("Бот снят с паузы")
        self.set_status_message(self.tr('state_running'), force=True)
        return True

    def toggle_pause(self):
        if self.is_paused:
            return self.resume()
        return self.pause()

    def _show_notification(self, title_key, message_key, type="info", **kwargs):
        if not self.root or self.is_multi_worker:
            if self.is_multi_worker:
                message = kwargs.get("message") or self.tr(message_key, **kwargs)
                logger.warning("Скрытый исполнитель: %s", message)
            return
        self.gui_queue.put((self._show_notification_dialog, (title_key, message_key, kwargs), {}))

    def _show_notification_dialog(self, title_key, message_key, kwargs):
        kwargs = dict(kwargs)
        dialog = tk.Toplevel()
        dialog.title(self.tr(title_key))
        dialog.geometry("400x200")
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.focus_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 400) // 2
        y = (dialog.winfo_screenheight() - 200) // 2
        dialog.geometry(f"400x200+{x}+{y}")
        custom_message = kwargs.pop("message", None)
        message = str(custom_message) if custom_message is not None else self.tr(message_key, **kwargs)
        tk.Label(dialog, text=message, wraplength=350, font=("Arial", 10)).pack(pady=40)
        btn = tk.Button(dialog, text=self.tr('ok'), command=dialog.destroy, width=10)
        btn.pack(pady=20)
        btn.focus_set()
        dialog.bind('<Return>', lambda e: dialog.destroy())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
        dialog.transient()
        dialog.focus_set()
        dialog.lift()

    def _find_template_scaled(self, template_path, region=None, confidence=0.8):
        logger.debug(f"Поиск с масштабированием: диапазон [{self.scale_min}, {self.scale_max}], шагов {self.scale_steps}")
        screen_bgr, origin = self._capture_screen_bgr(region=region)
        screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
        template = self.template_cache.get_gray(template_path)
        if template is None:
            return None, None, 0
        best_val = -1
        best_loc = None
        best_scale = 1.0
        scales = np.linspace(self.scale_min, self.scale_max, self.scale_steps)
        for scale in scales:
            if scale <= 0:
                continue
            resized = self.template_cache.get_scaled_gray(template_path, scale)
            if resized is None:
                continue
            if resized.shape[0] > screen_gray.shape[0] or resized.shape[1] > screen_gray.shape[1]:
                continue
            result = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_scale = scale
        if best_val > confidence:
            left = best_loc[0]
            top = best_loc[1]
            left += origin[0]
            top += origin[1]
            width = int(template.shape[1] * best_scale)
            height = int(template.shape[0] * best_scale)
            center_x = left + width // 2
            center_y = top + height // 2
            return pyautogui.Point(center_x, center_y), (left, top, width, height), best_val
        return None, None, 0

    def _check_orb_match(self, template_path, bbox, match_threshold=None):
        if not isinstance(bbox, tuple) or len(bbox) != 4 or not all(isinstance(v, int) for v in bbox):
            logger.error(f"ORB: некорректный bbox {bbox}, пропускаем проверку")
            return True
        orb_data = self.template_cache.get_orb(template_path)
        kp = orb_data.keypoints
        des = orb_data.descriptors
        logger.info(f"ORB: шаблон {template_path} имеет {len(kp) if kp else 0} ключевых точек")

        if des is None or len(kp) < 5:
            logger.info(f"ORB: недостаточно точек в шаблоне ({len(kp) if kp else 0}) – пропускаем ORB для этого шаблона")
            return True

        screen = self._capture_bbox_bgr(bbox)
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create()
        kp_screen, des_screen = orb.detectAndCompute(screen_gray, None)
        if des_screen is None or len(kp_screen) < 5:
            logger.info(f"ORB: недостаточно точек в найденной области ({len(kp_screen) if kp_screen else 0})")
            return False

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        matches = bf.knnMatch(des, des_screen, k=2)

        good = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < 0.75 * n.distance:
                    good.append(m)

        threshold = self.orb_match_threshold if match_threshold is None else max(1, int(match_threshold))
        logger.info(f"ORB: хороших совпадений {len(good)} (порог {threshold})")
        return len(good) >= threshold

    def _clicker_loop(self):
        pyautogui.PAUSE = 0
        logger.info("Цикл кликера запущен")
        while not self.stop_event.is_set() and not self.stop_hotkey_pressed:
            try:
                if self.is_paused:
                    time.sleep(0.1)
                    continue
                now = time.time()
                if self.routine_mode:
                    current_group_disp = self.current_routine_task_id or "ожидание"
                elif self.cycle_mode and self.cycle_groups:
                    current_group_disp = self.cycle_groups[self.current_cycle_index] if self.cycle_groups else "None"
                else:
                    current_group_disp = "None (обычный режим)"
                logger.info(f"=== Итерация: группа={current_group_disp}, last_action_time={self.last_action_time:.2f}, now={now:.2f}, diff={now - self.last_action_time:.2f}")

                if self.anti_loop_enabled:
                    expired = [coord for coord, unblock in self.blocked_coords.items() if unblock <= now]
                    for coord in expired:
                        del self.blocked_coords[coord]

                current_group = None
                current_routine_task = None
                if self.routine_mode:
                    if self._research_watchdog_due(now):
                        # The visual path has already consumed its cumulative
                        # slot.  Record an explicit deferral rather than letting
                        # repeated animated clicks reset the normal idle timer.
                        self._defer_current_routine_no_action(now)
                        continue
                    if self._drain_expired_account_pass(now):
                        # The next iteration enters the existing confirmed
                        # account-switch path; no remaining task is launched
                        # after the hard task-pass deadline.
                        continue
                    current_routine_task = self._begin_due_routine(now)
                    if current_routine_task is None:
                        time.sleep(max(0.1, min(0.5, self.sleep_not_found)))
                        continue
                    if self._try_global_login_connection_recovery(current_routine_task):
                        continue
                    if (
                        current_routine_task.get("id") == "radar_marches"
                        and bool(
                            current_routine_task.get("settings", {}).get(
                                "dispatch_until_full",
                                False,
                            )
                        )
                        and self._is_settlement_screen_visible()
                    ):
                        # The normal scheduler does not run again while a task
                        # remains current, so its march observation used to stay
                        # stale after the last dispatch.  Re-read the visible
                        # counter on the settlement screen and end the radar
                        # block immediately at 4/4 (or the configured maximum).
                        active_marches = self.get_active_marches(now)
                        if active_marches >= self.routine_max_marches:
                            logger.info(
                                "Radar dispatch capacity reached: %s/%s; advancing to radar_rewards",
                                active_marches,
                                self.routine_max_marches,
                            )
                            self.set_status_message(
                                f"Радар: все походы заняты {active_marches}/{self.routine_max_marches}; "
                                "перехожу к наградам",
                                force=True,
                            )
                            self._finish_current_routine(now)
                            continue
                    if self._pause_for_manual_account_verification(current_routine_task):
                        continue
                    current_group = effective_task_group(current_routine_task)
                    system_images = [
                        img for img in self.search_images
                        if (
                            img.get("group") == SYSTEM_TEMPLATE_GROUP
                            and self._is_active(img)
                            and image_is_allowed_for_routine(
                                img,
                                current_routine_task.get("id"),
                                routine_started=(
                                    current_routine_task.get("id") != "game_login"
                                    and bool(
                                        self.routine_current_had_action
                                        or self.routine_completed_steps
                                    )
                                ),
                            )
                        )
                    ]
                    active_images = [
                        img for img in self.search_images
                        if (
                            img.get("group") == current_group
                            and self._is_active(img)
                            and not self._missing_template_uses_visual_fallback(img)
                            and not (
                                current_routine_task.get("id") == "__account_switch__"
                                and self.account_switch_selected_at
                            )
                            and runtime_step_is_ready(img, self.routine_completed_steps)
                            and healing_pending_allows_image(
                                img,
                                current_routine_task,
                            )
                        )
                    ]
                    active_images.sort(key=lambda img: int(img.get("routine_priority", 100)))
                    active_images = system_images + active_images
                    logger.info(f"Рутинная задача {current_group}: активных областей {len(active_images)}")
                elif self.cycle_mode and self.cycle_groups:
                    current_group = self.cycle_groups[self.current_cycle_index]
                    active_images = [img for img in self.search_images
                                     if img.get("group") == current_group and self._is_active(img)]
                    logger.info(f"Группа {current_group}: активных областей {len(active_images)}")
                    self.set_status_message(f"Сканирование группы: {current_group}")
                else:
                    active_images = [img for img in self.search_images if self._is_active(img)]
                    logger.info(f"Обычный режим: активных областей {len(active_images)}")
                    self.set_status_message(f"Активных областей: {len(active_images)}")

                if (
                    self.routine_mode
                    and current_routine_task
                    and is_radar_task_id(current_routine_task.get("id"))
                    and self._try_radar_in_progress_card_fallback(
                        current_routine_task
                    )
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task
                    and current_routine_task.get("id") == "heal"
                    and current_routine_task.get("settings", {}).get(
                        "_collection_pending",
                        False,
                    )
                    and current_routine_task.get("settings", {}).get(
                        "_hospital_target"
                    )
                    and self._try_healing_visual_fallback(
                        current_routine_task,
                        remembered_only=True,
                    )
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task
                    and current_routine_task.get("id") in {"mysterious_merchant", "trucks"}
                    and not self.get_routine_templates(
                        current_routine_task,
                        active_only=True,
                    )
                ):
                    if (
                        current_routine_task.get("id") == "mysterious_merchant"
                        and self._try_mysterious_merchant_visual_fallback(
                            current_routine_task
                        )
                    ) or (
                        current_routine_task.get("id") == "trucks"
                        and self._try_trucks_visual_fallback(current_routine_task)
                    ):
                        continue

                if not active_images:
                    self.set_status_message("Нет активных областей", force=True)
                    if self.routine_mode and current_routine_task:
                        if self._routine_idle_completion_ready(current_routine_task) or (
                            self.routine_current_had_action
                            and not current_routine_task.get("complete_when_idle")
                            and not current_routine_task.get("completion_uid")
                            and self._routine_runtime_completion_ready(current_routine_task)
                        ):
                            self._finish_current_routine(now)
                        elif current_routine_task.get("complete_when_idle"):
                            self.routine_last_action_time = now
                        else:
                            self._defer_current_routine_no_action(now)
                        continue
                    if self.cycle_mode and self.cycle_groups:
                        idle = time.time() - self.last_action_time
                        logger.info(f"Нет активных областей, idle = {idle:.2f} / {self.cycle_timeout}")
                        if idle > self.cycle_timeout:
                            logger.info(f"*** ПЕРЕКЛЮЧЕНИЕ: idle {idle:.2f} > {self.cycle_timeout} ***")
                            self._switch_to_next_group()
                            continue
                    time.sleep(self.sleep_not_found)
                    continue

                action_occurred = False
                refresh_after_action = False
                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "research"
                    and self._try_research_visual_fallback(current_routine_task)
                ):
                    # A finished 1/1 research can expose Collect at the same
                    # time as the generic tree selector.  Collect/start always
                    # wins so the selector cannot skip the pending result.
                    continue
                if self.uses_adb:
                    with self._adb_capture_lock:
                        self._adb_iteration_frame = self._capture_adb_frame(force=True)
                radar_card_visible = False
                if self.routine_mode and is_radar_task_id(current_routine_task.get("id")):
                    try:
                        radar_frame, _radar_origin = self._capture_screen_bgr()
                        radar_card_visible = (
                            detect_radar_card_action_target(radar_frame) is not None
                        )
                    except Exception:
                        logger.exception("Radar card guard could not inspect the current screen")
                iteration_plan = build_group_iteration_plan(
                    active_images,
                    self.group_execution,
                    cycle_mode=self.cycle_mode and not self.routine_mode,
                    cycle_groups=[current_group] if self.routine_mode else self.cycle_groups,
                    current_cycle_index=0 if self.routine_mode else self.current_cycle_index,
                )

                for group_plan in iteration_plan:
                    group_name = group_plan["group"]
                    group_images = group_plan["images"]
                    if group_name:
                        self.set_status_message(f"Группа: {group_name} | Областей: {len(group_images)}")

                    for image_index, img_config in enumerate(group_images):
                        if self.stop_event.is_set() or self.stop_hotkey_pressed or self.is_paused:
                            break

                        if (
                            radar_card_visible
                            and is_radar_task_id(current_routine_task.get("id"))
                            and img_config.get("runtime_step") == "radar_marker"
                        ):
                            logger.debug(
                                "Radar marker skipped while a task card is open: %s",
                                img_config.get("description"),
                            )
                            continue

                        if img_config["group"] and img_config["group"] in self.groups:
                            if not self.groups[img_config["group"]]:
                                continue
                        if img_config.get("guard_only"):
                            continue
                        if (
                            img_config.get("requires_settlement_screen")
                            and not self._is_settlement_screen_visible()
                        ):
                            continue

                        if not setting_requirement_matches(
                            img_config,
                            current_routine_task.get("settings", {}),
                        ):
                            continue
                        if (
                            current_routine_task.get("id") == "prize_hunt"
                            and not prize_hunt_branch_allows_image(
                                img_config,
                                current_routine_task.get("settings", {}).get(
                                    "repeat_until_stopped",
                                    True,
                                ),
                            )
                        ):
                            continue

                        self.set_status_message(f"Проверка: {img_config['description']}")

                        guard_uids = img_config.get("skip_if_visible_uids") or ()
                        if isinstance(guard_uids, str):
                            guard_uids = (guard_uids,)
                        guard_uids = [str(uid) for uid in guard_uids if str(uid)]
                        legacy_guard_uid = str(img_config.get("skip_if_uid_visible") or "")
                        if legacy_guard_uid and legacy_guard_uid not in guard_uids:
                            guard_uids.append(legacy_guard_uid)
                        skip_guarded_action = False
                        for guard_uid in guard_uids:
                            guard_image = next(
                                (image for image in group_images if image.get("uid") == guard_uid),
                                None,
                            )
                            if not guard_image:
                                continue
                            guard_location, guard_bbox, _guard_confidence = self._locate_image(guard_image)
                            guard_is_valid = False
                            if guard_location and guard_bbox:
                                guard_is_valid, _guard_reject_reason = self._validate_detected_match(
                                    guard_image,
                                    guard_bbox,
                                )
                            if guard_is_valid:
                                logger.debug(
                                    "Пропуск %s: защитный шаблон %s уже виден",
                                    img_config.get("description"),
                                    guard_image.get("description"),
                                )
                                skip_guarded_action = True
                                break
                        if skip_guarded_action:
                            continue

                        required_visible_uid = str(img_config.get("requires_visible_uid") or "")
                        if required_visible_uid:
                            required_image = next(
                                (image for image in group_images if image.get("uid") == required_visible_uid),
                                None,
                            )
                            if required_image is None:
                                logger.warning(
                                    "Пропуск %s: обязательный защитный шаблон %s отсутствует",
                                    img_config.get("description"),
                                    required_visible_uid,
                                )
                                continue
                            required_location, _required_bbox, _required_confidence = self._locate_image(
                                required_image
                            )
                            if not required_location:
                                logger.debug(
                                    "Пропуск %s: обязательный шаблон %s не виден",
                                    img_config.get("description"),
                                    required_image.get("description"),
                                )
                                continue

                        last_used = img_config.get("last_used", 0)
                        cooldown = img_config.get("cooldown", 1.5)
                        time_since = now - last_used
                        if time_since < cooldown:
                            logger.debug(f"Кулдаун {img_config['description']}: прошло {time_since:.1f} / {cooldown}")
                            continue

                        try:
                            location, bbox, _confidence = self._locate_image(img_config)

                            if location and bbox:
                                if (
                                    is_radar_task_id(current_routine_task.get("id"))
                                    and img_config.get("runtime_step") == "radar_marker"
                                    and radar_marker_requires_notification(
                                        img_config,
                                        current_routine_task.get("id"),
                                    )
                                ):
                                    radar_frame, _radar_origin = self._capture_screen_bgr()
                                    if (
                                        not radar_marker_has_notification(radar_frame, bbox)
                                    ):
                                        logger.info(
                                            "Radar marker rejected without notification dot: %s @ %s",
                                            img_config.get("description"),
                                            bbox,
                                        )
                                        continue
                                if self.anti_loop_enabled:
                                    coord_key = (
                                        img_config.get("uid") or img_config.get("path"),
                                        round(location.x),
                                        round(location.y),
                                    )
                                    if coord_key in self.blocked_coords:
                                        logger.debug(f"Блокировка координат {coord_key} для {img_config['description']}")
                                        self.set_status_message(f"Координаты заблокированы: {img_config['description']}")
                                        continue

                                is_valid, reject_reason = self._validate_detected_match(img_config, bbox)
                                if not is_valid:
                                    self.set_status_message(
                                        f"{reject_reason} отклонил: {img_config['description']}"
                                    )
                                    continue

                                if (
                                    is_radar_task_id(current_routine_task.get("id"))
                                    and img_config.get("prevents_idle_completion")
                                    and radar_marker_was_confirmed(
                                        img_config.get("uid") or img_config.get("path"),
                                        location.x,
                                        location.y,
                                        self.routine_radar_confirmed_marker_keys,
                                    )
                                ):
                                    logger.debug(
                                        "Пропуск отложенного значка радара: %s",
                                        img_config.get("description"),
                                    )
                                    continue

                                if not self._is_action_allowed(img_config):
                                    self.set_status_message(
                                        f"Пропущено премиальное действие: {img_config['description']}",
                                        force=True,
                                    )
                                    continue

                                self.set_status_message(
                                    f"Найдено: {img_config['description']} ({bbox[0]},{bbox[1]})"
                                )
                                if (
                                    is_radar_task_id(current_routine_task.get("id"))
                                    and img_config.get("prevents_idle_completion")
                                ):
                                    # Remember the marker before executing its action. Some
                                    # radar cards open even when their post-click verifier
                                    # rejects the resulting screen. The countdown guard must
                                    # still be able to confirm and suppress that marker.
                                    self.routine_radar_pending_marker_key = (
                                        img_config.get("uid") or img_config.get("path"),
                                        round(location.x),
                                        round(location.y),
                                    )
                                action_confirmed = self._execute_action(img_config, location)
                                if action_confirmed is False:
                                    logger.warning(
                                        "Действие не подтверждено экраном: %s",
                                        img_config.get("description"),
                                    )
                                    if self.routine_action_failure_reason == "stamina":
                                        self._defer_current_routine_unavailable(
                                            "не хватает выносливости или закончились предметы",
                                            time.time(),
                                            retry_delay=60.0,
                                        )
                                        refresh_after_action = True
                                        break
                                    if (
                                        self.routine_mode
                                        and current_routine_task.get("id") == "research"
                                        and img_config.get("group")
                                        != SYSTEM_TEMPLATE_GROUP
                                    ):
                                        # A failed laboratory or node action is
                                        # not permission to try another template
                                        # every few seconds. Keep the pointer on
                                        # research and use its bounded retry.
                                        self._defer_current_routine_no_action(
                                            time.time()
                                        )
                                        refresh_after_action = True
                                        break
                                    continue
                                self.stats[img_config["path"]] = self.stats.get(img_config["path"], 0) + 1
                                self.click_count += 1
                                action_occurred = True
                                is_system_template = img_config.get("group") == SYSTEM_TEMPLATE_GROUP
                                defer_reason = str(img_config.get("defer_routine_reason") or "")
                                if self.routine_mode and not is_system_template and defer_reason:
                                    self._defer_current_routine_unavailable(
                                        defer_reason,
                                        time.time(),
                                    )
                                    refresh_after_action = True
                                elif self.routine_mode and not is_system_template:
                                    self.routine_current_had_action = True
                                    self.routine_last_action_time = time.time()
                                    self.routine_idle_confirmation_count = 0
                                    if (
                                        is_radar_task_id(current_routine_task.get("id"))
                                        and img_config.get("prevents_idle_completion")
                                    ):
                                        self.routine_radar_pending_marker_key = (
                                            img_config.get("uid") or img_config.get("path"),
                                            round(location.x),
                                            round(location.y),
                                        )
                                    runtime_step = str(img_config.get("runtime_step") or "")
                                    if runtime_step:
                                        if (
                                            current_routine_task.get("id") == "radar_marches"
                                            and runtime_step == "radar_march"
                                        ):
                                            self.routine_radar_dispatched_this_pass = True
                                        if (
                                            is_radar_task_id(current_routine_task.get("id"))
                                            and runtime_step == "radar_marker"
                                        ):
                                            reset_radar_card_runtime_steps(
                                                self.routine_completed_steps
                                            )
                                        self.routine_completed_steps.update(
                                            completed_runtime_steps_for_image(img_config)
                                        )
                                        logger.info(
                                            "Шаг сценария подтверждён: %s | выполнено=%s",
                                            runtime_step,
                                            sorted(self.routine_completed_steps),
                                        )
                                    if (
                                        is_radar_task_id(current_routine_task.get("id"))
                                        and img_config.get("confirms_radar_marker")
                                    ):
                                        self._confirm_pending_radar_marker()
                                    complete_if_false = str(
                                        img_config.get("complete_if_setting_false") or ""
                                    )
                                    if (
                                        complete_if_false
                                        and not bool(
                                            current_routine_task.get("settings", {}).get(
                                                complete_if_false,
                                                False,
                                            )
                                        )
                                    ):
                                        self._finish_current_routine(self.routine_last_action_time)
                                        refresh_after_action = True
                                    if (
                                        self.current_routine_task_id is not None
                                        and img_config.get("completes_routine", False)
                                    ):
                                        self._finish_current_routine(
                                            self.routine_last_action_time,
                                            completion_clicked=True,
                                        )
                                        refresh_after_action = True
                                    if (
                                        self.current_routine_task_id is not None
                                        and self.routine_action_completes_task
                                    ):
                                        self.routine_action_completes_task = False
                                        self._finish_current_routine(
                                            self.routine_last_action_time,
                                            completion_clicked=True,
                                        )
                                        refresh_after_action = True
                                    limit_key = str(img_config.get("limit_key") or "")
                                    if limit_key:
                                        self.routine_current_action_count += 1
                                        self.routine_action_counts[limit_key] = (
                                            self.routine_action_counts.get(limit_key, 0) + 1
                                        )
                                        limit = int(current_routine_task.get("settings", {}).get(limit_key, 0) or 0)
                                        if (
                                            current_routine_task.get("id") == "alliance_donations"
                                            and limit_key == "max_project_checks"
                                        ):
                                            self.set_status_message(
                                                "Пожертвования: проверено проектов "
                                                f"{self.routine_action_counts[limit_key]}/{limit}",
                                                force=True,
                                            )
                                        if limit > 0 and self.routine_action_counts[limit_key] >= limit:
                                            if img_config.get("defer_when_limit_reached", False):
                                                self._defer_current_routine_unavailable(
                                                    limit_key,
                                                    self.routine_last_action_time,
                                                )
                                            else:
                                                self._finish_current_routine(self.routine_last_action_time)
                                            refresh_after_action = True
                                    completion_uid = current_routine_task.get("completion_uid") or ""
                                    if (
                                        self.current_routine_task_id is not None
                                        and completion_uid
                                        and img_config.get("uid") == completion_uid
                                    ):
                                        self._finish_current_routine(
                                            self.routine_last_action_time,
                                            completion_clicked=True,
                                        )
                                    refresh_after_action = True
                                elif self.routine_mode and is_system_template:
                                    if current_routine_task.get("id") == "game_login":
                                        self.routine_last_action_time = time.time()
                                        self.routine_idle_confirmation_count = 0
                                    refresh_after_action = True
                                if self.anti_loop_enabled:
                                    default_block = cooldown if img_config.get("allow_repeat", False) else self.block_duration
                                    block_seconds = max(0.1, float(img_config.get("block_seconds", default_block)))
                                    self.blocked_coords[coord_key] = time.time() + block_seconds
                                if group_plan["delay_between"] > 0 and image_index < len(group_images) - 1:
                                    self.set_status_message(
                                        f"Пауза между областями: {group_plan['delay_between']:.1f} сек"
                                    )
                                    self._interruptible_sleep(group_plan["delay_between"])
                                time.sleep(0.1)
                                if refresh_after_action:
                                    break
                        except Exception:
                            logger.exception(f"Ошибка при обработке области {img_config.get('description')}:")
                            continue

                    if self.stop_event.is_set() or self.stop_hotkey_pressed or self.is_paused or refresh_after_action:
                        break
                    if group_plan["group"] and group_plan["delay_after"] > 0:
                        self.set_status_message(
                            f"Пауза после группы {group_plan['group']}: {group_plan['delay_after']:.1f} сек"
                        )
                        self._interruptible_sleep(group_plan["delay_after"])

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_igg_game_confirmation(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_igg_rejected_login(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_connection_recovery(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_igg_confirmation(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_igg_id_selection(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_return_to_main(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_igg_login(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_google_chooser(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_saved_password(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "__account_switch__"
                    and not action_occurred
                    and self._try_account_switch_visual_fallback(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "game_login"
                    and not action_occurred
                    and self._try_game_login_visual_fallback(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "mail_rewards"
                    and not action_occurred
                    and self._try_mail_visual_fallback(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "fence_survivors"
                    and not action_occurred
                    and self._try_fence_survivors_visual_fallback(
                        current_routine_task
                    )
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id")
                    in {"processing_factory", "processing_contest"}
                    and not action_occurred
                    and self._try_processing_factory_visual_fallback(
                        current_routine_task
                    )
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "research"
                    and not action_occurred
                    and self._try_research_visual_fallback(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "heal"
                    and not action_occurred
                    and self._try_healing_visual_fallback(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "collective_mind"
                    and not action_occurred
                    and self._try_collective_tutorial_fallback(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and current_routine_task.get("id") == "prize_hunt"
                    and not action_occurred
                    and self._try_prize_hunt_confirmation_fallback(current_routine_task)
                ):
                    continue

                if (
                    self.routine_mode
                    and is_radar_task_id(current_routine_task.get("id"))
                    and not action_occurred
                    and self._try_radar_visual_fallback(current_routine_task)
                ):
                    continue

                if self.routine_mode:
                    if refresh_after_action or self.current_routine_task_id is None:
                        continue
                    idle = time.time() - self.routine_last_action_time
                    if current_routine_task.get("id") == "__account_switch__":
                        elapsed = time.time() - self.routine_task_started_at
                        timeout = float(current_routine_task.get("timeout_seconds", 120.0))
                        if self.account_switch_error or self.account_switch_probe_ready:
                            self._finish_current_routine(time.time())
                            continue
                        if self.account_switch_selected_at:
                            if (
                                time.time() - self.account_switch_selected_at >= 8.0
                                and self._account_switch_main_screen_confirmed(
                                    current_routine_task
                                )
                            ):
                                self.account_switch_confirmed = True
                                self._finish_current_routine(time.time())
                            elif elapsed >= timeout:
                                self.account_switch_error = (
                                    "Переключение не завершено: главный экран игры не появился"
                                )
                                self._finish_current_routine(time.time())
                            elif (
                                current_routine_task.get("settings", {}).get("login_method") == "igg"
                                and time.time() - self.account_switch_selected_at >= 15.0
                            ):
                                try:
                                    igg_form_visible = bool(
                                        extract_igg_login_form(self.adb_client.ui_xml())
                                    )
                                except AdbError:
                                    igg_form_visible = False
                                if igg_form_visible:
                                    self.account_switch_error = (
                                        "IGG не завершил вход: проверьте логин и пароль"
                                    )
                                    self._finish_current_routine(time.time())
                            continue
                        if elapsed >= timeout:
                            login_method = current_routine_task.get("settings", {}).get(
                                "login_method", "igg"
                            )
                            self.account_switch_error = (
                                f"Переключение не выполнено: окно входа {login_method.upper()} не найдено"
                            )
                            self._finish_current_routine(time.time())
                        continue
                    if current_routine_task.get("id") == "game_login":
                        if self._is_main_screen_visible():
                            self.routine_idle_confirmation_count += 1
                            task_elapsed = time.time() - self.routine_task_started_at
                            if (
                                task_elapsed >= GAME_LOGIN_MINIMUM_SECONDS
                                and idle >= GAME_LOGIN_STABLE_SECONDS
                                and self.routine_idle_confirmation_count >= 3
                            ):
                                self.set_status_message(
                                    "Вход в игру выполнен: главный экран стабилен",
                                    force=True,
                                )
                                self._finish_current_routine(time.time())
                            continue
                        self.routine_idle_confirmation_count = 0
                        if (
                            self.uses_adb
                            and self.routine_login_restart_count < GAME_LOGIN_MAX_RESTARTS
                            and idle >= GAME_LOGIN_RESTART_SECONDS
                            and self._restart_game_for_login()
                        ):
                            continue
                    timeout = float(current_routine_task.get("timeout_seconds", 8.0))
                    idle_check_timeout = routine_idle_check_timeout(
                        current_routine_task,
                        self.routine_current_had_action,
                    )
                    if not action_occurred and no_available_squad_wait_exceeded(
                        current_routine_task,
                        self.routine_completed_steps,
                        idle,
                    ):
                        self._defer_current_routine_no_squad(time.time())
                        continue
                    if not action_occurred and routine_missing_followup_is_unavailable(
                        current_routine_task,
                        self.routine_completed_steps,
                        idle,
                    ):
                        unavailable_reason = (
                            "boost_item_unavailable"
                            if current_routine_task.get("id") == "gathering_boost"
                            else (
                                "исследование пустоши недоступно или аккаунт не зарегистрирован"
                                if current_routine_task.get("id") == "wasteland_exploration"
                                else "событие конкурса сейчас не проводится"
                            )
                        )
                        self._defer_current_routine_unavailable(
                            unavailable_reason,
                            time.time(),
                        )
                        continue
                    if (
                        not action_occurred
                        and current_routine_task.get("id") == "processing_contest"
                        and "open_contest" in self.routine_completed_steps
                        and idle >= 10.0
                    ):
                        # The contest screen was positively confirmed. If no
                        # claim/action appears after it settles, the event has
                        # nothing available; do not wait for a second guard
                        # template for a full minute.
                        self.set_status_message(
                            "Конкурс по обработке: доступных наград нет",
                            force=True,
                        )
                        logger.info(
                            "Processing contest screen remained idle after confirmation; completing the check"
                        )
                        self._finish_current_routine(time.time())
                        continue
                    if not action_occurred and idle >= idle_check_timeout:
                        if donation_exhaustion_is_complete(
                            current_routine_task,
                            self.routine_completed_steps,
                            idle,
                        ):
                            self.set_status_message(
                                "Пожертвования: все доступные проекты проверены",
                                force=True,
                            )
                            self._finish_current_routine(time.time())
                            continue
                        if current_routine_task.get("manual_screen_required", False):
                            guard_uid = str(
                                current_routine_task.get("idle_completion_guard_uid") or ""
                            )
                            if guard_uid and not self._template_uid_is_visible(guard_uid):
                                self._defer_current_routine_unavailable(
                                    "сначала откройте радарную станцию",
                                    time.time(),
                                )
                                continue
                        if current_routine_task.get("id") == "game_login":
                            self.routine_home_recovery_attempted = True
                            self.set_status_message(
                                "Вход в игру: возвращаюсь на главный экран",
                                force=True,
                            )
                            if self._return_to_main_screen(max_back_steps=5):
                                self._finish_current_routine(time.time())
                            else:
                                self._defer_current_routine_no_action(time.time())
                            continue
                        if self._retry_current_resource_search(current_routine_task):
                            continue
                        if (
                            current_routine_task.get("empty_home_is_success")
                            and self._is_main_screen_visible()
                        ):
                            self.set_status_message(
                                f"{self.get_routine_task_name(current_routine_task)}: доступных действий нет",
                                force=True,
                            )
                            self._finish_current_routine(time.time())
                            continue
                        if routine_home_recovery_due(
                            current_routine_task,
                            self.routine_current_had_action,
                            self.routine_home_recovery_attempted,
                            idle,
                        ) and self._try_recover_current_routine_home(current_routine_task):
                            continue
                        if processing_restart_stall_should_defer(
                            current_routine_task,
                            self.routine_current_had_action,
                            self.routine_home_recovery_attempted,
                            idle,
                            self.routine_completed_steps,
                        ):
                            logger.warning(
                                "Routine %s still has no confirmed action after restart recovery; deferring",
                                current_routine_task.get("id"),
                            )
                            self._defer_current_routine_no_action(time.time())
                            continue
                        if self._routine_idle_completion_ready(current_routine_task) or (
                            self.routine_current_had_action
                            and not current_routine_task.get("complete_when_idle")
                            and not current_routine_task.get("completion_uid")
                            and self._routine_runtime_completion_ready(current_routine_task)
                        ):
                            self._finish_current_routine(time.time())
                        elif current_routine_task.get("complete_when_idle"):
                            if self.routine_idle_guard_visible:
                                self.routine_idle_outside_since = 0.0
                            elif self.routine_idle_outside_since <= 0:
                                self.routine_idle_outside_since = time.time()
                            outside_seconds = (
                                time.time() - self.routine_idle_outside_since
                                if self.routine_idle_outside_since > 0
                                else 0.0
                            )
                            if routine_idle_screen_abort_due(
                                current_routine_task,
                                self.routine_idle_recovery_attempted,
                                outside_seconds,
                            ):
                                self._defer_current_routine_unavailable(
                                    "экран завершения не найден после возврата",
                                    time.time(),
                                )
                                continue
                            if routine_idle_screen_recovery_due(
                                current_routine_task,
                                self.routine_current_had_action,
                                self.routine_idle_guard_visible,
                                self.routine_idle_recovery_attempted,
                                outside_seconds,
                            ):
                                if self._try_recover_current_routine_idle_screen(
                                    current_routine_task
                                ):
                                    continue
                                self._defer_current_routine_unavailable(
                                    "не удалось вернуться из постороннего окна",
                                    time.time(),
                                )
                                continue
                            self.routine_last_action_time = time.time()
                            logger.info(
                                "Routine %s is idle outside its completion screen for %.1f sec; continuing",
                                current_routine_task.get("id"),
                                outside_seconds,
                            )
                        else:
                            self._defer_current_routine_no_action(time.time())
                        continue
                elif self.cycle_mode and self.cycle_groups:
                    idle = time.time() - self.last_action_time
                    logger.info(f"Таймер бездействия: idle = {idle:.2f} / {self.cycle_timeout}, группа {current_group}")
                    if idle > self.cycle_timeout:
                        logger.info(f"*** ПЕРЕКЛЮЧЕНИЕ: idle {idle:.2f} > {self.cycle_timeout} ***")
                        self._switch_to_next_group()
                        continue

                time.sleep(self.sleep_not_found)

            except Exception as e:
                logger.error(f"Критическая ошибка в цикле: {e}")
                time.sleep(self.sleep_error)

        self._set_state(BotState.STOPPED)
        device_lease = getattr(self, "device_lease", None)
        if device_lease is not None:
            device_lease.release()
            self.device_lease = None
        logger.info("Цикл кликера завершён")
        self.set_status_message(self.tr('state_stopped'), force=True)
        if self.root:
            self.gui_queue.put((self.root.deiconify, (), {}))

    def _switch_to_next_group(self):
        if not self.cycle_groups:
            return
        old_index = self.current_cycle_index
        self.current_cycle_index = (self.current_cycle_index + 1) % len(self.cycle_groups)
        self.last_action_time = time.time()
        logger.info(f"Переключение с группы {self.cycle_groups[old_index]} на {self.cycle_groups[self.current_cycle_index]}")
        self.set_status_message(
            f"Переключение: {self.cycle_groups[old_index]} -> {self.cycle_groups[self.current_cycle_index]}",
            force=True,
        )

    def _is_active(self, img):
        if img.get("observer_only"):
            return False
        if not img["enabled"]:
            return False
        if img["group"] and img["group"] in self.groups:
            return self.groups[img["group"]]
        return True

    def _missing_template_uses_visual_fallback(self, image):
        """Allow a missing radar opener when the guarded visual opener is enabled."""
        path = str(image.get("path") or "")
        if not path or os.path.exists(path) or not self.routine_mode:
            return False
        image_uid = str(image.get("uid") or "")
        image_group = image.get("group")
        for task in self._scheduler_routine_tasks():
            task_id = str(task.get("id") or "")
            if (
                is_radar_task_id(task_id)
                and task.get("settings", {}).get("visual_fallback", False)
                and effective_task_group(task) == image_group
                and image_uid
                == str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:open_radar"))
            ):
                return True
        return False

    def _current_task_settings(self):
        task = self.get_routine_task(self.current_routine_task_id)
        return task.get("settings", {}) if task else {}

    def _resolve_action_numbers(self, img_config):
        setting_key = str(img_config.get("setting_key") or "").strip()
        if setting_key:
            value = self._current_task_settings().get(setting_key)
            if value is not None:
                return [str(value)]
        return img_config.get("numbers", [])

    def _is_action_allowed(self, img_config):
        if not img_config.get("premium_action", False):
            return True
        settings = self._current_task_settings()
        return not settings.get("avoid_gems", True)

    def _detect_resource_result_level(self, img_config):
        level_uids = img_config.get("result_level_template_uids") or {}
        if not isinstance(level_uids, dict):
            return None
        matches = []
        scores = []
        for level_text, uid in level_uids.items():
            level_image = next(
                (
                    image for image in self.search_images
                    if str(image.get("uid") or "") == str(uid or "")
                ),
                None,
            )
            if level_image is None:
                continue
            location, bbox, confidence = self._locate_image(level_image)
            scores.append((level_text, confidence))
            if location is None or bbox is None:
                continue
            valid, _reason = self._validate_detected_match(level_image, bbox)
            if valid:
                matches.append((level_text, confidence))
        logger.info(
            "Resource result level scores: %s; valid: %s",
            ", ".join(f"{level}={confidence:.3f}" for level, confidence in scores),
            ", ".join(f"{level}={confidence:.3f}" for level, confidence in matches) or "none",
        )
        return select_best_resource_result_level(matches, raw_matches=scores)

    def _resource_result_level_rejected(self, img_config):
        setting_key = str(img_config.get("expected_result_level_setting") or "")
        if not setting_key:
            return False
        expected = int(self._current_task_settings().get(setting_key, 7) or 7)
        level_uids = img_config.get("result_level_template_uids") or {}
        if str(expected) not in level_uids:
            return False
        detected = self._detect_resource_result_level(img_config)
        if detected == expected:
            self.set_status_message(f"Подтверждён ресурс уровня {expected}", force=True)
            return False

        detected_label = str(detected) if detected is not None else "не распознан"
        logger.warning(
            "Resource result rejected: expected level %s, detected %s",
            expected,
            detected_label,
        )
        self.set_status_message(
            f"Ресурс отклонён: нужен уровень {expected}, найден {detected_label}",
            force=True,
        )
        try:
            if self.uses_adb:
                self.adb_client.keyevent(4)
            else:
                pyautogui.press("escape")
        except Exception:
            logger.exception("Не удалось закрыть карточку ресурса неверного уровня")
        self._invalidate_capture()
        img_config["last_used"] = time.time()
        task = self.get_routine_task(self.current_routine_task_id) or {}
        timeout = float(task.get("timeout_seconds", 8.0) or 8.0)
        self.routine_last_action_time = time.time() - timeout - 0.1
        return True

    def _configure_healing_troop_count(self, troop_count, frame):
        """Enter a bounded healing amount only while the numeric editor is visible."""
        scale_x = frame.shape[1] / 1280.0
        scale_y = frame.shape[0] / 720.0
        auto_x, auto_y = int(round(810 * scale_x)), int(round(678 * scale_y))
        clear_x, clear_y = int(round(1195 * scale_x)), int(round(468 * scale_y))
        field_x = int(round(1085 * scale_x))
        ok_x, ok_y = int(round(1198 * scale_x)), int(round(669 * scale_y))
        row_positions = (173, 263, 353, 443)
        troop_limit = max(1, int(troop_count))

        if healing_auto_fill_is_checked(frame):
            if self.uses_adb:
                self.adb_client.tap(auto_x, auto_y)
            else:
                pyautogui.click(auto_x, auto_y)
            self._invalidate_capture()
            self._interruptible_sleep(0.35)
            frame, _origin = self._capture_screen_bgr(force=True)
            if healing_auto_fill_is_checked(frame):
                logger.warning("Healing auto-fill could not be disabled safely")
                self.set_status_message(
                    "Лечение не запущено: не удалось отключить авто-пополнение",
                    force=True,
                )
                return False

        # The game can preselect every wounded troop even with auto-fill
        # disabled. Always use its global down-arrow clear control before
        # editing individual rows. Without this step, hidden rows can retain
        # hundreds of thousands of troops and make the final Heal tap unsafe.
        if self.uses_adb:
            self.adb_client.tap(clear_x, clear_y)
        else:
            pyautogui.click(clear_x, clear_y)
        self._invalidate_capture()
        self._interruptible_sleep(0.35)
        frame, _origin = self._capture_screen_bgr(force=True)
        if not healing_selection_is_empty(frame):
            logger.error("Healing global troop reset was not confirmed")
            self.set_status_message(
                "Лечение не запущено: общий сброс войск не подтверждён",
                force=True,
            )
            return False
        logger.info("Healing global troop selection cleared safely")

        def configure_row(row_index, row_y, quota):
            if self.stop_event.is_set() or self.stop_hotkey_pressed:
                return False
            target_y = int(round(row_y * scale_y))
            if self.uses_adb:
                self.adb_client.tap(field_x, target_y)
            else:
                pyautogui.click(field_x, target_y)
            self._invalidate_capture()
            self._interruptible_sleep(0.20)

            editor_frame, _origin = self._capture_screen_bgr(force=True)
            if not healing_number_editor_is_open(editor_frame):
                logger.warning(
                    "Healing row %s is not available",
                    row_index,
                )
                return None

            if self.uses_adb:
                self.adb_client.clear_focused_text(20)
                self.adb_client.input_text(str(quota))
            else:
                pyautogui.hotkey("ctrl", "a")
                pyautogui.write(str(quota))
            self._invalidate_capture()
            self._interruptible_sleep(0.12)

            editor_frame, _origin = self._capture_screen_bgr(force=True)
            if not healing_number_editor_is_open(editor_frame):
                logger.warning("Healing numeric editor closed before row %s was confirmed", row_index)
                self.set_status_message(
                    f"Лечение не запущено: ввод количества {row_index} не подтверждён",
                    force=True,
                )
                return False

            actual_quota = quota
            if self.uses_adb:
                entered_value = self.adb_client.focused_edit_text_value()
                try:
                    actual_quota = int(str(entered_value))
                except (TypeError, ValueError):
                    actual_quota = -1
                if not 0 <= actual_quota <= quota:
                    logger.error(
                        "Healing row %s input is unsafe: maximum %s, found %r",
                        row_index,
                        quota,
                        entered_value,
                    )
                    self.adb_client.keyevent(4)
                    self._invalidate_capture()
                    self.set_status_message(
                        f"Лечение не запущено: в строке {row_index} введено неверное количество",
                        force=True,
                    )
                    return False

            # This coordinate is safe only after the white Android editor has
            # been positively detected. It is the editor's OK button, not a
            # blind tap near the in-game healing controls.
            if self.uses_adb:
                self.adb_client.tap(ok_x, ok_y)
            else:
                pyautogui.click(ok_x, ok_y)
            self._invalidate_capture()
            self._interruptible_sleep(0.20)

            after_frame, _origin = self._capture_screen_bgr(force=True)
            if healing_number_editor_is_open(after_frame):
                logger.warning("Healing numeric editor remained open after row %s", row_index)
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
                self._invalidate_capture()
                self.set_status_message(
                    f"Лечение не запущено: окно количества {row_index} не закрылось",
                    force=True,
                )
                return False
            logger.info(
                "Healing row %s configured with %s of requested %s",
                row_index,
                actual_quota,
                quota,
            )
            return actual_quota

        selected_total = 0
        for row_index, row_y in enumerate(row_positions, start=1):
            remaining = troop_limit - selected_total
            if remaining <= 0:
                break
            result = configure_row(row_index, row_y, remaining)
            if result is None:
                break
            if result is False:
                return False
            selected_total += int(result)

        if selected_total <= 0:
            self.set_status_message(
                "Лечение не запущено: доступные строки раненых не найдены",
                force=True,
            )
            return False

        logger.info(
            "Healing selected %s troops with configured maximum %s",
            selected_total,
            troop_limit,
        )
        self.set_status_message(
            f"Лечение: выбрано {selected_total} из максимум {troop_limit}",
            force=True,
        )

        final_frame, _origin = self._capture_screen_bgr(force=True)
        if healing_auto_fill_is_checked(final_frame):
            logger.error("Healing auto-fill became enabled after troop configuration")
            self.set_status_message(
                "Лечение не запущено: авто-пополнение снова включилось",
                force=True,
            )
            return False
        return True

    def _execute_action(self, img_config, location):
        self.routine_action_failure_reason = ""
        x, y = location.x, location.y
        offset = img_config.get("click_offset", (0, 0))
        display = self.get_display_profile() if self.uses_adb else make_display_profile(1280, 720)
        target_x = x + offset[0] * display.scale_x
        target_y = y + offset[1] * display.scale_y

        action = img_config.get("action", "click")
        numbers = self._resolve_action_numbers(img_config)
        click_seq = img_config.get("click_sequence", [])

        if self._resource_result_level_rejected(img_config):
            return False

        if action == "open_processing_factory":
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message("Открываю завод по обработке", force=True)

            confirmation_uid = str(img_config.get("confirmation_uid") or "")
            confirmation_image = next(
                (
                    image
                    for image in self.search_images
                    if str(image.get("uid") or "") == confirmation_uid
                ),
                None,
            )
            deadline = time.monotonic() + 4.0
            while (
                confirmation_image is not None
                and time.monotonic() < deadline
                and not self.stop_event.is_set()
            ):
                self._interruptible_sleep(0.35)
                guard_location, guard_bbox, _score = self._locate_image(
                    confirmation_image
                )
                if guard_location is None or guard_bbox is None:
                    continue
                is_valid, _reason = self._validate_detected_match(
                    confirmation_image,
                    guard_bbox,
                )
                if is_valid:
                    logger.info(
                        "Processing factory opening confirmed at (%s, %s)",
                        target_x,
                        target_y,
                    )
                    return True

            logger.warning(
                "Processing factory opening rejected: factory header did not appear"
            )
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Could not close the unexpected refinery screen")
            self._invalidate_capture()
            self.routine_completed_steps.discard("select_refinery")
            self.set_status_message(
                "Завод не открылся: возвращаюсь и повторяю поиск",
                force=True,
            )
            self._interruptible_sleep(0.8)
            return False

        if action == "open_processing_contest":
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message("Открываю конкурс по обработке", force=True)

            confirmation_uid = str(img_config.get("confirmation_uid") or "")
            confirmation_image = next(
                (
                    image
                    for image in self.search_images
                    if str(image.get("uid") or "") == confirmation_uid
                ),
                None,
            )
            deadline = time.monotonic() + 5.0
            while (
                confirmation_image is not None
                and time.monotonic() < deadline
                and not self.stop_event.is_set()
            ):
                self._interruptible_sleep(0.4)
                guard_location, guard_bbox, _score = self._locate_image(
                    confirmation_image
                )
                if guard_location is None or guard_bbox is None:
                    continue
                is_valid, _reason = self._validate_detected_match(
                    confirmation_image,
                    guard_bbox,
                )
                if is_valid:
                    logger.info("Processing contest opening confirmed")
                    return True

            logger.warning(
                "Processing contest entry was tapped, but its screen did not open"
            )
            self.set_status_message(
                "Конкурс по обработке не открылся: не засчитываю задачу",
                force=True,
            )
            return False

        if action == "collect_processing_factory_reward":
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message(
                "Собираю завершённую обработку",
                force=True,
            )
            self._interruptible_sleep(img_config.get("delay", 0.8))

            confirmation_uid = str(img_config.get("confirmation_uid") or "")
            confirmation_image = next(
                (
                    image
                    for image in self.search_images
                    if str(image.get("uid") or "") == confirmation_uid
                ),
                None,
            )

            def factory_screen_visible():
                if confirmation_image is None:
                    return False
                guard_location, guard_bbox, _score = self._locate_image(
                    confirmation_image
                )
                if guard_location is None or guard_bbox is None:
                    return False
                is_valid, _reason = self._validate_detected_match(
                    confirmation_image,
                    guard_bbox,
                )
                return bool(is_valid)

            if factory_screen_visible():
                return True

            # Collecting a finished line opens a full-screen result card on
            # some accounts. Close exactly one layer, then require the factory
            # header before the runtime step is accepted.
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Could not close the processing reward result")
                return False
            self._invalidate_capture()
            self._interruptible_sleep(1.0)
            if factory_screen_visible():
                logger.info("Processing reward result closed; factory screen restored")
                return True

            logger.warning(
                "Processing reward was collected, but the factory screen was not restored"
            )
            self.set_status_message(
                "Награда собрана, но экран завода не восстановлен",
                force=True,
            )
            return False

        if action == "alliance_marked_project":
            frame, _origin = self._capture_screen_bgr(force=True)
            target = detect_alliance_marked_project_target(frame)
            if target is None:
                logger.info("Alliance donation marker was not found; using project templates")
                self.set_status_message(
                    "Пожертвования: отметка проекта не найдена, проверяю резервные варианты",
                    force=True,
                )
                return False
            target_x, target_y = target
            if self.uses_adb:
                self.adb_client.tap(target_x, target_y)
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            logger.info(
                "Alliance marked project selected at (%s, %s)",
                target_x,
                target_y,
            )
            self.set_status_message(
                "Пожертвования: выбран отмеченный проект",
                force=True,
            )
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return True

        if action == "radar_defer_in_progress":
            self.routine_radar_in_progress_seen = True
            self._confirm_pending_radar_marker()
            try:
                if self.uses_adb:
                    self.adb_client.keyevent(4)
                else:
                    pyautogui.press("escape")
            except Exception:
                logger.exception("Не удалось закрыть выполняющееся задание радара")
                return False
            self._invalidate_capture()
            self.routine_last_action_time = time.time()
            self.routine_idle_outside_since = 0.0
            self.routine_idle_recovery_attempted = False
            img_config["last_used"] = self.routine_last_action_time
            if getattr(self, "current_routine_task_id", None) == "radar_marches":
                self.set_status_message(
                    "Радар: этот отряд уже выполняет задание, проверяю следующую карточку",
                    force=True,
                )
                self._interruptible_sleep(img_config.get("delay", 0.5))
                reset_radar_card_runtime_steps(self.routine_completed_steps)
                self.routine_last_action_time = time.time()
                return True
            self.routine_completed_steps.clear()
            self.set_status_message(
                "Радар: задание уже выполняется, проверяю следующую карточку",
                force=True,
            )
            self._interruptible_sleep(img_config.get("delay", 0.5))
            return True

        if action == "radar_return_shelter":
            if not (
                {"radar_action", "radar_march"}
                & self.routine_completed_steps
            ):
                logger.info(
                    "Radar return ignored until the task action is confirmed; steps=%s",
                    sorted(self.routine_completed_steps),
                )
                return False
            dispatched_radar_march = bool(
                getattr(self, "current_routine_task_id", None) == "radar_marches"
                and "radar_march" in self.routine_completed_steps
            )
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            self._confirm_pending_radar_marker()
            self.routine_last_action_time = time.time()
            # Each card is an independent flow. A recovery used by an earlier
            # card must not prevent us from escaping a later transient screen.
            self.routine_idle_outside_since = 0.0
            self.routine_idle_recovery_attempted = False
            img_config["last_used"] = self.routine_last_action_time
            if dispatched_radar_march:
                self.routine_radar_dispatched_this_pass = True
                for active_task in getattr(self, "routine_tasks", ()):
                    if str(active_task.get("id") or "") == "radar_marches":
                        active_task.setdefault("settings", {}).pop(
                            "_no_squad_confirmations",
                            None,
                        )
                        break
                action_counts = getattr(self, "routine_action_counts", None)
                if not isinstance(action_counts, dict):
                    action_counts = {}
                    self.routine_action_counts = action_counts
                dispatches = int(action_counts.get("radar_dispatches", 0) or 0) + 1
                action_counts["radar_dispatches"] = dispatches
                self.set_status_message(
                    f"Радар: отправлено отрядов {dispatches}; проверяю следующий свободный поход",
                    force=True,
                )
                self._interruptible_sleep(img_config.get("delay", 0.8))
                reset_radar_card_runtime_steps(self.routine_completed_steps)
                self.routine_last_action_time = time.time()
                self.routine_idle_confirmation_count = 0
                self.save_config()
                return True
            reset_radar_card_runtime_steps(self.routine_completed_steps)
            self.set_status_message(
                "Радар: задание обработано, возвращаюсь к следующей карточке",
                force=True,
            )
            self._interruptible_sleep(img_config.get("delay", 0.8))
            return True

        if action == "select_training_queue":
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            self._interruptible_sleep(0.8)
            queue_number = self.routine_action_counts.get("max_queue_checks", 0) + 1
            queue_ordinal = int(img_config.get("training_queue_ordinal", 0) or 0)
            radial_target = img_config.get("training_radial_target", ())
            if queue_ordinal and queue_number == queue_ordinal and len(radial_target) == 2:
                selected_frame, _selected_origin = self._capture_screen_bgr(force=True)
                radial_x = int(round(float(radial_target[0]) * display.scale_x))
                radial_y = int(round(float(radial_target[1]) * display.scale_y))
                self.routine_completed_steps.add("building")
                self.set_status_message(
                    f"Выбрано учебное здание {queue_ordinal}/4",
                    force=True,
                )
                screen_change = 0.0
                training_frame = selected_frame
                # Live accounts occasionally ignore the first radial action
                # tap while the building animation is still settling.  Retry
                # the *same* verified action (never neighbouring radial icons)
                # a few times before declaring this troop queue unavailable.
                for radial_attempt in range(1, 5):
                    if self.uses_adb:
                        self.adb_client.tap(radial_x, radial_y)
                    else:
                        pyautogui.click(radial_x, radial_y)
                    self._invalidate_capture()
                    self._interruptible_sleep(1.5)
                    training_frame, _training_origin = self._capture_screen_bgr(force=True)
                    if training_frame.shape != selected_frame.shape:
                        selected_frame = cv2.resize(
                            selected_frame,
                            (training_frame.shape[1], training_frame.shape[0]),
                            interpolation=cv2.INTER_LINEAR,
                        )
                    screen_change = float(
                        cv2.absdiff(selected_frame, training_frame).mean()
                    )
                    if screen_change >= 3.0:
                        break
                    logger.info(
                        "Training radial tap did not change the screen "
                        "(attempt %s/4, %.2f); retrying",
                        radial_attempt,
                        screen_change,
                    )
                if screen_change < 3.0:
                    self._save_routine_calibration_frame(
                        str(getattr(self, "current_routine_task_id", "training")),
                        f"radial_unopened_queue_{queue_ordinal}",
                        training_frame,
                    )
                if screen_change >= 3.0:
                    logger.info(
                        "Training screen opened for queue %s/4, screen change %.2f",
                        queue_ordinal,
                        screen_change,
                    )
                    synthetic = dict(img_config)
                    synthetic.update(
                        {
                            "action": "train_highest",
                            "click_offset": (423, 564),
                            "delay": 1.5,
                        }
                    )
                    synthetic_location = pyautogui.Point(
                        int(round(640 * display.scale_x)),
                        int(round(62 * display.scale_y)),
                    )
                    training_started = self._execute_action(
                        synthetic,
                        synthetic_location,
                    )
                    if training_started is True:
                        self.routine_completed_steps.add("train")
                        self.routine_action_completes_task = True
                    else:
                        logger.warning(
                            "Training queue %s/4 opened, but the start action was not confirmed",
                            queue_ordinal,
                        )
            img_config["last_used"] = time.time()
            self.set_status_message("Выбрано следующее учебное здание", force=True)
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action == "select_research_queue":
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            self._interruptible_sleep(1.5)
            selected_frame, _selected_origin = self._capture_screen_bgr(force=True)

            if research_progress_bar_is_active(selected_frame):
                img_config["last_used"] = time.time()
                self.routine_completed_steps.add("confirm")
                self.routine_action_completes_task = True
                self.set_status_message(
                    "Исследование уже запущено: активный таймер подтверждён",
                    force=True,
                )
                logger.info(
                    "Active research progress bar confirmed after centring the "
                    "laboratory; ordered queue can continue"
                )
                return

            # The queue shortcut only centres the research laboratory. Open
            # the centred building first and confirm that its radial menu is
            # visible before selecting Personal Research.
            radial_frame = None
            building_candidates = ((620, 320), (640, 300), (600, 340))
            for building_ref_x, building_ref_y in building_candidates:
                building_x = int(round(building_ref_x * display.scale_x))
                building_y = int(round(building_ref_y * display.scale_y))
                if self.uses_adb:
                    self.adb_client.tap(building_x, building_y)
                else:
                    pyautogui.click(building_x, building_y)
                self._invalidate_capture()
                self._interruptible_sleep(0.9)
                candidate_frame, _candidate_origin = self._capture_screen_bgr(
                    force=True
                )
                if research_progress_bar_is_active(candidate_frame):
                    img_config["last_used"] = time.time()
                    self.routine_completed_steps.add("confirm")
                    self.routine_action_completes_task = True
                    self.set_status_message(
                        "Исследование уже запущено: активный таймер подтверждён",
                        force=True,
                    )
                    logger.info(
                        "Active research progress bar confirmed after opening "
                        "the centred laboratory"
                    )
                    return
                if research_radial_menu_is_visible(selected_frame, candidate_frame):
                    radial_frame = candidate_frame
                    logger.info(
                        "Research laboratory radial menu confirmed at (%s, %s) "
                        "by its local control region",
                        building_x,
                        building_y,
                    )
                    break
                logger.info(
                    "Centred research laboratory tap at (%s, %s) did not open "
                    "the radial menu",
                    building_x,
                    building_y,
                )

            if radial_frame is None:
                logger.warning(
                    "Research laboratory radial menu was not confirmed; "
                    "keeping the ordered queue on research"
                )
                self.set_status_message(
                    "Не удалось открыть меню лаборатории; повторяю исследование",
                    force=True,
                )
                return False

            # The radial action is the round microscope control to the lower
            # right of the centred laboratory.  Its label extends down-left,
            # which made the old (755, 475) point miss the actual control.
            research_opened = False
            # A free laboratory exposes three radial actions and places
            # Personal Research lower than an already-busy laboratory, which
            # only exposes two. The live free-lab control is centred near
            # (755, 475); the older (790, 420) point closes that menu without
            # opening research.
            research_targets = ((755, 475), (770, 460), (790, 420))
            for target_index, (research_ref_x, research_ref_y) in enumerate(
                research_targets
            ):
                research_x = int(round(research_ref_x * display.scale_x))
                research_y = int(round(research_ref_y * display.scale_y))
                if self.uses_adb:
                    self.adb_client.tap(research_x, research_y)
                else:
                    pyautogui.click(research_x, research_y)
                self._invalidate_capture()
                self._interruptible_sleep(1.4)
                research_frame, _research_origin = self._capture_screen_bgr(
                    force=True
                )
                if (
                    research_progress_bar_is_active(research_frame)
                    or research_tree_progress_is_active(research_frame)
                ):
                    img_config["last_used"] = time.time()
                    self.routine_completed_steps.add("confirm")
                    self.routine_action_completes_task = True
                    logger.info(
                        "Research radial action exposed an active progress timer"
                    )
                    return
                if (
                    research_tree_is_visible(research_frame)
                    or detect_research_action_target(research_frame) is not None
                ):
                    research_opened = True
                    logger.info(
                        "Research screen confirmed after radial tap at (%s, %s)",
                        research_x,
                        research_y,
                    )
                    break
                logger.info(
                    "Research radial target at (%s, %s) was not confirmed",
                    research_x,
                    research_y,
                )
                if target_index + 1 < len(research_targets):
                    # A miss outside a radial action closes the menu. Reopen
                    # and reconfirm it before trying a fallback point.
                    reopened = False
                    for building_ref_x, building_ref_y in building_candidates:
                        building_x = int(round(building_ref_x * display.scale_x))
                        building_y = int(round(building_ref_y * display.scale_y))
                        if self.uses_adb:
                            self.adb_client.tap(building_x, building_y)
                        else:
                            pyautogui.click(building_x, building_y)
                        self._invalidate_capture()
                        self._interruptible_sleep(0.9)
                        reopened_frame, _reopened_origin = (
                            self._capture_screen_bgr(force=True)
                        )
                        if research_radial_menu_is_visible(
                            research_frame,
                            reopened_frame,
                        ):
                            radial_frame = reopened_frame
                            reopened = True
                            logger.info(
                                "Research radial menu reopened before fallback "
                                "target %s",
                                target_index + 2,
                            )
                            break
                        research_frame = reopened_frame
                    if not reopened:
                        logger.warning(
                            "Research radial menu could not be reopened after "
                            "a missed action target"
                        )
                        break
            if not research_opened:
                logger.warning(
                    "Research laboratory did not open after all radial targets; "
                    "keeping the ordered queue on research"
                )
                return False
            img_config["last_used"] = time.time()
            self.set_status_message("Открываю личные исследования", force=True)
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action == "research_confirm":
            before, _before_origin = self._capture_screen_bgr(force=True)
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            self._interruptible_sleep(1.4)
            after, _after_origin = self._capture_screen_bgr(force=True)
            if after.shape != before.shape:
                before = cv2.resize(
                    before,
                    (after.shape[1], after.shape[0]),
                    interpolation=cv2.INTER_LINEAR,
                )
            screen_change = float(cv2.absdiff(before, after).mean())
            active_after = (
                research_progress_bar_is_active(after)
                or research_tree_progress_is_active(after)
            )
            button_still_visible = detect_research_action_target(after) is not None
            if screen_change < 2.0 and button_still_visible and not active_after:
                logger.warning(
                    "Research confirmation button did not advance the screen (%.2f)",
                    screen_change,
                )
                return False
            img_config["last_used"] = time.time()
            self.set_status_message(
                "Исследование запущено: подтверждение экрана получено",
                force=True,
            )
            logger.info("Research start confirmed, screen change %.2f", screen_change)
            return True

        if action == "open_world_search":
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            self.set_status_message("\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u043a\u043d\u043e\u043f\u043a\u0438 \u043f\u043e\u0438\u0441\u043a\u0430 \u0432 \u0440\u0435\u0433\u0438\u043e\u043d\u0435", force=True)
            search_image = next(
                (
                    image for image in self.search_images
                    if image.get("uid") == img_config.get("next_template_uid")
                ),
                None,
            )
            search_location = None
            deadline = time.monotonic() + 6.0
            while search_image and time.monotonic() < deadline and not self.stop_event.is_set():
                self._interruptible_sleep(0.5)
                search_location, search_bbox, _score = self._locate_image(search_image)
                if search_location and search_bbox:
                    valid, _reason = self._validate_detected_match(search_image, search_bbox)
                    if valid:
                        break
                    search_location = None
            if search_location:
                search_x = int(round(search_location.x))
                search_y = int(round(search_location.y))
                source = "template"
            else:
                search_x = int(round(43 * display.scale_x))
                search_y = int(round(447 * display.scale_y))
                source = "fallback"
            if self.uses_adb:
                self.adb_client.tap(search_x, search_y)
            else:
                pyautogui.click(search_x, search_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            logger.info("World search opened at (%s, %s), source=%s", search_x, search_y, source)
            self.set_status_message("\u041f\u043e\u0438\u0441\u043a \u0440\u0435\u0441\u0443\u0440\u0441\u043e\u0432 \u043e\u0442\u043a\u0440\u044b\u0442", force=True)
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action == "resource_search":
            level = min(7, max(1, int(self._current_task_settings().get("resource_level", 7))))
            resource_tabs = {
                "food": 550,
                "wood": 715,
                "metal": 880,
                "oil": 1045,
            }
            resource_x = resource_tabs.get(str(self.current_routine_task_id or ""))
            if resource_x is not None:
                resource_x = int(round(resource_x * display.scale_x))
                resource_y = int(round(608 * display.scale_y))
                if self.uses_adb:
                    self.adb_client.tap(resource_x, resource_y)
                else:
                    pyautogui.click(resource_x, resource_y)
                self._interruptible_sleep(0.5)
                if self.stop_event.is_set() or self.stop_hotkey_pressed:
                    return False
            minus_x = int(round(target_x - 146 * display.scale_x))
            minus_y = int(round(target_y - 76 * display.scale_y))
            plus_x = int(round(target_x + 144 * display.scale_x))
            plus_y = minus_y
            if self.uses_adb:
                for _ in range(7):
                    self.adb_client.tap(plus_x, plus_y)
                    self._interruptible_sleep(0.35)
                    if self.stop_event.is_set() or self.stop_hotkey_pressed:
                        return False
                self._interruptible_sleep(0.4)
                for _ in range(7 - level):
                    self.adb_client.tap(minus_x, minus_y)
                    self._interruptible_sleep(0.35)
                    if self.stop_event.is_set() or self.stop_hotkey_pressed:
                        return False
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
                self._interruptible_sleep(2.0)
                if self.stop_event.is_set() or self.stop_hotkey_pressed:
                    return False
                frame = self.adb_client.screenshot_bgr()
                self.adb_client.tap(frame.shape[1] // 2, int(round(frame.shape[0] * 0.49)))
            else:
                for _ in range(7):
                    pyautogui.click(plus_x, plus_y)
                    self._interruptible_sleep(0.35)
                    if self.stop_event.is_set() or self.stop_hotkey_pressed:
                        return False
                self._interruptible_sleep(0.4)
                for _ in range(7 - level):
                    pyautogui.click(minus_x, minus_y)
                    self._interruptible_sleep(0.35)
                    if self.stop_event.is_set() or self.stop_hotkey_pressed:
                        return False
                pyautogui.click(target_x, target_y)
                self._interruptible_sleep(2.0)
                if self.stop_event.is_set() or self.stop_hotkey_pressed:
                    return False
                center_x, center_y = self._screen_normalized_point(0.5, 0.49)
                pyautogui.click(center_x, center_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message(f"Поиск ресурса уровня {level}", force=True)
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action in {"zombie_search", "hivemind_search"}:
            minus_x = int(round(target_x - 146 * display.scale_x))
            plus_x = int(round(target_x + 144 * display.scale_x))
            level_y = int(round(target_y - 76 * display.scale_y))
            click = self.adb_client.tap if self.uses_adb else pyautogui.click

            if action == "zombie_search":
                settings = self._current_task_settings()
                fallback_levels = zombie_fallback_levels(settings)
                context = routine_march_context_key(
                    self.input_backend,
                    getattr(self, "adb_serial", "desktop"),
                    getattr(self, "current_account_id", "default"),
                )
                restore_by_context = getattr(self, "zombie_level_restore", {})
                self.zombie_level_restore = restore_by_context
                pending_restore = getattr(self, "zombie_level_restore_pending", {})
                self.zombie_level_restore_pending = pending_restore
                startup_offset = min(
                    fallback_levels,
                    max(0, int(pending_restore.pop(context, 0) or 0)),
                )
                if startup_offset:
                    self.set_status_message(
                        f"Зомби: восстанавливаю уровень после остановки (+{startup_offset})",
                        force=True,
                    )
                    for _ in range(startup_offset):
                        click(plus_x, level_y)
                        self._interruptible_sleep(0.35)
                        if self.stop_event.is_set() or self.stop_hotkey_pressed:
                            return False
                    restore_by_context.pop(context, None)
                    self.save_config()
                previous_level_exists = context in restore_by_context
                current_offset = min(
                    fallback_levels,
                    max(0, int(restore_by_context.get(context, 0) or 0)),
                )

                if previous_level_exists and fallback_levels > 0:
                    if current_offset >= fallback_levels:
                        self.set_status_message(
                            f"Зомби: возвращаю стартовый уровень (+{current_offset})",
                            force=True,
                        )
                        for _ in range(current_offset):
                            click(plus_x, level_y)
                            self._interruptible_sleep(0.35)
                            if self.stop_event.is_set() or self.stop_hotkey_pressed:
                                return False
                        current_offset = 0
                    else:
                        current_offset += 1
                        click(minus_x, level_y)
                        self._interruptible_sleep(0.35)
                        if self.stop_event.is_set() or self.stop_hotkey_pressed:
                            return False
                    restore_by_context[context] = current_offset
                    self.save_config()
                elif current_offset:
                    self.set_status_message(
                        f"Зомби: возвращаю стартовый уровень (+{current_offset})",
                        force=True,
                    )
                    for _ in range(current_offset):
                        click(plus_x, level_y)
                        self._interruptible_sleep(0.35)
                        if self.stop_event.is_set() or self.stop_hotkey_pressed:
                            return False
                    current_offset = 0
                    restore_by_context.pop(context, None)
                    self.save_config()

                found_offset = None
                for level_offset in range(current_offset, fallback_levels + 1):
                    if level_offset > current_offset:
                        click(minus_x, level_y)
                        restore_by_context[context] = level_offset
                        self.save_config()
                        self._interruptible_sleep(0.4)
                        if self.stop_event.is_set() or self.stop_hotkey_pressed:
                            return False

                    level_text = "сохранённом уровне" if level_offset == 0 else f"уровне -{level_offset}"
                    self.set_status_message(f"Поиск зомби на {level_text}", force=True)
                    click(int(round(target_x)), int(round(target_y)))
                    self._interruptible_sleep(2.5)
                    if self.stop_event.is_set() or self.stop_hotkey_pressed:
                        return False
                    self._invalidate_capture()
                    search_location, _bbox, _confidence = self._locate_image(img_config)
                    if search_location is None:
                        found_offset = level_offset
                        break
                    if level_offset < fallback_levels:
                        self.set_status_message(
                            f"Зомби не найдены: понижаю уровень ({level_offset + 1}/{fallback_levels})",
                            force=True,
                        )

                if found_offset is None:
                    for _ in range(fallback_levels):
                        click(plus_x, level_y)
                        self._interruptible_sleep(0.35)
                    restore_by_context.pop(context, None)
                    self.save_config()
                    img_config["last_used"] = time.time()
                    self.set_status_message(
                        f"Зомби не найдены на стартовом и {fallback_levels} нижних уровнях",
                        force=True,
                    )
                    retry_seconds = max(
                        10,
                        min(3600, int(settings.get("not_found_retry_seconds", 60) or 60)),
                    )
                    self._defer_current_routine_unavailable(
                        "зомби подходящего уровня не найдены",
                        time.time(),
                        retry_delay=retry_seconds,
                    )
                    return False

                # Keep the chosen level in the game and rotate to the next
                # configured level for the following squad. This prevents the
                # search from selecting the same zombie for every free march.
                restore_by_context[context] = found_offset
                self.save_config()
                if self.uses_adb:
                    self.adb_client.tap(display.width // 2, int(round(display.height * 0.49)))
                else:
                    center_x, center_y = self._screen_normalized_point(0.5, 0.49)
                    pyautogui.click(center_x, center_y)
                self._invalidate_capture()
                img_config["last_used"] = time.time()
                suffix = "" if found_offset == 0 else f" (-{found_offset} от стартового)"
                self.set_status_message(f"Зомби найдены{suffix}", force=True)
                self._interruptible_sleep(img_config.get("delay", self.sleep_found))
                return True

            selected_level = 7 if int(self._current_task_settings().get("level", 6) or 6) == 7 else 6
            for _ in range(7):
                click(plus_x, level_y)
                self._interruptible_sleep(0.3)
                if self.stop_event.is_set() or self.stop_hotkey_pressed:
                    return False
            for _ in range(7 - selected_level):
                click(minus_x, level_y)
                self._interruptible_sleep(0.3)
                if self.stop_event.is_set() or self.stop_hotkey_pressed:
                    return False
            self.set_status_message(
                f"Коллективный разум: выбран уровень {selected_level}",
                force=True,
            )
            click(int(round(target_x)), int(round(target_y)))
            self._interruptible_sleep(2.0)
            self._invalidate_capture()
            no_result_uid = str(img_config.get("no_result_template_uid") or "")
            no_result = next(
                (
                    image for image in self.search_images
                    if str(image.get("uid") or "") == no_result_uid
                ),
                None,
            ) if no_result_uid else None
            if no_result is not None:
                no_result_location, _bbox, _confidence = self._locate_image(no_result)
                if no_result_location is not None:
                    img_config["last_used"] = time.time()
                    self.set_status_message(
                        "Коллективный разум выбранного уровня рядом не найден; повтор позже",
                        force=True,
                    )
                    self._interruptible_sleep(img_config.get("delay", self.sleep_found))
                    return True
            if self.uses_adb:
                self.adb_client.tap(display.width // 2, int(round(display.height * 0.49)))
            else:
                center_x, center_y = self._screen_normalized_point(0.5, 0.49)
                pyautogui.click(center_x, center_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message(
                f"Поиск коллективного разума уровня {selected_level}",
                force=True,
            )
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return True

        if action == "prize_start_or_prepare":
            if self.uses_adb:
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            self._interruptible_sleep(2.0)

            still_waiting, _bbox, _confidence = self._locate_image(img_config)
            if still_waiting is not None:
                setup_x = int(round(873 * display.scale_x))
                setup_y = int(round(340 * display.scale_y))
                if self.uses_adb:
                    self.adb_client.tap(setup_x, setup_y)
                else:
                    pyautogui.click(setup_x, setup_y)
                self._invalidate_capture()
                self.set_status_message(
                    "Охота: отряд не настроен, открываю его заполнение",
                    force=True,
                )
            else:
                self.set_status_message("Охота: подбор запущен", force=True)
            img_config["last_used"] = time.time()
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action == "prize_prepare":
            frame, _origin = self._capture_screen_bgr(force=True)
            scale_x = frame.shape[1] / 1280.0
            scale_y = frame.shape[0] / 720.0
            first_slider = (int(1010 * scale_x), int(137 * scale_y))
            fill_max = (int(744 * scale_x), int(644 * scale_y))
            if self.uses_adb:
                self.adb_client.tap(*first_slider)
                time.sleep(0.25)
                self.adb_client.tap(*fill_max)
            else:
                pyautogui.click(*first_slider)
                time.sleep(0.25)
                pyautogui.click(*fill_max)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message("Отряд охоты заполнен доступными войсками", force=True)
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action == "google_account_select":
            frame, _origin = self._capture_screen_bgr(force=True)
            scale_x = frame.shape[1] / 1280.0
            scale_y = frame.shape[0] / 720.0
            settings = self._current_task_settings()
            chooser_index = min(20, max(1, int(settings.get("chooser_index", 1))))
            candidates = []
            if self.uses_adb:
                try:
                    candidates = extract_google_accounts(self.adb_client.ui_xml())
                except AdbError as exc:
                    logger.warning("Не удалось прочитать список аккаунтов Google: %s", exc)
            self.account_switch_candidates = candidates
            if settings.get("probe_only", False):
                self.account_switch_probe_ready = True
                self.routine_action_completes_task = True
                img_config["last_used"] = time.time()
                labels = ", ".join(
                    f"№{item['chooser_index']} {mask_google_account(item['email'])}"
                    for item in candidates
                )
                message = f"Найдено аккаунтов Google: {len(candidates)}"
                if labels:
                    message = f"{message} ({labels})"
                self.set_status_message(message, force=True)
                logger.info("Google account probe: %s", message)
                return
            if candidates and chooser_index > len(candidates):
                self.account_switch_error = (
                    f"Аккаунт Google №{chooser_index} не найден; доступно: {len(candidates)}"
                )
                self.routine_action_completes_task = True
                img_config["last_used"] = time.time()
                self.set_status_message(self.account_switch_error, force=True)
                return
            target_account_id = str(settings.get("target_account_id") or "")
            expected_login = self.get_account_login(target_account_id, "google").casefold()
            candidate = next(
                (item for item in candidates if item["email"].casefold() == expected_login),
                None,
            ) if expected_login else None
            if expected_login and candidate is None:
                self.account_switch_error = "Нужный Google-аккаунт не найден в LDPlayer"
                self.routine_action_completes_task = True
                img_config["last_used"] = time.time()
                self.set_status_message(self.account_switch_error, force=True)
                return
            if candidate is not None:
                chooser_index = int(candidate["chooser_index"])
            account_x = int(640 * scale_x)
            account_y = int((353 + (chooser_index - 1) * 103) * scale_y)
            if self.uses_adb:
                self.adb_client.tap(account_x, account_y)
            else:
                pyautogui.click(account_x, account_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.account_switch_selected_at = time.time()
            self.set_status_message(f"Выбран аккаунт Google №{chooser_index}", force=True)
            self._interruptible_sleep(8.0)
            if self.uses_adb and not self.stop_event.is_set():
                try:
                    if requires_google_reauthentication(self.adb_client.ui_xml()):
                        target_account_id = str(settings.get("target_account_id") or "")
                        profile = find_account(self.account_profiles, target_account_id)
                        auto_login = bool(profile and profile.get("auto_login", False))
                        if (
                            auto_login
                            and self.account_has_saved_password(target_account_id)
                        ):
                            self.account_switch_auto_login_attempted = True
                            if self.fill_google_credential(target_account_id, "password"):
                                self.account_switch_selected_at = time.time()
                                self.set_status_message(
                                    "Пароль Google введён; проверяю главный экран",
                                    force=True,
                                )
                            else:
                                self.account_switch_error = (
                                    "Автоматический ввод пароля Google не выполнен безопасно"
                                )
                                self.routine_action_completes_task = True
                        else:
                            self.account_switch_error = (
                                "Переключение остановлено: Google требует подтверждение входа"
                            )
                            self.routine_action_completes_task = True
                except AdbError as exc:
                    logger.warning("Не удалось проверить экран входа Google: %s", exc)
            return

        if action == "open_healing_hospital":
            group = img_config.get("group")
            start_image = next(
                (
                    image
                    for image in self.search_images
                    if image.get("group") == group
                    and image.get("enabled", True)
                    and image.get("runtime_step") == "start_healing"
                ),
                None,
            )

            def tap(point):
                if self.uses_adb:
                    self.adb_client.tap(
                        int(round(point.x)),
                        int(round(point.y)),
                    )
                else:
                    pyautogui.click(point.x, point.y)
                self._invalidate_capture()
                img_config["last_used"] = time.time()

            def healing_screen_is_ready():
                try:
                    screen_frame, _origin = self._capture_screen_bgr(force=True)
                except Exception:
                    logger.exception(
                        "Healing hospital form confirmation failed"
                    )
                else:
                    if healing_troop_form_is_visible(screen_frame):
                        return True
                if start_image is None:
                    return False
                start_location, start_bbox, _score = self._locate_image(start_image)
                if start_location is None or start_bbox is None:
                    return False
                is_valid, _reason = self._validate_detected_match(
                    start_image,
                    start_bbox,
                )
                return is_valid

            self._remember_healing_camera_route()
            tap(location)
            self.set_status_message(
                "Лечение: открываю госпиталь и проверяю завершённую партию",
                force=True,
            )
            if start_image is None:
                self._interruptible_sleep(
                    max(0.8, float(img_config.get("delay", self.sleep_found)))
                )
                return True

            for _check in range(4):
                self._interruptible_sleep(0.35)
                if healing_screen_is_ready():
                    settings = self._current_task_settings()
                    self._remember_healing_hospital_target(
                        settings,
                        (location.x, location.y),
                        save=not settings.get("_collection_pending", False),
                    )
                    if settings.get("_collection_pending", False):
                        self._finish_pending_healing_collection(
                            settings,
                            "hospital entrance",
                        )
                    return True

            # The first tap can collect a completed batch without opening the
            # hospital. Re-find the stable overview row and tap it again.
            retry_location, retry_bbox, _score = self._locate_image(img_config)
            if retry_location is not None and retry_bbox is not None:
                is_valid, _reason = self._validate_detected_match(
                    img_config,
                    retry_bbox,
                )
                if is_valid:
                    tap(retry_location)
                    self.set_status_message(
                        "Вылеченные войска собраны, открываю следующую партию",
                        force=True,
                    )
                    for _check in range(4):
                        self._interruptible_sleep(0.35)
                        if healing_screen_is_ready():
                            settings = self._current_task_settings()
                            self._remember_healing_hospital_target(
                                settings,
                                (retry_location.x, retry_location.y),
                                save=False,
                            )
                            self._finish_pending_healing_collection(
                                settings,
                                "hospital overview",
                            )
                            logger.info(
                                "Finished healing was collected through the hospital overview"
                            )
                            return True

            logger.warning(
                "Healing overview did not open the hospital after collection check"
            )
            return False

        if action == "collect_healed_troops":
            current_location = location
            for attempt in range(2):
                if attempt:
                    current_location, current_bbox, _score = self._locate_image(img_config)
                    if current_location is None or current_bbox is None:
                        healing_settings = self._current_task_settings()
                        if healing_settings.get("_collection_pending", False):
                            self._finish_pending_healing_collection(
                                healing_settings,
                                "template disappearance before retry",
                            )
                        self.set_status_message("Вылеченные войска собраны", force=True)
                        logger.info("Finished healing marker disappeared after collection")
                        return True
                    is_valid, reject_reason = self._validate_detected_match(
                        img_config,
                        current_bbox,
                    )
                    if not is_valid:
                        logger.warning(
                            "Finished healing marker rejected before retry by %s",
                            reject_reason,
                        )
                        return False

                if self.uses_adb:
                    self.adb_client.tap(
                        int(round(current_location.x)),
                        int(round(current_location.y)),
                    )
                else:
                    pyautogui.click(current_location.x, current_location.y)
                self._invalidate_capture()
                img_config["last_used"] = time.time()
                self.set_status_message(
                    f"Собираю вылеченные войска, попытка {attempt + 1}/2",
                    force=True,
                )

                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline and not self.stop_event.is_set():
                    self._interruptible_sleep(0.35)
                    location_after, bbox_after, _score = self._locate_image(img_config)
                    if location_after is None or bbox_after is None:
                        healing_settings = self._current_task_settings()
                        if healing_settings.get("_collection_pending", False):
                            self._finish_pending_healing_collection(
                                healing_settings,
                                f"template tap {attempt + 1}",
                            )
                        self.set_status_message("Вылеченные войска собраны", force=True)
                        logger.info(
                            "Finished healing marker disappeared after attempt %s",
                            attempt + 1,
                        )
                        return True
                    current_location = location_after

            self.set_status_message(
                "Вылеченные войска не собраны: значок остался на экране",
                force=True,
            )
            logger.warning("Finished healing marker remained visible after two taps")
            return False

        if action == "heal_troops":
            healing_settings = self._current_task_settings()
            if healing_settings.get("_collection_pending", False):
                logger.warning(
                    "Healing start blocked while the previous batch is pending"
                )
                self.set_status_message(
                    "Лечение не запущено: предыдущая партия ещё не собрана",
                    force=True,
                )
                img_config["last_used"] = time.time()
                return False
            troop_count = max(1, int(healing_settings.get("troop_count", 2500)))
            frame, _origin = self._capture_screen_bgr(force=True)
            if not self._configure_healing_troop_count(troop_count, frame):
                img_config["last_used"] = time.time()
                return False

            # Do not re-use a template center here: the similarly worded
            # instant-heal button is directly to the left. Once the troop form
            # and bounded selection are confirmed, only the stable right-hand
            # ordinary Heal button is safe.
            self._invalidate_capture()
            final_frame, _origin = self._capture_screen_bgr(force=True)
            if not healing_troop_form_is_visible(final_frame):
                logger.warning("Healing troop form disappeared before confirmation")
                self.set_status_message(
                    "Лечение не запущено: форма госпиталя после ввода не найдена",
                    force=True,
                )
                img_config["last_used"] = time.time()
                return False
            if healing_selection_is_empty(final_frame):
                logger.warning("Healing troop selection became empty before start")
                self.set_status_message(
                    "Лечение не запущено: введённое количество не сохранилось",
                    force=True,
                )
                img_config["last_used"] = time.time()
                return False

            scale_x = final_frame.shape[1] / 1280.0
            scale_y = final_frame.shape[0] / 720.0
            heal_x = int(round(1028 * scale_x))
            heal_y = int(round(617 * scale_y))
            if self.uses_adb:
                self.adb_client.tap(heal_x, heal_y)
            else:
                pyautogui.click(heal_x, heal_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self._interruptible_sleep(max(0.8, float(img_config.get("delay", self.sleep_found))))

            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline and not self.stop_event.is_set():
                frame_after, _origin = self._capture_screen_bgr(force=True)
                location_after, bbox_after, _score = self._locate_image(img_config)
                if (
                    not healing_troop_form_is_visible(frame_after)
                    or location_after is None
                    or bbox_after is None
                ):
                    settings = self._current_task_settings()
                    settings["_collection_pending"] = True
                    settings["_pending_heal_count"] = troop_count
                    settings["_last_heal_started_at"] = time.time()
                    settings["_last_pending_camera_scan_at"] = time.time()
                    settings["_hospital_target_failures"] = 0
                    settings.pop("_last_saved_hospital_attempt_at", None)
                    self.save_config()
                    self.set_status_message(f"Лечение запущено, лимит {troop_count}", force=True)
                    logger.info("Healing started with configured limit %s", troop_count)
                    return True
                self._interruptible_sleep(0.5)
            logger.warning("Healing start button remained visible after click")
            self.set_status_message(
                "Лечение не запущено: кнопка осталась на экране",
                force=True,
            )
            return False

        if action == "train_highest":
            frame, _origin = self._capture_screen_bgr(force=True)
            height, width = frame.shape[:2]
            scale_x = width / 1280.0
            scale_y = height / 720.0
            tier_boxes = (
                (650, 125, 726, 207),
                (742, 125, 818, 207),
                (834, 125, 910, 207),
                (925, 115, 1010, 213),
                (1015, 125, 1095, 207),
                (1105, 125, 1188, 207),
            )
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            highest_index = 0
            for index, (left, top, right, bottom) in enumerate(tier_boxes):
                x1, y1 = int(left * scale_x), int(top * scale_y)
                x2, y2 = int(right * scale_x), int(bottom * scale_y)
                roi = hsv[y1:y2, x1:x2]
                if roi.size and float(roi[:, :, 1].mean()) >= 20.0:
                    highest_index = index
            left, top, right, bottom = tier_boxes[highest_index]
            tier_x = int(round(((left + right) / 2.0) * scale_x))
            tier_y = int(round(((top + bottom) / 2.0) * scale_y))
            if self.uses_adb:
                self.adb_client.tap(tier_x, tier_y)
                time.sleep(0.35)
                selected_frame, _selected_origin = self._capture_screen_bgr(force=True)
                self.adb_client.tap(int(round(target_x)), int(round(target_y)))
            else:
                pyautogui.click(tier_x, tier_y)
                time.sleep(0.35)
                selected_frame, _selected_origin = self._capture_screen_bgr(force=True)
                pyautogui.click(target_x, target_y)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message(
                f"Проверяю запуск войск уровня {highest_index + 1}",
                force=True,
            )
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            started_frame, _started_origin = self._capture_screen_bgr(force=True)
            if selected_frame.shape != started_frame.shape:
                screen_change = 100.0
                button_change = 100.0
            else:
                screen_change = float(cv2.absdiff(selected_frame, started_frame).mean())
                frame_height, frame_width = selected_frame.shape[:2]
                button_x = int(round(target_x))
                button_y = int(round(target_y))
                x1 = max(0, button_x - int(round(150 * frame_width / 1280.0)))
                x2 = min(frame_width, button_x + int(round(150 * frame_width / 1280.0)))
                y1 = max(0, button_y - int(round(55 * frame_height / 720.0)))
                y2 = min(frame_height, button_y + int(round(55 * frame_height / 720.0)))
                button_change = float(
                    cv2.absdiff(
                        selected_frame[y1:y2, x1:x2],
                        started_frame[y1:y2, x1:x2],
                    ).mean()
                )
            if screen_change < 1.0 and button_change < 3.0:
                logger.warning(
                    "Training start was not confirmed: screen change %.2f, button change %.2f",
                    screen_change,
                    button_change,
                )
                self.set_status_message(
                    "Запуск обучения не подтверждён: очередь войск не засчитана",
                    force=True,
                )
                return False
            logger.info(
                "Training start confirmed for tier %s: screen change %.2f, button change %.2f",
                highest_index + 1,
                screen_change,
                button_change,
            )
            self.set_status_message(
                f"Обучение войск уровня {highest_index + 1} запущено и подтверждено",
                force=True,
            )
            return True

        if action == "research_select":
            selected_branch = self._select_available_research()
            if selected_branch is None:
                logger.warning(
                    "Research selection did not expose a Collect/Confirm action "
                    "in the configured branches"
                )
                self.set_status_message(
                    "Доступное исследование не найдено; сохраняю очередь",
                    force=True,
                )
                return False
            self.set_status_message(
                f"Выбрано исследование: "
                f"{'война' if selected_branch == 'war' else 'экономика'}",
                force=True,
            )
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

            # Kept unreachable for one release as a rollback reference. The
            # dynamic scanner above supersedes the old single-page selector.
            branch = self._current_task_settings().get("branch", "off")
            if branch == "off":
                return
            branch_x, branch_y = (70, 300) if branch == "war" else (70, 165)
            branch_x = int(round(branch_x * display.scale_x))
            branch_y = int(round(branch_y * display.scale_y))
            swipe_left_from = (int(1000 * display.scale_x), int(500 * display.scale_y))
            swipe_left_to = (int(300 * display.scale_x), int(500 * display.scale_y))
            swipe_right_from = swipe_left_to
            swipe_right_to = swipe_left_from
            if self.uses_adb:
                self.adb_client.tap(branch_x, branch_y)
                time.sleep(0.5)
                for _ in range(6):
                    self.adb_client.swipe(*swipe_right_from, *swipe_right_to, 450)
                    time.sleep(0.15)
                for _ in range(2):
                    self.adb_client.swipe(*swipe_left_from, *swipe_left_to, 450)
                    time.sleep(0.3)
            else:
                pyautogui.click(branch_x, branch_y)
                time.sleep(0.5)
                for _ in range(6):
                    pyautogui.moveTo(*swipe_right_from)
                    pyautogui.dragTo(*swipe_right_to, duration=0.45, button="left")
                    time.sleep(0.15)
                for _ in range(2):
                    pyautogui.moveTo(*swipe_left_from)
                    pyautogui.dragTo(*swipe_left_to, duration=0.45, button="left")
                    time.sleep(0.3)

            frame, _origin = self._capture_screen_bgr(force=True)
            if frame.shape[1] != 1280 or frame.shape[0] != 720:
                frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)
            def find_research_candidates(candidate_frame):
                gray = cv2.cvtColor(candidate_frame, cv2.COLOR_BGR2GRAY)
                hsv = cv2.cvtColor(candidate_frame, cv2.COLOR_BGR2HSV)
                circles = cv2.HoughCircles(
                    gray,
                    cv2.HOUGH_GRADIENT,
                    dp=1.2,
                    minDist=70,
                    param1=100,
                    param2=40,
                    minRadius=32,
                    maxRadius=55,
                )
                points = []
                if circles is None:
                    return points
                for x_value, y_value, radius in np.round(circles[0]).astype(int):
                    if not (115 <= x_value <= 1168 and 90 <= y_value <= 650):
                        continue
                    yy, xx = np.ogrid[:candidate_frame.shape[0], :candidate_frame.shape[1]]
                    mask = (
                        (xx - x_value) ** 2 + (yy - y_value) ** 2
                        <= int(radius * 0.75) ** 2
                    )
                    saturation = (
                        float(hsv[:, :, 1][mask].mean()) if np.any(mask) else 0.0
                    )
                    if saturation >= 55.0:
                        points.append((int(x_value), int(y_value)))
                return points

            def select_research_frontier(points):
                centered = [point for point in points if 350 <= point[0] <= 1000] or points
                frontier_x = max(point[0] for point in centered)
                frontier_points = [point for point in centered if point[0] >= frontier_x - 35]
                selected = min(frontier_points, key=lambda point: abs(point[1] - 360))
                return selected, frontier_points

            candidates = find_research_candidates(frame)
            if candidates:
                # The rightmost colored nodes are the current unlocked frontier.
                (research_x, research_y), frontier = select_research_frontier(candidates)
                selected_reference_y = int(research_y)
                logger.info(
                    "Research candidates=%s, frontier=%s, selected=(%s, %s)",
                    candidates,
                    frontier,
                    research_x,
                    research_y,
                )
                research_x = int(round(research_x * display.scale_x))
                research_y = int(round(research_y * display.scale_y))
                if self.uses_adb:
                    self.adb_client.tap(research_x, research_y)
                else:
                    pyautogui.click(research_x, research_y)
                self._invalidate_capture()
                self._interruptible_sleep(0.8)
                changed_frame, _changed_origin = self._capture_screen_bgr(force=True)
                if changed_frame.shape[1] != 1280 or changed_frame.shape[0] != 720:
                    changed_frame = cv2.resize(
                        changed_frame,
                        (1280, 720),
                        interpolation=cv2.INTER_LINEAR,
                    )
                change_score = float(
                    cv2.absdiff(frame, changed_frame).mean()
                )
                if change_score < 3.0:
                    logger.info(
                        "Research node tap did not change the screen (%.2f); retrying at (%s, %s)",
                        change_score,
                        research_x,
                        research_y,
                    )
                    if self.uses_adb:
                        self.adb_client.tap(research_x, research_y)
                    else:
                        pyautogui.click(research_x, research_y)
                    self._interruptible_sleep(0.8)
                else:
                    logger.info(
                        "Research node opened at (%s, %s), screen change %.2f",
                        research_x,
                        research_y,
                        change_score,
                    )
                    followup_candidates = find_research_candidates(changed_frame)
                    centered_followup = [
                        point
                        for point in followup_candidates
                        if 350 <= point[0] <= 1000
                    ]
                    if len(centered_followup) >= 2:
                        (followup_x, followup_y), followup_frontier = (
                            select_research_frontier(followup_candidates)
                        )
                        logger.info(
                            "Research tree recentered; candidates=%s, frontier=%s, selecting=(%s, %s)",
                            followup_candidates,
                            followup_frontier,
                            followup_x,
                            followup_y,
                        )
                        followup_x = int(round(followup_x * display.scale_x))
                        followup_y = int(round(followup_y * display.scale_y))
                        if self.uses_adb:
                            self.adb_client.tap(followup_x, followup_y)
                        else:
                            pyautogui.click(followup_x, followup_y)
                        self._interruptible_sleep(0.8)
                verification_frame, _verification_origin = self._capture_screen_bgr(
                    force=True
                )
                research_action_visible = (
                    detect_research_action_target(verification_frame) is not None
                )
                attempted_rows = [selected_reference_y]
                alternate_frame = verification_frame
                for alternate_attempt in range(4):
                    if research_action_visible:
                        break
                    if (
                        alternate_frame.shape[1] != 1280
                        or alternate_frame.shape[0] != 720
                    ):
                        alternate_reference = cv2.resize(
                            alternate_frame,
                            (1280, 720),
                            interpolation=cv2.INTER_LINEAR,
                        )
                    else:
                        alternate_reference = alternate_frame
                    alternate_candidates = find_research_candidates(alternate_reference)
                    remaining = [
                        point
                        for point in alternate_candidates
                        if all(abs(point[1] - row_y) >= 45 for row_y in attempted_rows)
                    ]
                    if not remaining:
                        break
                    (alternate_x, alternate_y), alternate_frontier = (
                        select_research_frontier(remaining)
                    )
                    attempted_rows.append(int(alternate_y))
                    logger.info(
                        "Research alternate attempt %s: candidates=%s, frontier=%s, selected=(%s, %s)",
                        alternate_attempt + 1,
                        remaining,
                        alternate_frontier,
                        alternate_x,
                        alternate_y,
                    )
                    tap_x = int(round(alternate_x * display.scale_x))
                    tap_y = int(round(alternate_y * display.scale_y))
                    if self.uses_adb:
                        self.adb_client.tap(tap_x, tap_y)
                    else:
                        pyautogui.click(tap_x, tap_y)
                    self._invalidate_capture()
                    self._interruptible_sleep(1.0)
                    alternate_frame, _alternate_origin = self._capture_screen_bgr(
                        force=True
                    )
                    research_action_visible = (
                        detect_research_action_target(alternate_frame) is not None
                    )
                if not research_action_visible:
                    # A configured branch can be fully researched even though
                    # another branch still has an available project.  The user
                    # explicitly allows any available research, so probe the
                    # other branch before keeping the ordered queue blocked.
                    alternate_branch = "economy" if branch == "war" else "war"
                    alternate_branch_y = 165 if alternate_branch == "economy" else 300
                    alternate_branch_x = int(round(70 * display.scale_x))
                    alternate_branch_y = int(
                        round(alternate_branch_y * display.scale_y)
                    )
                    logger.info(
                        "Research branch %s exposed no action; probing %s",
                        branch,
                        alternate_branch,
                    )
                    if self.uses_adb:
                        self.adb_client.tap(alternate_branch_x, alternate_branch_y)
                    else:
                        pyautogui.click(alternate_branch_x, alternate_branch_y)
                    self._invalidate_capture()
                    self._interruptible_sleep(0.6)
                    if self.uses_adb:
                        for _ in range(6):
                            self.adb_client.swipe(
                                *swipe_right_from, *swipe_right_to, 450
                            )
                            time.sleep(0.15)
                        for _ in range(2):
                            self.adb_client.swipe(
                                *swipe_left_from, *swipe_left_to, 450
                            )
                            time.sleep(0.3)
                    else:
                        for _ in range(6):
                            pyautogui.moveTo(*swipe_right_from)
                            pyautogui.dragTo(
                                *swipe_right_to, duration=0.45, button="left"
                            )
                            time.sleep(0.15)
                        for _ in range(2):
                            pyautogui.moveTo(*swipe_left_from)
                            pyautogui.dragTo(
                                *swipe_left_to, duration=0.45, button="left"
                            )
                            time.sleep(0.3)

                    branch_frame, _branch_origin = self._capture_screen_bgr(
                        force=True
                    )
                    if (
                        branch_frame.shape[1] != 1280
                        or branch_frame.shape[0] != 720
                    ):
                        branch_reference = cv2.resize(
                            branch_frame,
                            (1280, 720),
                            interpolation=cv2.INTER_LINEAR,
                        )
                    else:
                        branch_reference = branch_frame
                    branch_candidates = find_research_candidates(branch_reference)
                    branch_attempted_rows = []
                    for branch_attempt in range(5):
                        remaining = [
                            point
                            for point in branch_candidates
                            if all(
                                abs(point[1] - row_y) >= 45
                                for row_y in branch_attempted_rows
                            )
                        ]
                        if not remaining:
                            break
                        (branch_node_x, branch_node_y), branch_frontier = (
                            select_research_frontier(remaining)
                        )
                        branch_attempted_rows.append(int(branch_node_y))
                        logger.info(
                            "Research %s branch attempt %s: candidates=%s, frontier=%s, selected=(%s, %s)",
                            alternate_branch,
                            branch_attempt + 1,
                            remaining,
                            branch_frontier,
                            branch_node_x,
                            branch_node_y,
                        )
                        tap_x = int(round(branch_node_x * display.scale_x))
                        tap_y = int(round(branch_node_y * display.scale_y))
                        if self.uses_adb:
                            self.adb_client.tap(tap_x, tap_y)
                        else:
                            pyautogui.click(tap_x, tap_y)
                        self._invalidate_capture()
                        self._interruptible_sleep(1.0)
                        branch_frame, _branch_origin = self._capture_screen_bgr(
                            force=True
                        )
                        research_action_visible = (
                            detect_research_action_target(branch_frame) is not None
                        )
                        if research_action_visible:
                            branch = alternate_branch
                            logger.info(
                                "Research action found in fallback branch %s",
                                alternate_branch,
                            )
                            break
                        if branch_attempt == 0:
                            if (
                                branch_frame.shape[1] != 1280
                                or branch_frame.shape[0] != 720
                            ):
                                recentered_reference = cv2.resize(
                                    branch_frame,
                                    (1280, 720),
                                    interpolation=cv2.INTER_LINEAR,
                                )
                            else:
                                recentered_reference = branch_frame
                            recentered_candidates = find_research_candidates(
                                recentered_reference
                            )
                            same_row_candidates = [
                                point
                                for point in recentered_candidates
                                if abs(point[1] - branch_node_y) < 45
                            ]
                            if same_row_candidates:
                                recentered_x, recentered_y = max(
                                    same_row_candidates,
                                    key=lambda point: point[0],
                                )
                                logger.info(
                                    "Research %s branch recentered; confirming row at (%s, %s)",
                                    alternate_branch,
                                    recentered_x,
                                    recentered_y,
                                )
                                tap_x = int(
                                    round(recentered_x * display.scale_x)
                                )
                                tap_y = int(
                                    round(recentered_y * display.scale_y)
                                )
                                if self.uses_adb:
                                    self.adb_client.tap(tap_x, tap_y)
                                else:
                                    pyautogui.click(tap_x, tap_y)
                                self._invalidate_capture()
                                self._interruptible_sleep(1.0)
                                branch_frame, _branch_origin = (
                                    self._capture_screen_bgr(force=True)
                                )
                                research_action_visible = (
                                    detect_research_action_target(branch_frame)
                                    is not None
                                )
                                if research_action_visible:
                                    branch = alternate_branch
                                    logger.info(
                                        "Research action found in fallback branch %s after recentering",
                                        alternate_branch,
                                    )
                                    break
                        if (
                            branch_frame.shape[1] != 1280
                            or branch_frame.shape[0] != 720
                        ):
                            branch_reference = cv2.resize(
                                branch_frame,
                                (1280, 720),
                                interpolation=cv2.INTER_LINEAR,
                            )
                        else:
                            branch_reference = branch_frame
                        branch_candidates = find_research_candidates(
                            branch_reference
                        )

                if not research_action_visible:
                    logger.warning(
                        "Research selection did not expose a Collect/Confirm action in either branch"
                    )
                    return False
                self.set_status_message(
                    f"Выбрано исследование: {'война' if branch == 'war' else 'экономика'}",
                    force=True,
                )
            else:
                self.set_status_message("Доступное исследование не найдено", force=True)
                return False
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action == "swipe":
            swipe_from = img_config.get("swipe_from", (900, 600))
            swipe_to = img_config.get("swipe_to", (900, 330))
            duration_ms = max(100, int(img_config.get("swipe_duration_ms", 500)))
            repeat_count = max(1, min(10, int(img_config.get("swipe_repeat_count", 1))))
            repeat_pause = max(0.0, min(1.0, float(img_config.get("swipe_repeat_pause", 0.2))))
            from_x = int(round(float(swipe_from[0]) * display.scale_x))
            from_y = int(round(float(swipe_from[1]) * display.scale_y))
            to_x = int(round(float(swipe_to[0]) * display.scale_x))
            to_y = int(round(float(swipe_to[1]) * display.scale_y))
            for repeat_index in range(repeat_count):
                if self.stop_event.is_set() or self.stop_hotkey_pressed:
                    break
                if self.uses_adb:
                    self.adb_client.swipe(from_x, from_y, to_x, to_y, duration_ms)
                else:
                    pyautogui.moveTo(from_x, from_y)
                    pyautogui.dragTo(to_x, to_y, duration=duration_ms / 1000.0, button="left")
                if repeat_index + 1 < repeat_count and repeat_pause:
                    self._interruptible_sleep(repeat_pause)
            self._invalidate_capture()
            img_config["last_used"] = time.time()
            self.set_status_message(img_config.get("description", "Прокрутка списка"), force=True)
            self._interruptible_sleep(img_config.get("delay", self.sleep_found))
            return

        if action == "zombie_attack":
            frame, _origin = self._capture_screen_bgr(force=True)
            if zombie_camp_checkbox_is_checked(frame):
                camp_x = int(round(820 * frame.shape[1] / 1280.0))
                camp_y = int(round(518 * frame.shape[0] / 720.0))
                self.set_status_message(
                    "Охота на зомби: отключаю разбивку лагеря после атаки",
                    force=True,
                )
                if self.uses_adb:
                    self.adb_client.tap(camp_x, camp_y)
                else:
                    pyautogui.click(camp_x, camp_y)
                self._invalidate_capture()
                self._interruptible_sleep(0.35)
            action = "click"

        if self.uses_adb:
            current_x = int(round(target_x))
            current_y = int(round(target_y))
            if click_seq:
                self.adb_client.tap(current_x, current_y)
                time.sleep(0.2)
                for dx, dy in click_seq:
                    current_x += int(round(dx * display.scale_x))
                    current_y += int(round(dy * display.scale_y))
                    self.adb_client.tap(current_x, current_y)
                    time.sleep(0.2)
            elif numbers and action == "click":
                self.adb_client.tap(current_x, current_y)
                self._interruptible_sleep(0.5)
                for num_str in numbers:
                    self.adb_client.input_text(num_str)
                    self._interruptible_sleep(0.3)
                self._interruptible_sleep(1.0)
            elif action == "click":
                self.adb_client.tap(current_x, current_y)
            elif action == "double_click":
                self.adb_client.double_tap(current_x, current_y)
            elif action == "right_click":
                self.adb_client.long_press(current_x, current_y)
        else:
            pyautogui.moveTo(target_x, target_y, duration=0.1)
            time.sleep(0.05)
            if click_seq:
                pyautogui.click()
                time.sleep(0.2)
                for dx, dy in click_seq:
                    pyautogui.moveRel(dx, dy, duration=0.1)
                    pyautogui.click()
                    time.sleep(0.2)
            elif numbers and action == "click":
                pyautogui.click()
                self._interruptible_sleep(0.5)
                for num_str in numbers:
                    pyautogui.write(num_str)
                    self._interruptible_sleep(0.3)
                self._interruptible_sleep(1.0)
            elif action == "click":
                pyautogui.click()
            elif action == "double_click":
                pyautogui.doubleClick()
            elif action == "right_click":
                pyautogui.rightClick()

        current_routine_task_id = getattr(self, "current_routine_task_id", None)
        if (
            is_radar_task_id(current_routine_task_id)
            and img_config.get("requires_settlement_screen")
        ):
            self.routine_idle_outside_since = 0.0
            self.routine_idle_recovery_attempted = False
        if (
            current_routine_task_id == "__account_switch__"
            and img_config.get("group") == ACCOUNT_SWITCH_TEMPLATE_GROUP
        ):
            self.routine_completed_steps.add("account_switch_navigation_started")

        self._invalidate_capture()

        if action == "observe":
            logger.info("Наблюдение подтверждено: %s в (%s, %s)", img_config["description"], x, y)
            self.set_status_message(f"Обнаружено: {img_config['description']}", force=True)
        else:
            logger.info(f"Клик по области {img_config['description']} в ({x}, {y}) - action_occurred=True")
            self.set_status_message(f"Действие: {img_config['description']} @ ({x}, {y})", force=True)
        img_config["last_used"] = time.time()

        if self.cycle_mode:
            self.last_action_time = time.time()
            logger.info(f"Таймер группы обновлён перед сном: {self.last_action_time:.2f}")

        delay = img_config.get("delay", self.sleep_found)
        if delay > 0:
            if action == "observe":
                logger.info("Пауза %.1f сек после подтверждения %s", delay, img_config["description"])
            else:
                logger.info(f"Блокирующая задержка {delay} сек после клика по {img_config['description']}")
            self._interruptible_sleep(delay)

        if img_config.get("confirm_disappears", False):
            stamina_frame, stamina_origin = self._capture_screen_bgr(force=True)
            settings = self._current_task_settings()
            configured_amount = str(settings.get("stamina_item_amount", "auto") or "auto")
            refill_attempts = 0
            max_refill_attempts = 8
            stamina_enabled = current_routine_task_id is None or current_routine_task_id in {
                "zombie_hunt",
                "wasteland_exploration",
            }
            while stamina_enabled and stamina_dialog_is_visible(stamina_frame):
                if not bool(settings.get("use_stamina_items", True)):
                    self.routine_action_failure_reason = "stamina"
                    logger.warning("Недостаточно выносливости; автоматическое пополнение отключено")
                    self.set_status_message(
                        "Недостаточно выносливости: автопополнение отключено",
                        force=True,
                    )
                    return False
                if refill_attempts >= max_refill_attempts:
                    self.routine_action_failure_reason = "stamina"
                    logger.warning(
                        "Пополнение выносливости остановлено после %s безопасных попыток",
                        max_refill_attempts,
                    )
                    self.set_status_message(
                        "Лимит автопополнения выносливости достигнут: повторю позже",
                        force=True,
                    )
                    return False

                refill_amount = None
                stamina_target = None
                if configured_amount == "auto":
                    for candidate_amount in (50, 100, 500):
                        candidate_target = detect_stamina_refill_target(
                            stamina_frame,
                            candidate_amount,
                        )
                        if candidate_target is not None:
                            refill_amount = candidate_amount
                            stamina_target = candidate_target
                            break
                else:
                    refill_amount = int(configured_amount)
                    stamina_target = detect_stamina_refill_target(
                        stamina_frame,
                        refill_amount,
                    )

                if (configured_amount == "auto" and stamina_target is None) or refill_amount == 1000:
                    refill_amount = 1000
                    frame_height, frame_width = stamina_frame.shape[:2]
                    swipe_x = int(round(650 * frame_width / 1280.0))
                    swipe_from_y = int(round(600 * frame_height / 720.0))
                    swipe_to_y = int(round(535 * frame_height / 720.0))
                    logger.info("Прокручиваю список к предмету выносливости +1000")
                    if self.uses_adb:
                        self.adb_client.swipe(swipe_x, swipe_from_y, swipe_x, swipe_to_y, 300)
                    else:
                        screen_x = stamina_origin[0] + swipe_x
                        pyautogui.moveTo(screen_x, stamina_origin[1] + swipe_from_y)
                        pyautogui.dragTo(
                            screen_x,
                            stamina_origin[1] + swipe_to_y,
                            duration=0.3,
                            button="left",
                        )
                    self._invalidate_capture()
                    self._interruptible_sleep(0.5)
                    stamina_frame, stamina_origin = self._capture_screen_bgr(force=True)
                    stamina_target = detect_lowest_stamina_refill_target(stamina_frame)

                if stamina_target is None:
                    self.routine_action_failure_reason = "stamina"
                    logger.warning("Предмет выносливости +%s не найден", refill_amount)
                    self.set_status_message(
                        f"Предмет выносливости +{refill_amount} не найден",
                        force=True,
                    )
                    return False

                refill_attempts += 1
                refill_x, refill_y = stamina_target
                logger.info(
                    "Недостаточно выносливости: использую предмет +%s в (%s, %s), попытка %s/%s",
                    refill_amount,
                    refill_x,
                    refill_y,
                    refill_attempts,
                    max_refill_attempts,
                )
                self.set_status_message(
                    f"Недостаточно выносливости: использую предмет +{refill_amount}",
                    force=True,
                )
                if self.uses_adb:
                    self.adb_client.tap(refill_x, refill_y)
                else:
                    pyautogui.click(
                        stamina_origin[0] + refill_x,
                        stamina_origin[1] + refill_y,
                    )
                self._invalidate_capture()
                self._interruptible_sleep(0.8)

                post_refill_frame, post_refill_origin = self._capture_screen_bgr(force=True)
                if stamina_dialog_is_visible(post_refill_frame):
                    frame_height, frame_width = post_refill_frame.shape[:2]
                    close_x = int(round(1057 * frame_width / 1280.0))
                    close_y = int(round(97 * frame_height / 720.0))
                    logger.info(
                        "Закрываю подтверждение пополнения выносливости в (%s, %s)",
                        close_x,
                        close_y,
                    )
                    if self.uses_adb:
                        self.adb_client.tap(close_x, close_y)
                    else:
                        pyautogui.click(
                            post_refill_origin[0] + close_x,
                            post_refill_origin[1] + close_y,
                        )
                    self._invalidate_capture()
                    self._interruptible_sleep(0.6)

                retry_location = None
                retry_deadline = time.monotonic() + 4.0
                while time.monotonic() < retry_deadline and not self.stop_event.is_set():
                    retry_location, _retry_bbox, _retry_score = self._locate_image(img_config)
                    if retry_location is not None:
                        break
                    self._interruptible_sleep(0.25)

                if retry_location is None:
                    self.routine_action_failure_reason = "stamina"
                    img_config["last_used"] = 0
                    logger.warning("Экран отряда не восстановился после пополнения выносливости")
                    self.set_status_message(
                        "Выносливость пополнена, но экран отряда не готов: повторю позже",
                        force=True,
                    )
                    return False

                self.set_status_message(
                    f"Выносливость пополнена на {refill_amount}: повторяю отправку",
                    force=True,
                )
                retry_x = retry_location.x + offset[0] * display.scale_x
                retry_y = retry_location.y + offset[1] * display.scale_y
                if self.uses_adb:
                    self.adb_client.tap(int(round(retry_x)), int(round(retry_y)))
                else:
                    pyautogui.click(retry_x, retry_y)
                self._invalidate_capture()
                self._interruptible_sleep(0.8)

                confirmation_deadline = time.monotonic() + 6.0
                stamina_required_again = False
                while time.monotonic() < confirmation_deadline and not self.stop_event.is_set():
                    self._interruptible_sleep(0.5)
                    confirmation_frame, confirmation_origin = self._capture_screen_bgr(force=True)
                    if stamina_dialog_is_visible(confirmation_frame):
                        stamina_frame = confirmation_frame
                        stamina_origin = confirmation_origin
                        stamina_required_again = True
                        logger.info(
                            "Одного предмета +%s недостаточно; продолжаю безопасное пополнение",
                            refill_amount,
                        )
                        break
                    location_after, bbox_after, _score = self._locate_image(img_config)
                    if not location_after or not bbox_after:
                        logger.info("Отправка похода подтверждена сменой экрана: %s", img_config["description"])
                        return True
                if stamina_required_again:
                    continue
                if self.stop_event.is_set():
                    return False
                self.routine_action_failure_reason = "stamina"
                logger.warning("Отправка не подтверждена после пополнения выносливости")
                self.set_status_message(
                    "Отправка после пополнения не подтверждена: повторю позже",
                    force=True,
                )
                return False

            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline and not self.stop_event.is_set():
                self._interruptible_sleep(0.5)
                location_after, bbox_after, _score = self._locate_image(img_config)
                if not location_after or not bbox_after:
                    logger.info("Отправка похода подтверждена сменой экрана: %s", img_config["description"])
                    return True
                confirmation_frame, _confirmation_origin = self._capture_screen_bgr(force=True)
                if stamina_enabled and stamina_dialog_is_visible(confirmation_frame):
                    self.routine_action_failure_reason = "stamina"
                    self.set_status_message(
                        "Недостаточно выносливости: повторю попытку позже",
                        force=True,
                    )
                    return False
            self.set_status_message(
                "Отправка похода не подтверждена: отряд остался на экране",
                force=True,
            )
            return False
        return True

    def _interruptible_sleep(self, seconds):
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self.stop_event.is_set() or self.stop_hotkey_pressed:
                logger.info("Сон прерван по stop_event")
                break
            if self.is_paused:
                logger.info("Сон прерван из-за паузы")
                break
            remaining = end_time - time.time()
            time.sleep(min(0.5, remaining))

    def start_schedule_thread(self):
        if self.schedule_thread is not None and self.schedule_thread.is_alive():
            return
        self.schedule_stop_event.clear()
        self.schedule_thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self.schedule_thread.start()
        logger.info("Поток расписания запущен")

    def stop_schedule_thread(self):
        self.schedule_stop_event.set()
        if self.schedule_thread is not None:
            self.schedule_thread.join(timeout=2)
            logger.info("Поток расписания остановлен")

    def _schedule_loop(self):
        while not self.schedule_stop_event.is_set():
            self.check_group_schedules()
            self.schedule_stop_event.wait(60)

    def check_group_schedules(self):
        changed = False
        now = time.localtime()
        current_minutes = now.tm_hour * 60 + now.tm_min

        for group, schedule in self.group_schedules.items():
            if not schedule.get('auto', False):
                continue
            schedule_type = schedule.get('type', 'time')
            on_time = schedule.get('on_time')
            off_time = schedule.get('off_time')
            duration = schedule.get('duration', 0)
            current_state = self.groups.get(group, False)

            on_min = parse_time_to_minutes(on_time)
            if schedule_type == 'time':
                off_min = parse_time_to_minutes(off_time)
                if on_min is None or off_min is None:
                    continue
                if on_min <= off_min:
                    should_be_on = on_min <= current_minutes < off_min
                else:
                    should_be_on = (current_minutes >= on_min) or (current_minutes < off_min)
            else:
                if on_min is None:
                    continue
                should_be_on = (on_min <= current_minutes < on_min + duration)

            if should_be_on != current_state:
                self.groups[group] = should_be_on
                changed = True
                logger.info(f"Группа {group} изменена по расписанию: {should_be_on}")

        if changed:
            self.save_config()
            if self.root:
                self.root.event_generate("<<GroupsChanged>>")

    def select_area(self, master=None, for_work_area=False, default_group=None, default_description=None):
        if not self.stop_event.is_set():
            self._show_notification('warning', 'unavailable_during_run')
            return
        self._last_root = master
        self._pending_area_group = default_group if not for_work_area else None
        self._pending_area_description = default_description if not for_work_area else None
        if master:
            master.withdraw()

        def on_cancel():
            self._pending_area_group = None
            self._pending_area_description = None
            if self._last_root:
                self._last_root.deiconify()

        if for_work_area:
            callback = self._save_work_area
        else:
            callback = self._save_area

        if self.uses_adb:
            try:
                self._pending_adb_capture = self._capture_adb_frame(force=True).copy()
            except AdbError as exc:
                if master:
                    master.deiconify()
                self._show_notification('error', 'error', message=str(exc))
                return
            selector = AdbScreenSelector(
                master=master,
                frame_bgr=self._pending_adb_capture,
                callback=callback,
                on_cancel=on_cancel,
                language=self.lang,
            )
        else:
            self._pending_adb_capture = None
            selector = ScreenSelector(
                master=master,
                callback=callback,
                on_cancel=on_cancel,
            )

    def _save_work_area(self, x1, y1, x2, y2):
        if x1 == x2 or y1 == y2:
            self._show_notification('error', 'area_zero')
            if self._last_root:
                self._last_root.deiconify()
            return
        self.set_custom_region(x1, y1, x2-x1, y2-y1)
        if self.root and hasattr(self.root, 'work_area_var'):
            self.root.work_area_var.set(self.tr('selected_region'))
        if self.root and hasattr(self.root, 'work_area_combo') and hasattr(self.root, 'work_area_choices'):
            for index, (code, _text) in enumerate(self.root.work_area_choices):
                if code == 'selected':
                    self.root.work_area_combo.current(index)
                    break
        if self._last_root:
            self._last_root.deiconify()

    def _save_area(self, x1, y1, x2, y2):
        if x1 == x2 or y1 == y2:
            self._pending_area_group = None
            self._pending_area_description = None
            self._show_notification('error', 'area_zero')
            if self._last_root:
                self._last_root.deiconify()
            return
        try:
            if self.uses_adb and self._pending_adb_capture is not None:
                crop_bgr = self._pending_adb_capture[y1:y2, x1:x2]
                if crop_bgr.size == 0:
                    raise ValueError(self.tr('area_zero'))
                img = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
            else:
                img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            if img.size[0] < 5 or img.size[1] < 5:
                self._pending_area_group = None
                self._pending_area_description = None
                self._show_notification('error', 'area_too_small')
                if self._last_root:
                    self._last_root.deiconify()
                return

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_path = tmp.name
            img.save(temp_path)

            dialog = tk.Toplevel(self._last_root)
            dialog.title(self.tr('save_area_title'))
            dialog.geometry("500x500")
            dialog.resizable(False, False)
            dialog.attributes("-topmost", True)
            dialog.grab_set()
            dialog.focus_set()
            dialog.lift()
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - 500) // 2
            y = (dialog.winfo_screenheight() - 500) // 2
            dialog.geometry(f"500x500+{x}+{y}")

            tk.Label(dialog, text=self.tr('enter_description'), font=("Arial", 10)).pack(pady=10)
            entry = tk.Entry(dialog, font=("Arial", 10), width=30)
            entry.pack(pady=5)
            if self._pending_area_description:
                entry.insert(0, self._pending_area_description)
                entry.selection_range(0, tk.END)
            entry.focus_set()

            tk.Label(dialog, text=self.tr('group_optional'), font=("Arial", 10)).pack(pady=5)
            group_var = tk.StringVar(value=self._pending_area_group or "")
            group_list = sorted(list(self.groups.keys()), key=str.lower)
            group_combo = ttk.Combobox(dialog, textvariable=group_var, values=group_list,
                                       state="normal", width=27)
            group_combo.pack(pady=5)

            def save():
                description = entry.get().strip()
                if not description:
                    self._show_notification('error', 'enter_description_error')
                    return
                group_name = group_var.get().strip()
                if group_name and group_name not in self.groups:
                    self.groups[group_name] = True

                safe_description = self._transliterate(description)
                safe_description = safe_description.replace(' ', '_')
                safe_description = ''.join(c for c in safe_description if c.isalnum() or c == '_')
                safe_description = safe_description.strip('_')
                if not safe_description:
                    safe_description = "area"
                if len(safe_description) > 30:
                    safe_description = safe_description[:30]
                timestamp = time.strftime("%H%M%S")
                target_folder = self._get_group_path(group_name)
                filename = target_folder / f"{safe_description}_{timestamp}.png"
                if filename.exists():
                    filename = target_folder / f"{safe_description}_{timestamp}_{uuid.uuid4().hex[:4]}.png"

                shutil.move(temp_path, filename)

                new_image = {
                    "uid": str(uuid.uuid4()),
                    "path": str(filename),
                    "action": "click",
                    "delay": self.sleep_found,
                    "confidence": 0.9,
                    "grayscale": True,
                    "description": description,
                    "enabled": True,
                    "click_offset": (0, 0),
                    "numbers": [],
                    "click_sequence": [],
                    "last_used": 0,
                    "cooldown": 1.5,
                    "group": group_name if group_name else None,
                    "use_scaling": True,
                }
                self.search_images.append(new_image)
                self.stats[str(filename)] = 0
                self.save_config()
                if self.refresh_groups_callback:
                    self.refresh_groups_callback()
                if self.root:
                    self.root.event_generate("<<GroupsChanged>>")
                self._pending_area_group = None
                self._pending_area_description = None
                dialog.destroy()
                if self._last_root:
                    self._last_root.deiconify()
                self._show_notification('success', 'area_saved', name=description)

            def cancel():
                try:
                    os.remove(temp_path)
                except:
                    pass
                self._pending_area_group = None
                self._pending_area_description = None
                dialog.destroy()
                if self._last_root:
                    self._last_root.deiconify()

            btn_frame = tk.Frame(dialog)
            btn_frame.pack(pady=15)
            tk.Button(btn_frame, text=self.tr('save'), command=save, width=12).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text=self.tr('cancel'), command=cancel, width=12).pack(side=tk.LEFT, padx=5)

            dialog.bind('<Return>', lambda e: save())
            dialog.bind('<Escape>', lambda e: cancel())
            dialog.protocol("WM_DELETE_WINDOW", cancel)

        except Exception as e:
            logger.exception("Ошибка при сохранении области")
            self._pending_area_group = None
            self._pending_area_description = None
            self._show_notification('error', 'error', message=str(e))
            if self._last_root:
                self._last_root.deiconify()


class ScreenSelector:
    def __init__(self, master, callback, on_cancel=None):
        self.callback = callback
        self.on_cancel = on_cancel
        self.window = tk.Toplevel(master)
        self.window.attributes("-fullscreen", True)
        self.window.attributes("-alpha", 0.3)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="black")
        self.canvas = tk.Canvas(self.window, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.window.bind("<Escape>", self._on_escape)
        self.canvas.focus_set()
        self.canvas.create_text(self.window.winfo_screenwidth()//2, 50,
                               text="Выделите область (ESC - отмена)" if master else "Select area (ESC - cancel)",
                               fill="white", font=("Arial", 16))

    def _on_click(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y, outline="red", width=3
        )

    def _on_drag(self, event):
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)
            width = abs(event.x - self.start_x)
            height = abs(event.y - self.start_y)
            self.canvas.delete("size")
            self.canvas.create_text(event.x + 50, event.y - 10,
                                   text=f"{width}x{height}", fill="white",
                                   font=("Arial", 12), tags="size")

    def _on_release(self, event):
        if self.start_x is None or self.start_y is None:
            return
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        self.window.destroy()
        self.callback(x1, y1, x2, y2)

    def _on_escape(self, _event=None):
        self.window.destroy()
        if self.on_cancel:
            self.on_cancel()


class AdbScreenSelector:
    """Select a template on an exact Android framebuffer without desktop scaling."""

    def __init__(self, master, frame_bgr, callback, on_cancel=None, language='ru'):
        self.callback = callback
        self.on_cancel = on_cancel
        self.frame_height, self.frame_width = frame_bgr.shape[:2]
        self.window = tk.Toplevel(master)
        self.window.title("Выбор шаблона ADB" if language == 'ru' else "ADB template selection")
        self.window.attributes("-topmost", True)
        self.window.grab_set()

        max_width = max(640, self.window.winfo_screenwidth() - 120)
        max_height = max(420, self.window.winfo_screenheight() - 190)
        self.scale = min(1.0, max_width / self.frame_width, max_height / self.frame_height)
        display_width = max(1, int(self.frame_width * self.scale))
        display_height = max(1, int(self.frame_height * self.scale))

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        if self.scale != 1.0:
            pil_image = pil_image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(pil_image)

        help_text = (
            "Протяните прямоугольник, затем нажмите Enter или «Сохранить». ESC — отмена."
            if language == 'ru'
            else "Drag a rectangle, then press Enter or Save. ESC cancels."
        )
        ttk.Label(self.window, text=help_text, padding=6).pack(fill=tk.X)
        self.canvas = tk.Canvas(
            self.window,
            width=display_width,
            height=display_height,
            cursor="cross",
            highlightthickness=0,
        )
        self.canvas.pack(padx=8, pady=4)
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')

        self.start = None
        self.selection = None
        self.rect = None
        self.size_text = None
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        buttons = ttk.Frame(self.window, padding=6)
        buttons.pack(fill=tk.X)
        ttk.Button(
            buttons,
            text="Сохранить" if language == 'ru' else "Save",
            command=self._confirm,
        ).pack(side=tk.RIGHT, padx=4)
        ttk.Button(
            buttons,
            text="Отмена" if language == 'ru' else "Cancel",
            command=self._cancel,
        ).pack(side=tk.RIGHT, padx=4)
        self.window.bind("<Return>", self._confirm)
        self.window.bind("<Escape>", self._cancel)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - self.window.winfo_width()) // 2
        y = (self.window.winfo_screenheight() - self.window.winfo_height()) // 2
        self.window.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.canvas.focus_set()

    def _clamp(self, x, y):
        return (
            min(max(0, int(x)), int(self.frame_width * self.scale) - 1),
            min(max(0, int(y)), int(self.frame_height * self.scale) - 1),
        )

    def _on_press(self, event):
        self.start = self._clamp(event.x, event.y)
        self.selection = None
        if self.rect:
            self.canvas.delete(self.rect)
        if self.size_text:
            self.canvas.delete(self.size_text)
        self.rect = self.canvas.create_rectangle(*self.start, *self.start, outline="#ff3b30", width=3)

    def _on_drag(self, event):
        if self.start is None:
            return
        current = self._clamp(event.x, event.y)
        self.canvas.coords(self.rect, *self.start, *current)
        width = int(abs(current[0] - self.start[0]) / self.scale)
        height = int(abs(current[1] - self.start[1]) / self.scale)
        if self.size_text:
            self.canvas.delete(self.size_text)
        self.size_text = self.canvas.create_text(
            current[0],
            max(12, current[1] - 12),
            text=f"{width}x{height}",
            fill="white",
            font=("Arial", 11, "bold"),
        )

    def _on_release(self, event):
        if self.start is None:
            return
        end = self._clamp(event.x, event.y)
        x1, x2 = sorted((self.start[0], end[0]))
        y1, y2 = sorted((self.start[1], end[1]))
        self.selection = (
            int(round(x1 / self.scale)),
            int(round(y1 / self.scale)),
            int(round(x2 / self.scale)),
            int(round(y2 / self.scale)),
        )

    def _confirm(self, _event=None):
        if not self.selection:
            return
        x1, y1, x2, y2 = self.selection
        if x2 - x1 < 5 or y2 - y1 < 5:
            return
        self.window.destroy()
        self.callback(x1, y1, x2, y2)

    def _cancel(self, _event=None):
        self.window.destroy()
        if self.on_cancel:
            self.on_cancel()


class SystemMonitor:
    def __init__(self, parent, root):
        self.parent = parent
        self.root = root
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.X, pady=2)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("green.Horizontal.TProgressbar", background='#00cc66', troughcolor='#e0e0e0')

        cpu_frame = ttk.Frame(self.frame)
        cpu_frame.pack(fill=tk.X, pady=1)
        ttk.Label(cpu_frame, text="CPU:", width=8).pack(side=tk.LEFT)
        self.cpu_label = ttk.Label(cpu_frame, text="0%", width=8)
        self.cpu_label.pack(side=tk.LEFT)
        self.cpu_bar = ttk.Progressbar(cpu_frame, length=150, mode='determinate', style="green.Horizontal.TProgressbar")
        self.cpu_bar.pack(side=tk.LEFT, padx=5)

        ram_frame = ttk.Frame(self.frame)
        ram_frame.pack(fill=tk.X, pady=1)
        ttk.Label(ram_frame, text="RAM:", width=8).pack(side=tk.LEFT)
        self.ram_label = ttk.Label(ram_frame, text="0 MB / 0 MB", width=20)
        self.ram_label.pack(side=tk.LEFT)
        self.ram_bar = ttk.Progressbar(ram_frame, length=150, mode='determinate', style="green.Horizontal.TProgressbar")
        self.ram_bar.pack(side=tk.LEFT, padx=5)

        self.gpu_frame = None
        self.gpu_label = None
        self.gpu_bar = None

        initial_gpu_load = get_gpu_load_percent() if HAS_GPUTIL else None
        if initial_gpu_load is not None:
            try:
                self.gpu_frame = ttk.Frame(self.frame)
                self.gpu_frame.pack(fill=tk.X, pady=1)
                ttk.Label(self.gpu_frame, text="GPU:", width=8).pack(side=tk.LEFT)
                self.gpu_label = ttk.Label(self.gpu_frame, text=f"{initial_gpu_load:.1f}%", width=8)
                self.gpu_label.pack(side=tk.LEFT)
                self.gpu_bar = ttk.Progressbar(self.gpu_frame, length=150, mode='determinate', style="green.Horizontal.TProgressbar")
                self.gpu_bar.pack(side=tk.LEFT, padx=5)
                self.gpu_bar['value'] = initial_gpu_load
            except:
                pass

        self.update()

    def update(self):
        if self.root.monitor_after_id:
            self.root.after_cancel(self.root.monitor_after_id)
        if HAS_PSUTIL:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_label.config(text=f"{cpu_percent:.1f}%")
            self.cpu_bar['value'] = cpu_percent

            ram = psutil.virtual_memory()
            used_gb = ram.used / (1024**3)
            total_gb = ram.total / (1024**3)
            self.ram_label.config(text=f"{used_gb:.1f} GB / {total_gb:.1f} GB")
            self.ram_bar['value'] = ram.percent

        if self.gpu_label:
            try:
                gpu_load = get_gpu_load_percent()
                if gpu_load is not None:
                    self.gpu_label.config(text=f"{gpu_load:.1f}%")
                    self.gpu_bar['value'] = gpu_load
            except:
                pass

        self.root.monitor_after_id = self.root.after(1000, self.update)


class AreaManager:
    """Окно управления областями (список, редактирование, удаление)."""
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.dialog = None
        self.tree = None
        self.stats_label = None
        self.drag_data = {"item": None, "x": 0, "y": 0}
        self.last_target = None
        self.sort_reverse = {}
        self.current_sort_col = None

    def tr(self, key, **kwargs):
        return self.bot.tr(key, **kwargs)

    def show(self, highlight_desc=None, highlight_uid=None):
        if not self.bot.stop_event.is_set():
            self.bot._show_notification('warning', 'stop_bot_first')
            return

        if not self.bot.search_images:
            self.bot._show_notification('info', 'no_areas')
            return

        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(self.tr('area_manager_title'))
        self.dialog.geometry("1300x700")
        self.dialog.attributes("-topmost", True)
        self.dialog.grab_set()
        self.dialog.focus_set()
        self.dialog.lift()
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 1300) // 2
        y = (self.dialog.winfo_screenheight() - 700) // 2
        self.dialog.geometry(f"1300x700+{x}+{y}")

        self.dialog.bind('<Return>', lambda e: self.edit_selected())
        self.dialog.bind('<Delete>', lambda e: self.delete_selected())
        self.dialog.bind('<space>', lambda e: self.toggle_selected())
        self.dialog.bind('<Escape>', lambda e: self.dialog.destroy())
        self.dialog.bind('<Control-Up>', lambda e: self.move_up())
        self.dialog.bind('<Control-Down>', lambda e: self.move_down())
        self.dialog.bind('<Up>', lambda e: self._move_selection(-1))
        self.dialog.bind('<Down>', lambda e: self._move_selection(1))

        main = ttk.Frame(self.dialog, padding="5")
        main.pack(fill=tk.BOTH, expand=True)

        columns = (
            self.tr('col_num'),
            self.tr('col_description'),
            self.tr('col_action'),
            self.tr('col_delay'),
            self.tr('col_confidence'),
            self.tr('col_grayscale'),
            self.tr('col_status'),
            self.tr('col_group'),
            self.tr('col_numbers'),
            self.tr('col_clicks')
        )
        self.tree = ttk.Treeview(main, columns=columns, show="headings", height=18, selectmode='browse')

        for i, col in enumerate(columns):
            self.tree.heading(f"#{(i+1)}", text=col, command=lambda c=col: self.sort_by_column(c))

        self.tree.column("#1", width=40, anchor="center")
        self.tree.column("#2", width=150)
        self.tree.column("#3", width=90, anchor="center")
        self.tree.column("#4", width=70, anchor="center")
        self.tree.column("#5", width=70, anchor="center")
        self.tree.column("#6", width=70, anchor="center")
        self.tree.column("#7", width=70, anchor="center")
        self.tree.column("#8", width=100, anchor="center")
        self.tree.column("#9", width=150, anchor="center")
        self.tree.column("#10", width=70, anchor="center")

        scrollbar = ttk.Scrollbar(main, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<ButtonPress-1>", self.on_drag_start)
        self.tree.bind("<B1-Motion>", self.on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self.on_drag_drop)

        self.refresh_list()

        if highlight_uid:
            self.select_by_uid(highlight_uid)
        elif highlight_desc:
            self.select_by_description(highlight_desc)

        btn_panel = ttk.Frame(self.dialog)
        btn_panel.pack(fill=tk.X, padx=5, pady=5)

        center_frame = ttk.Frame(btn_panel)
        center_frame.pack(anchor='center')

        tk.Button(center_frame, text=self.tr('edit'), command=self.edit_selected).pack(side=tk.LEFT, padx=2)
        tk.Button(center_frame, text=self.tr('toggle'), command=self.toggle_selected).pack(side=tk.LEFT, padx=2)
        tk.Button(center_frame, text=self.tr('delete'), command=self.delete_selected).pack(side=tk.LEFT, padx=2)
        tk.Button(center_frame, text=self.tr('up'), command=self.move_up).pack(side=tk.LEFT, padx=2)
        tk.Button(center_frame, text=self.tr('down'), command=self.move_down).pack(side=tk.LEFT, padx=2)
        tk.Button(center_frame, text=self.tr('refresh'), command=self.refresh_list).pack(side=tk.LEFT, padx=2)
        tk.Button(center_frame, text=self.tr('sort'), command=self.sort_by_column).pack(side=tk.LEFT, padx=2)
        tk.Button(center_frame, text=self.tr('close'), command=self.dialog.destroy).pack(side=tk.LEFT, padx=2)

        self.stats_label = ttk.Label(btn_panel, text=self.tr('total_active', total=len(self.bot.search_images), active=self.get_active_count()))
        self.stats_label.pack(side=tk.RIGHT, padx=5)

        self.dialog.transient(self.parent)
        self.dialog.focus_set()

    def select_by_description(self, desc):
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            if values and values[1] == desc:
                self.tree.selection_set(item)
                self.tree.focus(item)
                self.tree.see(item)
                break

    def select_by_uid(self, uid):
        if uid and self.tree.exists(uid):
            self.tree.selection_set(uid)
            self.tree.focus(uid)
            self.tree.see(uid)

    def _get_image_index_by_item_id(self, item_id):
        for index, img in enumerate(self.bot.search_images):
            if img.get("uid") == item_id:
                return index
        if str(item_id).isdigit():
            idx = int(item_id)
            if 0 <= idx < len(self.bot.search_images):
                return idx
        return None

    def sort_by_column(self, col_name=None):
        if col_name is None:
            col_name = self.current_sort_col or self.tr('col_description')
        col_names = [self.tr('col_num'), self.tr('col_description'), self.tr('col_action'), self.tr('col_delay'), self.tr('col_confidence'), self.tr('col_grayscale'), self.tr('col_status'), self.tr('col_group'), self.tr('col_numbers'), self.tr('col_clicks')]
        if col_name not in col_names:
            return
        col_idx = col_names.index(col_name)
        self.current_sort_col = col_name
        reverse = self.sort_reverse.get(col_idx, False)
        self.sort_reverse[col_idx] = not reverse

        def sort_value(item_id):
            value = self.tree.item(item_id, 'values')[col_idx]
            if col_idx in (0, 3, 4, 9):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return float('-inf')
            return str(value).lower()

        items = list(self.tree.get_children(''))
        items.sort(key=sort_value, reverse=reverse)
        for index, item in enumerate(items):
            self.tree.move(item, '', index)

    # ---------- Drag & Drop ----------
    def on_drag_start(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.drag_data["item"] = item
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y

    def on_drag_motion(self, event):
        if self.drag_data["item"]:
            target = self.tree.identify_row(event.y)
            if target and target != self.last_target:
                if self.last_target:
                    self.tree.item(self.last_target, tags=())
                if target:
                    self.tree.item(target, tags=('target',))
                    self.tree.tag_configure('target', background='lightblue')
                self.last_target = target

    def on_drag_drop(self, event):
        if self.drag_data["item"]:
            target_item = self.tree.identify_row(event.y)
            if self.last_target:
                self.tree.item(self.last_target, tags=())
                self.last_target = None
            if target_item and target_item != self.drag_data["item"]:
                src_index = self._get_image_index_by_item_id(self.drag_data["item"])
                dst_index = self._get_image_index_by_item_id(target_item)
                if src_index is None or dst_index is None:
                    self.drag_data["item"] = None
                    return

                # Удаляем элемент из списка
                moved_item = self.bot.search_images.pop(src_index)

                # Вставляем на новую позицию (перед целевой)
                if dst_index > src_index:
                    dst_index -= 1
                self.bot.search_images.insert(dst_index, moved_item)

                self.bot.save_config()
                self.refresh_list()
                self.tree.selection_set(moved_item["uid"])
                self.tree.focus(moved_item["uid"])
            self.drag_data["item"] = None

    # ---------- Подсчёт активных областей ----------
    def get_active_count(self):
        def is_active(img):
            if not img["enabled"]:
                return False
            if img["group"] and img["group"] in self.bot.groups:
                return self.bot.groups[img["group"]]
            return True
        return len([img for img in self.bot.search_images if is_active(img)])

    def refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, img in enumerate(self.bot.search_images):
            numbers_str = ", ".join(img.get("numbers", [])) if img.get("numbers") else "-"
            group_name = img.get("group", "")
            if group_name is None:
                group_name = ""
            self.tree.insert("", tk.END, iid=img["uid"], values=(
                i+1,
                img["description"],
                img["action"],
                f"{img['delay']:.2f}",
                f"{img['confidence']:.2f}",
                self.tr('yes') if img["grayscale"] else self.tr('no'),
                self.tr('active') if img["enabled"] else self.tr('inactive'),
                group_name,
                numbers_str,
                self.bot.stats.get(img["path"], 0)
            ))
        if self.stats_label:
            self.stats_label.config(text=self.tr('total_active', total=len(self.bot.search_images), active=self.get_active_count()))

    # ---------- Генерация уникального имени для копии ----------
    def generate_copy_name(self, base_name, existing_names):
        """Генерирует уникальное имя для копии с порядковым номером."""
        import re
        # Убираем возможный номер в скобках в конце
        clean_name = re.sub(r'\s*\(\d+\)$', '', base_name).strip()

        # Собираем все номера для этого чистого имени
        pattern = re.compile(r'^' + re.escape(clean_name) + r'\s*\((\d+)\)$')
        numbers = []
        for name in existing_names:
            match = pattern.match(name)
            if match:
                numbers.append(int(match.group(1)))

        if numbers:
            next_num = max(numbers) + 1
        else:
            # Нет ни одной копии с номером
            if clean_name in existing_names:
                # Оригинал без номера существует → первая копия (2)
                next_num = 2
            else:
                # Оригинала без номера нет (значит исходное имя уже было с номером,
                # но других копий нет). Тогда номер будет следующим после номера в исходном.
                # Но исходное имя уже есть в списке, поэтому numbers не пуст.
                # Этот случай практически невозможен, оставим запасной вариант.
                next_num = 2
        return f"{clean_name} ({next_num})"

    # ---------- Копирование области в другую группу ----------
    def copy_to_group(self, img):
        groups = sorted(list(self.bot.groups.keys()), key=str.lower)
        if not groups:
            self.bot._show_notification('warning', 'no_groups')
            return
        choice_dialog = tk.Toplevel(self.dialog)
        choice_dialog.title(self.tr('choose_group'))
        choice_dialog.geometry("300x150")
        choice_dialog.attributes("-topmost", True)
        choice_dialog.grab_set()
        choice_dialog.focus_set()
        choice_dialog.lift()
        choice_dialog.update_idletasks()
        x = (choice_dialog.winfo_screenwidth() - 300) // 2
        y = (choice_dialog.winfo_screenheight() - 150) // 2
        choice_dialog.geometry(f"300x150+{x}+{y}")

        tk.Label(choice_dialog, text="Выберите целевую группу:", font=("Arial", 10)).pack(pady=10)

        group_var = tk.StringVar()
        group_combo = ttk.Combobox(choice_dialog, textvariable=group_var, values=groups, state='readonly', width=20)
        group_combo.pack(pady=5)
        if groups:
            group_combo.current(0)

        def do_copy():
            target_group = group_var.get()
            if not target_group:
                return
            old_path = Path(img["path"])
            new_folder = self.bot._get_group_path(target_group)
            safe_description = self.bot._transliterate(img["description"])
            safe_description = safe_description.replace(' ', '_')
            safe_description = ''.join(c for c in safe_description if c.isalnum() or c == '_')
            safe_description = safe_description.strip('_')
            if not safe_description:
                safe_description = "area"
            if len(safe_description) > 30:
                safe_description = safe_description[:30]
            timestamp = time.strftime("%H%M%S")
            new_filename = new_folder / f"{safe_description}_{timestamp}.png"
            if new_filename.exists():
                new_filename = new_folder / f"{safe_description}_{timestamp}_{uuid.uuid4().hex[:4]}.png"
            shutil.copy2(old_path, new_filename)

            # Генерируем уникальное описание для копии
            existing_names = [i["description"] for i in self.bot.search_images]
            new_description = self.generate_copy_name(img["description"], existing_names)

            new_image = {
                "uid": str(uuid.uuid4()),
                "path": str(new_filename),
                "action": img["action"],
                "delay": img["delay"],
                "confidence": img["confidence"],
                "grayscale": img["grayscale"],
                "description": new_description,
                "enabled": img["enabled"],
                "click_offset": img["click_offset"],
                "numbers": img["numbers"].copy(),
                "click_sequence": img["click_sequence"].copy(),
                "last_used": 0,
                "cooldown": img["cooldown"],
                "group": target_group,
                "use_scaling": img["use_scaling"],
            }
            self.bot.search_images.append(new_image)
            self.bot.stats[str(new_filename)] = 0
            self.bot.save_config()
            self.refresh_list()
            choice_dialog.destroy()
            self.bot._show_notification('success', 'area_saved', name=new_image["description"])

        btn_frame = tk.Frame(choice_dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Копировать", command=do_copy, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Отмена", command=choice_dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)

        choice_dialog.bind('<Escape>', lambda e: choice_dialog.destroy())
        choice_dialog.bind('<Return>', lambda e: do_copy())

    # ---------- Редактирование области ----------
    def edit_selected(self):
        selected = self.tree.selection()
        if not selected:
            self.bot._show_notification('warning', 'select_area_first')
            return
        idx = self._get_image_index_by_item_id(selected[0])
        if idx is None:
            self.bot._show_notification('error', 'error', message="Не удалось определить выбранную область.")
            return
        img = self.bot.search_images[idx]

        edit_dialog = tk.Toplevel(self.dialog)
        edit_dialog.title(self.tr('edit_title', name=img['description']))
        edit_dialog.geometry("600x800")
        edit_dialog.attributes("-topmost", True)
        edit_dialog.grab_set()
        edit_dialog.focus_set()
        edit_dialog.lift()
        edit_dialog.update_idletasks()
        x = (edit_dialog.winfo_screenwidth() - 600) // 2
        y = (edit_dialog.winfo_screenheight() - 800) // 2
        edit_dialog.geometry(f"600x800+{x}+{y}")

        edit_dialog.bind('<Return>', lambda e: save_edit())
        edit_dialog.bind('<Escape>', lambda e: edit_dialog.destroy())

        main = ttk.Frame(edit_dialog, padding="10")
        main.pack(fill=tk.BOTH, expand=True)

        # Описание
        ttk.Label(main, text=self.tr('col_description')+':').grid(row=0, column=0, sticky="w", pady=5)
        desc_var = tk.StringVar(value=img["description"])
        desc_entry = ttk.Entry(main, textvariable=desc_var, width=40)
        desc_entry.grid(row=0, column=1, pady=5)

        # Действие
        ttk.Label(main, text=self.tr('action')+':').grid(row=1, column=0, sticky="w", pady=5)
        action_var = tk.StringVar(value=img["action"])
        action_combo = ttk.Combobox(main, textvariable=action_var,
                                    values=["click", "double_click", "right_click", "move"],
                                    state="readonly", width=20)
        action_combo.grid(row=1, column=1, sticky="w", pady=5)

        # Задержка
        ttk.Label(main, text=self.tr('delay_sec')+':').grid(row=2, column=0, sticky="w", pady=5)
        delay_var = tk.DoubleVar(value=img["delay"])
        delay_spin = ttk.Spinbox(main, from_=0.0, to=5.0, increment=0.05,
                                textvariable=delay_var, width=10)
        delay_spin.grid(row=2, column=1, sticky="w", pady=5)

        # Точность
        ttk.Label(main, text=self.tr('accuracy')+':').grid(row=3, column=0, sticky="w", pady=5)
        conf_frame = ttk.Frame(main)
        conf_frame.grid(row=3, column=1, sticky="w", pady=5)
        conf_var = tk.DoubleVar(value=img["confidence"])
        conf_scale = ttk.Scale(conf_frame, from_=0.7, to=0.99, variable=conf_var,
                               orient=tk.HORIZONTAL, length=200)
        conf_scale.pack(side=tk.LEFT)
        conf_label = ttk.Label(conf_frame, text=f"{conf_var.get():.2f}", width=5)
        conf_label.pack(side=tk.LEFT, padx=5)
        conf_scale.configure(command=lambda v: conf_label.config(text=f"{float(v):.2f}"))

        # Grayscale
        grayscale_var = tk.BooleanVar(value=img["grayscale"])
        ttk.Checkbutton(main, text=self.tr('grayscale_check'),
                       variable=grayscale_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=5)

        # Статус
        enabled_var = tk.BooleanVar(value=img["enabled"])
        ttk.Checkbutton(main, text=self.tr('active_check'),
                       variable=enabled_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=5)

        # Использовать масштабирование для этой области
        use_scaling_var = tk.BooleanVar(value=img.get("use_scaling", True))
        ttk.Checkbutton(main, text=self.tr('use_scaling'),
                       variable=use_scaling_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=5)

        # Группа
        ttk.Label(main, text=self.tr('col_group')+':').grid(row=8, column=0, sticky="w", pady=5)
        group_var = tk.StringVar(value=img.get("group") or "")
        group_list = sorted(list(self.bot.groups.keys()), key=str.lower)
        group_combo = ttk.Combobox(main, textvariable=group_var, values=group_list,
                                   state="normal", width=37)
        group_combo.grid(row=8, column=1, sticky="w", pady=5)

        # Числа для ввода
        ttk.Label(main, text=self.tr('numbers_entry')).grid(row=9, column=0, columnspan=2, sticky="w", pady=5)
        numbers_var = tk.StringVar(value=", ".join(img.get("numbers", [])))
        numbers_entry = ttk.Entry(main, textvariable=numbers_var, width=40)
        numbers_entry.grid(row=10, column=0, columnspan=2, pady=5)

        # Последовательность кликов
        ttk.Label(main, text=self.tr('click_sequence')).grid(row=11, column=0, columnspan=2, sticky="w", pady=5)
        seq_var = tk.StringVar(value="; ".join(f"{dx},{dy}" for dx, dy in img.get("click_sequence", [])))
        seq_entry = ttk.Entry(main, textvariable=seq_var, width=40)
        seq_entry.grid(row=12, column=0, columnspan=2, pady=5)
        ttk.Label(main, text=self.tr('click_sequence_help'), font=("Arial", 8, "italic")).grid(row=13, column=0, columnspan=2, sticky="w")

        # Кнопки
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=14, column=0, columnspan=2, pady=10)

        def resnap():
            edit_dialog.destroy()
            def replace_area(x1, y1, x2, y2):
                try:
                    if x1 == x2 or y1 == y2:
                        self.bot._show_notification('error', 'area_zero')
                        return
                    new_img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
                    new_img.save(img["path"])
                    self.bot.invalidate_template(img["path"])
                    self.bot._show_notification('success', 'area_saved', name=img["description"])
                    if self.bot.root:
                        self.bot.root.event_generate("<<GroupsChanged>>")
                except Exception as e:
                    logger.exception("Ошибка при пересъёмке области:")
                    self.bot._show_notification('error', 'error', message=str(e))
            if self.parent:
                self.parent.withdraw()
            selector = ScreenSelector(
                master=self.parent,
                callback=replace_area,
                on_cancel=lambda: self.parent.deiconify() if self.parent else None
            )

        tk.Button(btn_frame, text=self.tr('resnap'), command=resnap).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=self.tr('copy_to_group_btn'), command=lambda: self.copy_to_group(img)).pack(side=tk.LEFT, padx=5)

        def save_edit():
            old_group = img.get("group")
            img["description"] = desc_var.get()
            img["action"] = action_var.get()
            img["delay"] = delay_var.get()
            img["confidence"] = conf_var.get()
            img["grayscale"] = grayscale_var.get()
            img["enabled"] = enabled_var.get()
            img["use_scaling"] = use_scaling_var.get()

            new_group = group_var.get().strip()
            if new_group:
                if new_group not in self.bot.groups:
                    self.bot.groups[new_group] = True
                img["group"] = new_group
            else:
                img["group"] = None

            if new_group != old_group:
                self.bot._move_image_to_group(img, new_group if new_group else None)

            numbers_text = numbers_var.get().strip()
            img["numbers"] = [part.strip() for part in numbers_text.split(',') if part.strip()] if numbers_text else []

            seq_text = seq_var.get().strip()
            try:
                click_seq = parse_click_sequence(seq_text)
            except Exception:
                self.bot._show_notification('error', 'error', message=f"Неверный формат последовательности: {seq_text}")
                return
            img["click_sequence"] = click_seq

            self.refresh_list()
            self.bot.save_config()
            edit_dialog.destroy()
            self.bot._show_notification('success', 'settings_saved')
            if self.bot.root:
                self.bot.root.event_generate("<<GroupsChanged>>")

        btn_save_frame = ttk.Frame(main)
        btn_save_frame.grid(row=15, column=0, columnspan=2, pady=10)
        ttk.Button(btn_save_frame, text=self.tr('save_enter'), command=save_edit).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_save_frame, text=self.tr('cancel_esc'), command=edit_dialog.destroy).pack(side=tk.LEFT, padx=5)

    def toggle_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        for item in selected:
            idx = self._get_image_index_by_item_id(item)
            if idx is None:
                continue
            self.bot.search_images[idx]["enabled"] = not self.bot.search_images[idx]["enabled"]
        self.refresh_list()
        self.bot.save_config()

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        if messagebox.askyesno(self.tr('warning'), self.tr('delete_confirm', count=len(selected))):
            deleted_count = 0
            failed_files = []
            indexes_to_delete = []
            for item in selected:
                idx = self._get_image_index_by_item_id(item)
                if idx is not None:
                    indexes_to_delete.append(idx)
            for idx in sorted(set(indexes_to_delete), reverse=True):
                img = self.bot.search_images[idx]
                img_path = img["path"]
                try:
                    if os.path.exists(img_path):
                        if self.bot._delete_image(img):
                            deleted_count += 1
                        else:
                            failed_files.append(img_path)
                    else:
                        failed_files.append(img_path)
                except Exception as e:
                    logger.error(f"Ошибка удаления файла {img_path}: {e}")
                    failed_files.append(img_path)
                del self.bot.search_images[idx]
            self.refresh_list()
            self.bot.save_config()
            if self.bot.root:
                self.bot.root.event_generate("<<GroupsChanged>>")
            msg = self.tr('moved_to_trash', count=deleted_count)
            if failed_files:
                msg += f"\n{self.tr('delete_failed', failed=len(failed_files))}"
            self.bot._show_notification('success', 'success', message=msg)

    def move_up(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = self._get_image_index_by_item_id(selected[0])
        if idx is None:
            return
        if idx > 0:
            self.bot.search_images[idx], self.bot.search_images[idx-1] = self.bot.search_images[idx-1], self.bot.search_images[idx]
            moved_uid = self.bot.search_images[idx-1]["uid"]
            self.refresh_list()
            self.bot.save_config()
            self.tree.selection_set(moved_uid)
            self.tree.focus(moved_uid)

    def move_down(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = self._get_image_index_by_item_id(selected[0])
        if idx is None:
            return
        if idx < len(self.bot.search_images) - 1:
            self.bot.search_images[idx], self.bot.search_images[idx+1] = self.bot.search_images[idx+1], self.bot.search_images[idx]
            moved_uid = self.bot.search_images[idx+1]["uid"]
            self.refresh_list()
            self.bot.save_config()
            self.tree.selection_set(moved_uid)
            self.tree.focus(moved_uid)

    def _move_selection(self, delta):
        selection = self.tree.selection()
        if selection:
            current = self.tree.index(selection[0])
            new = current + delta
            if 0 <= new < len(self.tree.get_children()):
                self.tree.selection_set(self.tree.get_children()[new])
                self.tree.focus(self.tree.get_children()[new])
        else:
            if len(self.tree.get_children()) > 0:
                self.tree.selection_set(self.tree.get_children()[0])
                self.tree.focus(self.tree.get_children()[0])
        return "break"

class RoutineTasksDialog:
    """Compact scenario settings for healing and resource gathering."""

    BUILT_IN_IDS = {"heal", "prize_hunt", "food", "wood", "metal", "oil"}

    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.dialog = None
        self.rows = []
        self.max_marches_var = None

    def tr(self, key, **kwargs):
        return self.bot.tr(key, **kwargs)

    def show(self):
        if not self.bot.stop_event.is_set():
            self.bot._show_notification('warning', 'stop_bot_first')
            return

        self.rows = []
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(self.tr('routine_dialog_title'))
        self.dialog.geometry("1180x520")
        self.dialog.minsize(980, 420)
        self.dialog.attributes("-topmost", True)
        self.dialog.grab_set()
        self.dialog.focus_set()
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 1180) // 2
        y = (self.dialog.winfo_screenheight() - 520) // 2
        self.dialog.geometry(f"1180x520+{x}+{y}")

        ttk.Label(
            self.dialog,
            text=self.tr('routine_config_help'),
            foreground="#555555",
            wraplength=1120,
        ).pack(fill=tk.X, padx=12, pady=(10, 6))

        table = ttk.Frame(self.dialog, padding=8)
        table.pack(fill=tk.BOTH, expand=True)
        headers = (
            self.tr('routine_task_name'),
            self.tr('routine_group'),
            self.tr('routine_interval'),
            self.tr('routine_timeout'),
            self.tr('routine_uses_march'),
            self.tr('routine_march_duration'),
            self.tr('routine_final_template'),
            self.tr('routine_templates', count=""),
        )
        for column, text_value in enumerate(headers):
            ttk.Label(table, text=text_value, font=("Arial", 9, "bold")).grid(
                row=0, column=column, padx=3, pady=4, sticky="w"
            )

        group_values = sorted(self.bot.groups.keys(), key=str.lower)
        for row_index, task in enumerate(self.bot.routine_tasks, start=1):
            enabled_var = tk.BooleanVar(value=task.get("enabled", True))
            group_var = tk.StringVar(value=task.get("group", ""))
            interval_var = tk.DoubleVar(value=task.get("interval_minutes", 1.0))
            timeout_var = tk.DoubleVar(value=task.get("timeout_seconds", 8.0))
            uses_march_var = tk.BooleanVar(value=task.get("uses_march", False))
            duration_var = tk.DoubleVar(value=task.get("march_duration_minutes", 30.0))
            completion_var = tk.StringVar(value=self.tr('routine_auto_finish'))

            name_frame = ttk.Frame(table)
            name_frame.grid(row=row_index, column=0, sticky="w", padx=3, pady=4)
            ttk.Checkbutton(name_frame, variable=enabled_var).pack(side=tk.LEFT)
            ttk.Label(name_frame, text=self.bot.get_routine_task_name(task), width=17).pack(side=tk.LEFT)

            group_combo = ttk.Combobox(
                table,
                textvariable=group_var,
                values=group_values,
                state="normal",
                width=18,
            )
            group_combo.grid(row=row_index, column=1, padx=3, pady=4)
            ttk.Spinbox(
                table, from_=0.1, to=1440.0, increment=0.1,
                textvariable=interval_var, width=8,
            ).grid(row=row_index, column=2, padx=3, pady=4)
            ttk.Spinbox(
                table, from_=1.0, to=120.0, increment=1.0,
                textvariable=timeout_var, width=8,
            ).grid(row=row_index, column=3, padx=3, pady=4)
            ttk.Checkbutton(table, variable=uses_march_var).grid(
                row=row_index, column=4, padx=14, pady=4
            )
            ttk.Spinbox(
                table, from_=1.0, to=1440.0, increment=1.0,
                textvariable=duration_var, width=8,
            ).grid(row=row_index, column=5, padx=3, pady=4)

            completion_combo = ttk.Combobox(
                table,
                textvariable=completion_var,
                state="readonly",
                width=24,
            )
            completion_combo.grid(row=row_index, column=6, padx=3, pady=4)
            count_label = ttk.Label(table, width=12)
            count_label.grid(row=row_index, column=7, padx=3, pady=4, sticky="w")

            row_data = {
                "task_id": task["id"],
                "enabled": enabled_var,
                "group": group_var,
                "interval": interval_var,
                "timeout": timeout_var,
                "uses_march": uses_march_var,
                "duration": duration_var,
                "completion": completion_var,
                "completion_combo": completion_combo,
                "completion_map": {},
                "count_label": count_label,
            }
            self.rows.append(row_data)
            self._refresh_completion_choices(row_data, task.get("completion_uid", ""))
            completion_combo.configure(
                postcommand=lambda row=row_data: self._refresh_completion_choices(row)
            )

            ttk.Button(
                table,
                text=self.tr('routine_add_template'),
                command=lambda task_id=task["id"]: self.capture_template(task_id),
            ).grid(row=row_index, column=8, padx=4, pady=4)

            if task["id"] not in self.BUILT_IN_IDS:
                ttk.Button(
                    table,
                    text=self.tr('delete'),
                    command=lambda task_id=task["id"]: self.delete_task(task_id),
                ).grid(row=row_index, column=9, padx=3, pady=4)

        footer = ttk.Frame(self.dialog, padding=8)
        footer.pack(fill=tk.X)
        self.max_marches_var = tk.IntVar(value=self.bot.routine_max_marches)
        ttk.Label(footer, text=self.tr('routine_max_marches')).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Spinbox(
            footer,
            from_=1,
            to=5,
            textvariable=self.max_marches_var,
            width=3,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(
            footer,
            text=self.tr(
                'routine_marches',
                active=self.bot.get_active_marches(),
                maximum=self.bot.routine_max_marches,
            ),
            font=("Arial", 10, "bold"),
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text=self.tr('routine_reset_marches'), command=self.bot.reset_routine_marches).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(footer, text=self.tr('routine_new_task'), command=self.add_task).pack(side=tk.LEFT, padx=12)
        ttk.Button(footer, text=self.tr('profile_export'), command=self.export_profile).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text=self.tr('profile_import'), command=self.import_profile).pack(side=tk.LEFT, padx=4)
        ttk.Button(footer, text=self.tr('save'), command=self.save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(footer, text=self.tr('cancel'), command=self.dialog.destroy).pack(side=tk.RIGHT, padx=4)

        self.dialog.bind('<Return>', lambda _event: self.save())
        self.dialog.bind('<Escape>', lambda _event: self.dialog.destroy())
        self.dialog.transient(self.parent)

    def _template_choices(self, group_name):
        choices = {}
        for image in self.bot.search_images:
            if image.get("group") != group_name:
                continue
            label = f"{image.get('description', '')} [{str(image.get('uid', ''))[:8]}]"
            choices[label] = image.get("uid", "")
        return choices

    def _refresh_completion_choices(self, row, selected_uid=None):
        choices = self._template_choices(row["group"].get().strip())
        row["completion_map"] = choices
        auto_label = self.tr('routine_auto_finish')
        row["completion_combo"]["values"] = [auto_label, *choices.keys()]
        target_uid = selected_uid
        if target_uid is None:
            target_uid = choices.get(row["completion"].get(), "")
        selected_label = next((label for label, uid in choices.items() if uid == target_uid), auto_label)
        row["completion"].set(selected_label)
        row["count_label"].config(text=str(len(choices)))

    def _apply_rows(self, notify=True):
        try:
            self.bot.routine_max_marches = min(5, max(1, int(self.max_marches_var.get())))
            self.bot.routine_march_deadlines = self.bot.routine_march_deadlines[:self.bot.routine_max_marches]
            for row in self.rows:
                task = self.bot.get_routine_task(row["task_id"])
                if not task:
                    continue
                group = row["group"].get().strip()
                if not group:
                    raise ValueError(self.tr('routine_group'))
                task["group"] = group
                task["enabled"] = row["enabled"].get()
                task["interval_minutes"] = max(0.1, float(row["interval"].get()))
                task["timeout_seconds"] = max(1.0, float(row["timeout"].get()))
                task["uses_march"] = row["uses_march"].get()
                task["march_duration_minutes"] = max(1.0, float(row["duration"].get()))
                completion_map = self._template_choices(group)
                task["completion_uid"] = completion_map.get(row["completion"].get(), "")
                self.bot.groups[group] = task["enabled"]
        except (tk.TclError, TypeError, ValueError) as exc:
            self.bot._show_notification('error', 'error', message=str(exc))
            return False

        self.bot.routine_tasks = normalize_routine_tasks(self.bot.routine_tasks)
        self.bot.save_config()
        if self.bot.root:
            self.bot.root.event_generate("<<GroupsChanged>>")
        if notify:
            self.bot._show_notification('success', 'settings_saved')
        return True

    def save(self):
        if not self._apply_rows():
            return
        self.dialog.destroy()

    def capture_template(self, task_id):
        if not self._apply_rows(notify=False):
            return
        task = self.bot.get_routine_task(task_id)
        if not task:
            return
        group = task.get("group", "")
        description = f"{self.bot.get_routine_task_name(task)} {len(self.bot.get_routine_templates(task)) + 1}"
        self.dialog.destroy()
        self.bot.select_area(
            self.parent,
            default_group=group,
            default_description=description,
        )

    def add_task(self):
        name = simpledialog.askstring(
            self.tr('routine_new_task'),
            self.tr('routine_task_name') + ':',
            parent=self.dialog,
        )
        if not name or not name.strip():
            return
        if not self._apply_rows(notify=False):
            return
        name = name.strip()
        self.bot.routine_tasks.append({
            "id": f"custom_{uuid.uuid4().hex}",
            "name": name,
            "group": name,
            "enabled": True,
            "uses_march": False,
            "priority": 100,
            "interval_minutes": 1.0,
            "timeout_seconds": 8.0,
            "march_duration_minutes": 30.0,
            "completion_uid": "",
        })
        self.bot.groups.setdefault(name, True)
        self.bot.save_config()
        self.dialog.destroy()
        self.show()

    def delete_task(self, task_id):
        if task_id in self.BUILT_IN_IDS:
            return
        self.bot.routine_tasks = [
            task for task in self.bot.routine_tasks if task.get("id") != task_id
        ]
        self.bot.save_config()
        self.dialog.destroy()
        self.show()

    def export_profile(self):
        if not self._apply_rows(notify=False):
            return
        destination = filedialog.asksaveasfilename(
            parent=self.dialog,
            title=self.tr('profile_export'),
            defaultextension=".zip",
            filetypes=[("BuZzbot profile", "*.zip")],
            initialfile="BuZzbot_Training_Profile.zip",
        )
        if not destination:
            return
        try:
            count = self.bot.export_training_profile(destination)
        except Exception as exc:
            logger.exception("Ошибка экспорта профиля обучения")
            self.bot._show_notification('error', 'error', message=str(exc))
            return
        self.bot._show_notification(
            'success',
            'profile_saved',
            path=destination,
            count=count,
        )

    def import_profile(self):
        source = filedialog.askopenfilename(
            parent=self.dialog,
            title=self.tr('profile_import'),
            filetypes=[("BuZzbot profile", "*.zip")],
        )
        if not source:
            return
        try:
            result = self.bot.import_training_profile(source)
        except Exception as exc:
            logger.exception("Ошибка импорта профиля обучения")
            self.bot._show_notification('error', 'error', message=str(exc))
            return
        self.dialog.destroy()
        self.bot._show_notification('success', 'profile_loaded', **result)


class GroupScheduleDialog:
    """Диалог настройки расписания групп и циклического режима с поддержкой профилей."""
    def __init__(self, parent, bot):
        self.parent = parent
        self.bot = bot
        self.dialog = None
        self.vars = {}          # для автовключения
        self.order_vars = {}     # для порядка и задержек
        self.cycle_listbox = None
        self.cycle_enabled_var = None
        self.cycle_timeout_var = None
        self.profile_combo = None
        self.current_profile_name = tk.StringVar()
        self.drag_data = {"item": None, "index": None, "y": 0, "selection": None}

    def tr(self, key, **kwargs):
        return self.bot.tr(key, **kwargs)

    def show(self):
        if not self.bot.groups:
            self.bot._show_notification('info', 'no_groups')
            return

        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(self.bot.tr('group_schedule_title'))
        self.dialog.geometry("950x750")
        self.dialog.attributes("-topmost", True)
        self.dialog.grab_set()
        self.dialog.focus_set()
        self.dialog.lift()
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 950) // 2
        y = (self.dialog.winfo_screenheight() - 750) // 2
        self.dialog.geometry(f"950x750+{x}+{y}")

        # Верхняя панель с выбором профиля
        profile_frame = ttk.Frame(self.dialog)
        profile_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(profile_frame, text="Профиль циклов:").pack(side=tk.LEFT, padx=5)
        self.profile_combo = ttk.Combobox(profile_frame, textvariable=self.current_profile_name,
                                          values=list(self.bot.cycle_profiles.keys()),
                                          state='readonly', width=20)
        self.profile_combo.pack(side=tk.LEFT, padx=5)
        self.profile_combo.bind('<<ComboboxSelected>>', self.on_profile_selected)

        ttk.Button(profile_frame, text="Новый", command=self.new_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(profile_frame, text="Удалить", command=self.delete_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(profile_frame, text="Переименовать", command=self.rename_profile).pack(side=tk.LEFT, padx=2)

        # Notebook (вкладки)
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ========== Вкладка 1: Автовключение ==========
        schedule_frame = ttk.Frame(notebook)
        notebook.add(schedule_frame, text="Автовключение")

        info_label = ttk.Label(schedule_frame,
            text="Если установлена галочка «Авто», группа будет автоматически включаться/выключаться по расписанию.\n"
                 "Если указана длительность, используется интервал (вкл. в заданное время на N минут).",
            font=("Arial", 9, "italic"), foreground="gray")
        info_label.pack(anchor='w', padx=10, pady=5)

        canvas = tk.Canvas(schedule_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(schedule_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # Заголовки
        header = ttk.Frame(scrollable_frame)
        header.pack(fill=tk.X, pady=2)
        ttk.Label(header, text="Группа", width=20, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(header, text="Авто", width=5, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(header, text="Вкл (ЧЧ:ММ)", width=12, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(header, text="Выкл (ЧЧ:ММ)", width=12, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(header, text="Интервал (мин)", width=14, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)

        def validate_spinbox(value, min_val, max_val):
            if value == "":
                return True
            try:
                v = int(value)
                return min_val <= v <= max_val
            except ValueError:
                return False

        vcmd_hour = (self.dialog.register(lambda v: validate_spinbox(v, 0, 23)), '%P')
        vcmd_minute = (self.dialog.register(lambda v: validate_spinbox(v, 0, 59)), '%P')
        vcmd_duration = (self.dialog.register(lambda v: validate_spinbox(v, 0, 1440)), '%P')

        for group in sorted(self.bot.groups.keys()):
            row = ttk.Frame(scrollable_frame)
            row.pack(fill=tk.X, pady=2)

            group_label = tk.Label(row, text=group, width=20, anchor="w", cursor="hand2",
                                    font=("Arial", 9))
            group_label.pack(side=tk.LEFT, padx=2)
            group_label.bind("<Double-Button-1>", lambda e, g=group: self.rename_group(g))

            auto_var = tk.BooleanVar()
            on_hour_var = tk.StringVar()
            on_min_var = tk.StringVar()
            off_hour_var = tk.StringVar()
            off_min_var = tk.StringVar()
            duration_var = tk.StringVar()
            type_var = tk.StringVar(value='time')

            schedule = self.bot.group_schedules.get(group, {})
            auto_var.set(schedule.get('auto', False))
            on_time = schedule.get('on_time', '')
            if on_time and ':' in on_time:
                on_h, on_m = on_time.split(':')
                on_hour_var.set(on_h)
                on_min_var.set(on_m)
            off_time = schedule.get('off_time', '')
            if off_time and ':' in off_time:
                off_h, off_m = off_time.split(':')
                off_hour_var.set(off_h)
                off_min_var.set(off_m)
            duration_var.set(str(schedule.get('duration', '')))
            if schedule.get('type') == 'interval':
                type_var.set('interval')

            cb = ttk.Checkbutton(row, variable=auto_var)
            cb.pack(side=tk.LEFT, padx=2)

            on_hour_spin = ttk.Spinbox(row, from_=0, to=23, width=3, format='%02.0f',
                                        validate='key', validatecommand=vcmd_hour,
                                        textvariable=on_hour_var)
            on_hour_spin.pack(side=tk.LEFT, padx=1)
            ttk.Label(row, text=":").pack(side=tk.LEFT)
            on_min_spin = ttk.Spinbox(row, from_=0, to=59, width=3, format='%02.0f',
                                        validate='key', validatecommand=vcmd_minute,
                                        textvariable=on_min_var)
            on_min_spin.pack(side=tk.LEFT, padx=1)

            off_hour_spin = ttk.Spinbox(row, from_=0, to=23, width=3, format='%02.0f',
                                         validate='key', validatecommand=vcmd_hour,
                                         textvariable=off_hour_var)
            off_hour_spin.pack(side=tk.LEFT, padx=1)
            ttk.Label(row, text=":").pack(side=tk.LEFT)
            off_min_spin = ttk.Spinbox(row, from_=0, to=59, width=3, format='%02.0f',
                                         validate='key', validatecommand=vcmd_minute,
                                         textvariable=off_min_var)
            off_min_spin.pack(side=tk.LEFT, padx=1)

            duration_spin = ttk.Spinbox(row, from_=0, to=1440, width=6, format='%02.0f',
                                         validate='key', validatecommand=vcmd_duration,
                                         textvariable=duration_var)
            duration_spin.pack(side=tk.LEFT, padx=2)

            self.vars[group] = (auto_var, on_hour_var, on_min_var, off_hour_var, off_min_var, duration_var, type_var)

        btn_schedule = ttk.Button(schedule_frame, text=self.bot.tr('save'),
                                   command=self.save_schedule)
        btn_schedule.pack(pady=5)

        # ========== Вкладка 2: Порядок и задержки ==========
        order_frame = ttk.Frame(notebook)
        notebook.add(order_frame, text="Порядок и задержки")

        info_order = ttk.Label(order_frame,
            text="Порядок групп определяет, в какой последовательности будут выполняться их области.\n"
                 "Задержка между областями – пауза после каждого действия внутри группы (пока не используется).\n"
                 "Задержка после группы – пауза после того, как все области группы были проверены.",
            font=("Arial", 9, "italic"), foreground="gray")
        info_order.pack(anchor='w', padx=10, pady=5)

        order_canvas = tk.Canvas(order_frame, highlightthickness=0)
        order_scrollbar = ttk.Scrollbar(order_frame, orient=tk.VERTICAL, command=order_canvas.yview)
        order_scrollable = ttk.Frame(order_canvas)

        order_scrollable.bind(
            "<Configure>",
            lambda e: order_canvas.configure(scrollregion=order_canvas.bbox("all"))
        )
        order_canvas.create_window((0, 0), window=order_scrollable, anchor="nw")
        order_canvas.configure(yscrollcommand=order_scrollbar.set)

        order_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0), pady=5)
        order_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        header2 = ttk.Frame(order_scrollable)
        header2.pack(fill=tk.X, pady=2)
        ttk.Label(header2, text="Группа", width=20, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(header2, text="Задержка между (сек)", width=18, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(header2, text="Задержка после (сек)", width=18, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)

        listbox_frame = ttk.Frame(order_scrollable)
        listbox_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(listbox_frame, text="Порядок групп (перетаскивание или кнопки):").pack(anchor='w')
        self.order_listbox = tk.Listbox(listbox_frame, selectmode=tk.SINGLE, height=6, font=("Arial", 10))
        self.order_listbox.pack(fill=tk.X, pady=2)

        ordered = sorted(self.bot.group_execution.items(), key=lambda x: x[1].get('order', 999))
        group_order = [g for g, _ in ordered]
        for g in self.bot.groups:
            if g not in group_order:
                group_order.append(g)
        for g in group_order:
            self.order_listbox.insert(tk.END, g)

        move_frame = ttk.Frame(order_scrollable)
        move_frame.pack(pady=2)
        tk.Button(move_frame, text="▲ Вверх", command=self.move_up).pack(side=tk.LEFT, padx=2)
        tk.Button(move_frame, text="▼ Вниз", command=self.move_down).pack(side=tk.LEFT, padx=2)

        delay_frames = {}
        for group in group_order:
            row = ttk.Frame(order_scrollable)
            row.pack(fill=tk.X, pady=2)

            ttk.Label(row, text=group, width=20).pack(side=tk.LEFT, padx=2)

            between_var = tk.DoubleVar(value=self.bot.group_execution.get(group, {}).get('delay_between', 0.0))
            between_spin = ttk.Spinbox(row, from_=0.0, to=10.0, increment=0.1, width=10,
                                        textvariable=between_var)
            between_spin.pack(side=tk.LEFT, padx=2)

            after_var = tk.DoubleVar(value=self.bot.group_execution.get(group, {}).get('delay_after', 0.0))
            after_spin = ttk.Spinbox(row, from_=0.0, to=30.0, increment=0.1, width=10,
                                      textvariable=after_var)
            after_spin.pack(side=tk.LEFT, padx=2)

            delay_frames[group] = (between_var, after_var)

        tk.Button(order_scrollable, text=self.bot.tr('save'),
                  command=lambda: self.save_order(delay_frames)).pack(pady=10)

        # ========== Вкладка 3: Циклы аккаунтов ==========
        cycle_frame = ttk.Frame(notebook)
        notebook.add(cycle_frame, text="Циклы аккаунтов")

        info_cycle = ttk.Label(cycle_frame,
            text="Включите циклический режим, чтобы бот перебирал группы по очереди.\n"
                 "Если в текущей группе нет действий дольше таймаута, бот переключится на следующую группу.\n"
                 "Это позволяет автоматически обслуживать несколько аккаунтов в одном окне.",
            font=("Arial", 9, "italic"), foreground="gray")
        info_cycle.pack(anchor='w', padx=10, pady=5)

        self.cycle_enabled_var = tk.BooleanVar(value=self.bot.cycle_mode)
        ttk.Checkbutton(cycle_frame, text=self.bot.tr('cycle_enable'),
                        variable=self.cycle_enabled_var).pack(anchor='w', padx=10, pady=2)

        timeout_frame = ttk.Frame(cycle_frame)
        timeout_frame.pack(anchor='w', padx=10, pady=5)
        ttk.Label(timeout_frame, text=self.bot.tr('cycle_timeout')).pack(side=tk.LEFT)
        self.cycle_timeout_var = tk.DoubleVar(value=self.bot.cycle_timeout)
        ttk.Spinbox(timeout_frame, from_=1.0, to=60.0, increment=1.0,
                    textvariable=self.cycle_timeout_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Label(cycle_frame, text=self.bot.tr('cycle_groups')).pack(anchor='w', padx=10, pady=2)

        cycle_listbox_frame = ttk.Frame(cycle_frame)
        cycle_listbox_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(cycle_listbox_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.cycle_listbox = tk.Listbox(cycle_listbox_frame, selectmode=tk.SINGLE, height=8, font=("Arial", 10),
                                        yscrollcommand=scrollbar.set,
                                        selectbackground='lightblue',
                                        selectforeground='black')
        self.cycle_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.cycle_listbox.yview)

        # Привязка событий для drag & drop
        self.cycle_listbox.bind("<Button-1>", self.on_drag_start)
        self.cycle_listbox.bind("<B1-Motion>", self.on_drag_motion)
        self.cycle_listbox.bind("<ButtonRelease-1>", self.on_drag_drop)

        cycle_btn_frame = ttk.Frame(cycle_frame)
        cycle_btn_frame.pack(pady=5)

        tk.Button(cycle_btn_frame, text="➕ Добавить", command=self.add_to_cycle).pack(side=tk.LEFT, padx=2)
        tk.Button(cycle_btn_frame, text="➖ Удалить", command=self.remove_from_cycle).pack(side=tk.LEFT, padx=2)

        cycle_move_frame = ttk.Frame(cycle_frame)
        cycle_move_frame.pack(pady=2)
        tk.Button(cycle_move_frame, text="▲ Вверх", command=self.move_cycle_up).pack(side=tk.LEFT, padx=2)
        tk.Button(cycle_move_frame, text="▼ Вниз", command=self.move_cycle_down).pack(side=tk.LEFT, padx=2)

        # Устанавливаем текущий профиль и загружаем его данные
        self.current_profile_name.set(self.bot.current_cycle_profile)
        self.update_profile_combo()
        self.load_current_profile()

        # Кнопка сохранения цикла
        tk.Button(cycle_frame, text=self.bot.tr('save'),
                  command=self.save_cycle).pack(pady=10)

        # ========== Общие кнопки ==========
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Button(btn_frame, text=self.bot.tr('rename_group'),
                  command=self.rename_selected_group).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text=self.bot.tr('delete_group'),
                  command=self.delete_group).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text=self.bot.tr('cancel'),
                  command=self.dialog.destroy).pack(side=tk.LEFT, padx=2)

        self.dialog.bind('<Escape>', lambda e: self.dialog.destroy())

    # ---------- Управление профилями ----------
    def load_current_profile(self):
        """Загружает настройки текущего профиля в интерфейс и применяет их к боту."""
        profile_name = self.current_profile_name.get()
        if not profile_name or profile_name not in self.bot.cycle_profiles:
            if self.bot.cycle_profiles:
                profile_name = next(iter(self.bot.cycle_profiles))
                self.current_profile_name.set(profile_name)
            else:
                # Создаём профиль по умолчанию
                self.bot.cycle_profiles["default"] = {
                    "enabled": False,
                    "timeout": 5.0,
                    "groups": []
                }
                profile_name = "default"
                self.current_profile_name.set("default")

        profile = self.bot.cycle_profiles.get(profile_name, {})
        self.cycle_enabled_var.set(profile.get("enabled", False))
        self.cycle_timeout_var.set(profile.get("timeout", 5.0))

        # Очищаем и заполняем список групп
        self.cycle_listbox.delete(0, tk.END)
        groups = profile.get("groups", [])
        for group in groups:
            self.cycle_listbox.insert(tk.END, group)

        # Синхронизируем с ботом
        self.bot.cycle_mode = profile.get("enabled", False)
        self.bot.cycle_timeout = profile.get("timeout", 5.0)
        self.bot.cycle_groups = groups
        self.bot.current_cycle_profile = profile_name
        self.bot.save_config()
        logger.info(f"Загружен профиль: {profile_name}, групп: {len(groups)}")

    def on_profile_selected(self, event=None):
        """Обработчик выбора профиля из комбобокса."""
        self.load_current_profile()

    def update_profile_combo(self):
        """Обновить список профилей в комбобоксе."""
        self.profile_combo['values'] = list(self.bot.cycle_profiles.keys())
        self.profile_combo.set(self.bot.current_cycle_profile)

    def new_profile(self):
        """Создать новый профиль."""
        name = simpledialog.askstring("Новый профиль", "Введите имя профиля:", parent=self.dialog)
        if not name or name.strip() == "":
            return
        name = name.strip()
        if name in self.bot.cycle_profiles:
            messagebox.showerror("Ошибка", "Профиль с таким именем уже существует.")
            return
        # Копируем настройки текущего профиля как основу
        current = self.bot.cycle_profiles.get(self.current_profile_name.get(), {})
        self.bot.cycle_profiles[name] = {
            "enabled": current.get("enabled", False),
            "timeout": current.get("timeout", 5.0),
            "groups": current.get("groups", [])
        }
        self.bot.current_cycle_profile = name
        self.current_profile_name.set(name)
        self.bot.save_config()
        self.update_profile_combo()
        self.load_current_profile()

    def delete_profile(self):
        """Удалить текущий профиль."""
        if len(self.bot.cycle_profiles) <= 1:
            messagebox.showwarning("Внимание", "Нельзя удалить единственный профиль.")
            return
        name = self.current_profile_name.get()
        if not messagebox.askyesno("Подтверждение", f"Удалить профиль '{name}'?"):
            return
        del self.bot.cycle_profiles[name]
        self.bot.current_cycle_profile = next(iter(self.bot.cycle_profiles))
        self.current_profile_name.set(self.bot.current_cycle_profile)
        self.bot.save_config()
        self.update_profile_combo()
        self.load_current_profile()

    def rename_profile(self):
        """Переименовать текущий профиль."""
        old_name = self.current_profile_name.get()
        new_name = simpledialog.askstring("Переименовать", "Новое имя профиля:", parent=self.dialog,
                                          initialvalue=old_name)
        if not new_name or new_name.strip() == "" or new_name == old_name:
            return
        new_name = new_name.strip()
        if new_name in self.bot.cycle_profiles:
            messagebox.showerror("Ошибка", "Профиль с таким именем уже существует.")
            return
        self.bot.cycle_profiles[new_name] = self.bot.cycle_profiles.pop(old_name)
        self.bot.current_cycle_profile = new_name
        self.current_profile_name.set(new_name)
        self.bot.save_config()
        self.update_profile_combo()

    # ---------- Вспомогательные методы для порядка ----------
    def move_up(self):
        sel = self.order_listbox.curselection()
        if sel and sel[0] > 0:
            idx = sel[0]
            item = self.order_listbox.get(idx)
            self.order_listbox.delete(idx)
            self.order_listbox.insert(idx-1, item)
            self.order_listbox.selection_set(idx-1)

    def move_down(self):
        sel = self.order_listbox.curselection()
        if sel and sel[0] < self.order_listbox.size()-1:
            idx = sel[0]
            item = self.order_listbox.get(idx)
            self.order_listbox.delete(idx)
            self.order_listbox.insert(idx+1, item)
            self.order_listbox.selection_set(idx+1)

    def move_cycle_up(self):
        sel = self.cycle_listbox.curselection()
        if sel and sel[0] > 0:
            idx = sel[0]
            item = self.cycle_listbox.get(idx)
            self.cycle_listbox.delete(idx)
            self.cycle_listbox.insert(idx-1, item)
            self.cycle_listbox.selection_set(idx-1)

    def move_cycle_down(self):
        sel = self.cycle_listbox.curselection()
        if sel and sel[0] < self.cycle_listbox.size()-1:
            idx = sel[0]
            item = self.cycle_listbox.get(idx)
            self.cycle_listbox.delete(idx)
            self.cycle_listbox.insert(idx+1, item)
            self.cycle_listbox.selection_set(idx+1)

    # ---------- Drag & Drop для списка цикла ----------
    def on_drag_start(self, event):
        index = self.cycle_listbox.nearest(event.y)
        if index >= 0:
            self.drag_data["item"] = self.cycle_listbox.get(index)
            self.drag_data["index"] = index
            self.drag_data["y"] = event.y
            self.drag_data["selection"] = self.cycle_listbox.curselection()
            self.cycle_listbox.selection_clear(0, tk.END)
            self.cycle_listbox.selection_set(index)
            self.cycle_listbox.activate(index)

    def on_drag_motion(self, event):
        if self.drag_data["item"] is None:
            return
        index = self.cycle_listbox.nearest(event.y)
        if index < 0:
            self.cycle_listbox.selection_clear(0, tk.END)
            self.cycle_listbox.selection_set(self.drag_data["index"])
            return
        self.cycle_listbox.selection_clear(0, tk.END)
        self.cycle_listbox.selection_set(index)

    def on_drag_drop(self, event):
        if self.drag_data["item"] is None:
            return
        target_index = self.cycle_listbox.nearest(event.y)
        if target_index < 0:
            self.cycle_listbox.selection_clear(0, tk.END)
            if self.drag_data["selection"]:
                self.cycle_listbox.selection_set(self.drag_data["selection"][0])
            self.drag_data["item"] = None
            return

        all_items = list(self.cycle_listbox.get(0, tk.END))
        src_index = self.drag_data["index"]

        if src_index == target_index:
            self.cycle_listbox.selection_clear(0, tk.END)
            self.cycle_listbox.selection_set(src_index)
            self.drag_data["item"] = None
            return

        moved_item = all_items.pop(src_index)
        if target_index > src_index:
            target_index -= 1
        all_items.insert(target_index, moved_item)

        self.cycle_listbox.delete(0, tk.END)
        for item in all_items:
            self.cycle_listbox.insert(tk.END, item)

        self.cycle_listbox.selection_clear(0, tk.END)
        self.cycle_listbox.selection_set(target_index)
        self.cycle_listbox.activate(target_index)

        # Сохраняем изменения в профиле
        profile_name = self.current_profile_name.get()
        profile = self.bot.cycle_profiles.get(profile_name, {})
        profile["groups"] = all_items
        self.bot.cycle_profiles[profile_name] = profile
        self.bot.cycle_groups = all_items
        self.bot.save_config()

        self.drag_data["item"] = None

    def add_to_cycle(self):
        groups = sorted(list(self.bot.groups.keys()), key=str.lower)
        if not groups:
            return
        dialog = tk.Toplevel(self.dialog)
        dialog.title("Добавить группу")
        dialog.geometry("400x150")
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.focus_set()
        dialog.lift()
        x = (dialog.winfo_screenwidth() - 400) // 2
        y = (dialog.winfo_screenheight() - 150) // 2
        dialog.geometry(f"400x150+{x}+{y}")

        tk.Label(dialog, text="Выберите группу:").pack(pady=10)

        var = tk.StringVar()
        combo = ttk.Combobox(dialog, textvariable=var, values=groups, state='readonly', width=30)
        combo.pack(pady=5)
        if groups:
            combo.current(0)

        def do_add():
            group = var.get()
            if group:
                if group in self.cycle_listbox.get(0, tk.END):
                    dialog.destroy()
                    return
                self.cycle_listbox.insert(tk.END, group)
                profile_name = self.current_profile_name.get()
                profile = self.bot.cycle_profiles.get(profile_name, {})
                profile["groups"] = list(self.cycle_listbox.get(0, tk.END))
                self.bot.cycle_profiles[profile_name] = profile
                self.bot.cycle_groups = profile["groups"]
                self.bot.save_config()
            dialog.destroy()

        tk.Button(dialog, text="Добавить", command=do_add).pack(pady=5)
        dialog.bind('<Return>', lambda e: do_add())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def remove_from_cycle(self):
        sel = self.cycle_listbox.curselection()
        if sel:
            self.cycle_listbox.delete(sel[0])
            profile_name = self.current_profile_name.get()
            profile = self.bot.cycle_profiles.get(profile_name, {})
            profile["groups"] = list(self.cycle_listbox.get(0, tk.END))
            self.bot.cycle_profiles[profile_name] = profile
            self.bot.cycle_groups = profile["groups"]
            self.bot.save_config()

    # ---------- Сохранение автовключения ----------
    def save_schedule(self):
        new_schedules = {}
        for group, (auto_var, on_hour_var, on_min_var, off_hour_var, off_min_var, duration_var, type_var) in self.vars.items():
            auto = auto_var.get()
            on_h = on_hour_var.get().strip()
            on_m = on_min_var.get().strip()
            off_h = off_hour_var.get().strip()
            off_m = off_min_var.get().strip()
            duration = duration_var.get().strip()

            on_valid, on_str = validate_hour_min(on_h, on_m)
            off_valid, off_str = validate_hour_min(off_h, off_m)

            if not on_valid:
                self.bot._show_notification('error', 'error', message=f"Неверное время включения для группы {group}.")
                return
            if not off_valid:
                self.bot._show_notification('error', 'error', message=f"Неверное время выключения для группы {group}.")
                return

            dur_int = 0
            if duration:
                try:
                    dur_int = int(duration)
                except:
                    self.bot._show_notification('error', 'error', message=f"Неверная длительность для группы {group}.")
                    return

            if auto:
                if dur_int > 0:
                    new_schedules[group] = {
                        'auto': True,
                        'type': 'interval',
                        'on_time': on_str if on_str else None,
                        'duration': dur_int
                    }
                else:
                    new_schedules[group] = {
                        'auto': True,
                        'type': 'time',
                        'on_time': on_str if on_str else None,
                        'off_time': off_str if off_str else None
                    }
            else:
                new_schedules[group] = {'auto': False}

        self.bot.group_schedules = new_schedules
        self.bot.save_config()
        self.bot._show_notification('success', 'settings_saved')

    # ---------- Сохранение порядка и задержек ----------
    def save_order(self, delay_frames):
        new_order = self.order_listbox.get(0, tk.END)
        for idx, group in enumerate(new_order):
            if group not in self.bot.group_execution:
                self.bot.group_execution[group] = {}
            self.bot.group_execution[group]['order'] = idx
        for group, (between_var, after_var) in delay_frames.items():
            if group not in self.bot.group_execution:
                self.bot.group_execution[group] = {}
            self.bot.group_execution[group]['delay_between'] = between_var.get()
            self.bot.group_execution[group]['delay_after'] = after_var.get()
        self.bot.save_config()
        self.bot._show_notification('success', 'settings_saved')

    # ---------- Сохранение цикла (в текущий профиль) ----------
    def save_cycle(self):
        profile_name = self.current_profile_name.get()
        profile = self.bot.cycle_profiles.get(profile_name, {})
        profile["enabled"] = self.cycle_enabled_var.get()
        profile["timeout"] = self.cycle_timeout_var.get()
        profile["groups"] = list(self.cycle_listbox.get(0, tk.END))
        self.bot.cycle_profiles[profile_name] = profile
        self.bot.current_cycle_profile = profile_name
        self.bot.cycle_mode = profile["enabled"]
        self.bot.cycle_timeout = profile["timeout"]
        self.bot.cycle_groups = profile["groups"]
        self.bot.save_config()
        self.bot._show_notification('success', 'settings_saved')

    # ---------- Переименование группы ----------
    def rename_selected_group(self):
        groups = list(self.vars.keys())
        if not groups:
            return
        old_name = simpledialog.askstring("Переименование", "Введите текущее имя группы:", parent=self.dialog)
        if not old_name or old_name.strip() == "":
            return
        old_name = old_name.strip()
        if old_name not in self.bot.groups:
            self.bot._show_notification('error', 'error', message="Группа не найдена.")
            return
        new_name = simpledialog.askstring("Переименование", f"Новое имя для группы '{old_name}':", parent=self.dialog)
        if not new_name or new_name.strip() == "":
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if new_name in self.bot.groups:
            self.bot._show_notification('error', 'error', message="Группа с таким именем уже существует.")
            return

        self.bot.groups[new_name] = self.bot.groups.pop(old_name)
        if old_name in self.bot.group_schedules:
            self.bot.group_schedules[new_name] = self.bot.group_schedules.pop(old_name)
        if old_name in self.bot.group_execution:
            self.bot.group_execution[new_name] = self.bot.group_execution.pop(old_name)
        for profile in self.bot.cycle_profiles.values():
            if old_name in profile.get("groups", []):
                idx = profile["groups"].index(old_name)
                profile["groups"][idx] = new_name

        for img in self.bot.search_images:
            if img.get("group") == old_name:
                img["group"] = new_name

        self.bot.save_config()
        if self.bot.root:
            self.bot.root.event_generate("<<GroupsChanged>>")
        self.dialog.destroy()
        self.show()
        self.bot._show_notification('success', 'settings_saved')

    def rename_group(self, old_name):
        self.rename_selected_group()

    # ---------- Удаление группы ----------
    def delete_group(self):
        groups = list(self.vars.keys())
        if not groups:
            return

        choice_dialog = tk.Toplevel(self.dialog)
        choice_dialog.title("Удаление группы")
        choice_dialog.geometry("300x150")
        choice_dialog.attributes("-topmost", True)
        choice_dialog.grab_set()
        choice_dialog.focus_set()
        choice_dialog.lift()
        choice_dialog.update_idletasks()
        x = (choice_dialog.winfo_screenwidth() - 300) // 2
        y = (choice_dialog.winfo_screenheight() - 150) // 2
        choice_dialog.geometry(f"300x150+{x}+{y}")

        tk.Label(choice_dialog, text="Выберите группу для удаления:", font=("Arial", 10)).pack(pady=10)

        group_var = tk.StringVar()
        group_combo = ttk.Combobox(choice_dialog, textvariable=group_var, values=groups, state='readonly', width=20)
        group_combo.pack(pady=5)
        if groups:
            group_combo.current(0)

        def do_delete():
            group = group_var.get()
            if not group:
                return

            for img in self.bot.search_images:
                if img.get("group") == group:
                    old_path = Path(img["path"])
                    new_path = IMG_DIR / old_path.name
                    if new_path.exists():
                        base = new_path.stem
                        ext = new_path.suffix
                        counter = 1
                        while new_path.exists():
                            new_path = IMG_DIR / f"{base}_{counter}{ext}"
                            counter += 1
                    try:
                        old_path.rename(new_path)
                        img["path"] = str(new_path)
                        img["group"] = None
                    except Exception as e:
                        logger.error(f"Ошибка перемещения файла при удалении группы: {e}")

            safe_name = self.bot._sanitize_filename(self.bot._transliterate(group))
            group_folder = IMG_DIR / safe_name
            if group_folder.exists():
                try:
                    group_folder.rmdir()
                except OSError:
                    pass

            del self.bot.groups[group]
            if group in self.bot.group_schedules:
                del self.bot.group_schedules[group]
            if group in self.bot.group_execution:
                del self.bot.group_execution[group]
            for profile in self.bot.cycle_profiles.values():
                if group in profile.get("groups", []):
                    profile["groups"].remove(group)

            self.bot.save_config()
            if self.bot.root:
                self.bot.root.event_generate("<<GroupsChanged>>")
            choice_dialog.destroy()
            self.dialog.destroy()
            self.show()
            self.bot._show_notification('success', 'settings_saved')

        btn_frame = tk.Frame(choice_dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Удалить", command=do_delete, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Отмена", command=choice_dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)

        choice_dialog.bind('<Escape>', lambda e: choice_dialog.destroy())
        choice_dialog.bind('<Return>', lambda e: do_delete())


def build_ui(root, bot):
    """Строит пользовательский интерфейс."""
    for widget in root.winfo_children():
        widget.destroy()

    root.title(f"{bot.tr('window_title')} v{APP_VERSION}")
    root.configure(bg='white')
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TFrame', background='white')
    style.configure('TLabel', background='white')
    style.configure('TLabelframe', background='white')
    style.configure('TLabelframe.Label', background='white')

    title_frame = ttk.Frame(root)
    title_frame.pack(fill=tk.X, padx=5, pady=5)

    ttk.Label(title_frame, text=f"{bot.tr('window_title')} v{APP_VERSION} by BuZ",
              font=("Arial", 14, "bold")).pack(side=tk.LEFT)

    lang_frame = ttk.Frame(title_frame)
    lang_frame.pack(side=tk.RIGHT)

    ttk.Label(lang_frame, text=bot.tr('language')).pack(side=tk.LEFT, padx=2)
    lang_var = tk.StringVar(value=bot.lang)
    lang_combo = ttk.Combobox(lang_frame, textvariable=lang_var, values=['ru', 'en'], state='readonly', width=5)
    lang_combo.pack(side=tk.LEFT)
    lang_combo.bind('<<ComboboxSelected>>', lambda e: change_language(root, bot, lang_var.get()))

    status_frame = ttk.LabelFrame(root, text=bot.tr('status'), padding=5)
    status_frame.pack(fill=tk.X, padx=5, pady=2)

    status_grid = ttk.Frame(status_frame)
    status_grid.pack()

    ttk.Label(status_grid, text=bot.tr('status')+':').grid(row=0, column=0, padx=2)
    status_label = ttk.Label(status_grid, text=bot.tr('state_stopped'), foreground="red")
    status_label.grid(row=0, column=1, padx=2)

    ttk.Label(status_grid, text=bot.tr('areas_count')).grid(row=0, column=2, padx=(10,2))
    count_label = ttk.Label(status_grid, text=str(len(bot.search_images)))
    count_label.grid(row=0, column=3, padx=2)

    ttk.Label(status_grid, text=bot.tr('clicks')).grid(row=0, column=4, padx=(10,2))
    clicks_label = ttk.Label(status_grid, text="0")
    clicks_label.grid(row=0, column=5, padx=2)

    ttk.Label(status_grid, text=bot.tr('time')).grid(row=0, column=6, padx=(10,2))
    time_label = ttk.Label(status_grid, text="0 сек")
    time_label.grid(row=0, column=7, padx=2)

    monitor = SystemMonitor(status_frame, root)

    def toggle_pause_from_ui():
        if bot.is_running:
            bot.toggle_pause()
            update_status()

    def run_test_search_from_ui():
        bot.start_test_search()

    def update_status():
        if root.status_after_id:
            root.after_cancel(root.status_after_id)
        if bot.is_running:
            if bot.state == BotState.PAUSED:
                status_label.config(text=bot.tr('state_paused'), foreground="#b8860b")
            else:
                status_label.config(text=bot.tr('state_running'), foreground="green")
            runtime = compute_runtime_seconds(
                bot.start_time,
                bot.total_paused_duration,
                bot.pause_started_at,
                bot.state,
                time.time(),
            )
            runtime_unit = "сек" if bot.lang == 'ru' else "sec"
            time_label.config(text=f"{runtime:.0f} {runtime_unit}")
            clicks_label.config(text=str(bot.click_count))
            pause_button.config(
                text=bot.tr('resume') if bot.is_paused else bot.tr('pause'),
                state=tk.NORMAL
            )
            normal_start_button.config(state=tk.DISABLED)
            if hasattr(root, 'routine_start_button'):
                root.routine_start_button.config(state=tk.DISABLED)
        else:
            status_label.config(text=bot.tr('state_stopped'), foreground="red")
            pause_button.config(text=bot.tr('pause'), state=tk.DISABLED)
            normal_start_button.config(state=tk.NORMAL)
            if hasattr(root, 'routine_start_button'):
                root.routine_start_button.config(state=tk.NORMAL)
        if hasattr(root, 'routine_marches_var'):
            root.routine_marches_var.set(
                bot.tr(
                    'routine_marches',
                    active=bot.get_active_marches(),
                    maximum=bot.routine_max_marches,
                )
            )
        count_label.config(text=str(len(bot.search_images)))
        root.status_after_id = root.after(1000, update_status)

    control_frame = ttk.LabelFrame(root, text=bot.tr('control'), padding=5)
    control_frame.pack(fill=tk.X, padx=5, pady=2)

    center_control = ttk.Frame(control_frame)
    center_control.pack(anchor='center')

    tk.Button(center_control, text=bot.tr('select_area'),
              command=lambda: bot.select_area(root), width=18).pack(side=tk.LEFT, padx=2)
    tk.Button(center_control, text=bot.tr('manage_areas'),
              command=lambda: AreaManager(root, bot).show(), width=20).pack(side=tk.LEFT, padx=2)
    tk.Button(center_control, text=bot.tr('group_schedule'),
              command=lambda: GroupScheduleDialog(root, bot).show(), width=20).pack(side=tk.LEFT, padx=2)
    normal_start_button = tk.Button(center_control, text=bot.tr('start'),
              command=lambda: [bot.start_normal(), update_status()], width=8)
    normal_start_button.pack(side=tk.LEFT, padx=2)
    pause_button = tk.Button(center_control, text=bot.tr('pause'),
              command=toggle_pause_from_ui, width=10, state=tk.DISABLED)
    pause_button.pack(side=tk.LEFT, padx=2)
    tk.Button(center_control, text=bot.tr('stop'),
              command=lambda: [bot.stop(), update_status()], width=8).pack(side=tk.LEFT, padx=2)
    tk.Button(center_control, text=bot.tr('test_search'),
              command=run_test_search_from_ui, width=12).pack(side=tk.LEFT, padx=2)

    root.status_after_id = None
    update_status()

    minimize_var = tk.BooleanVar(value=bot.minimize_on_start)
    def update_minimize_on_start():
        bot.minimize_on_start = minimize_var.get()
        bot.save_config()
    minimize_cb = ttk.Checkbutton(center_control, text=bot.tr('minimize_on_start'), variable=minimize_var,
                                   command=update_minimize_on_start)
    minimize_cb.pack(side=tk.LEFT, padx=5)

    status_line_frame = ttk.LabelFrame(root, text=bot.tr('status_line'), padding=5)
    status_line_frame.pack(fill=tk.X, padx=5, pady=2)
    status_line_var = tk.StringVar(value=bot.status_message or bot.get_default_status_message())
    root.status_line_var = status_line_var
    status_line_label = tk.Label(
        status_line_frame,
        textvariable=status_line_var,
        anchor='w',
        justify='left',
        wraplength=920,
        bg='#f4f1c9',
        relief='sunken',
        padx=8,
        pady=8,
        font=("Arial", 10),
    )
    status_line_label.pack(fill=tk.X)
    bot.attach_status_var(status_line_var)

    routine_frame = ttk.LabelFrame(root, text=bot.tr('routine_tasks'), padding=6)
    routine_frame.pack(fill=tk.X, padx=5, pady=2)
    routine_top = ttk.Frame(routine_frame)
    routine_top.pack(fill=tk.X)
    ttk.Label(routine_top, text=bot.tr('routine_help'), foreground="#555555").pack(side=tk.LEFT, padx=3)
    routine_marches_var = tk.StringVar()
    root.routine_marches_var = routine_marches_var
    ttk.Label(
        routine_top,
        textvariable=routine_marches_var,
        font=("Arial", 10, "bold"),
        foreground="#0a5c36",
    ).pack(side=tk.RIGHT, padx=6)

    routine_cards = ttk.Frame(routine_frame)
    routine_cards.pack(fill=tk.X, pady=(5, 2))
    root.routine_cards = routine_cards

    def rebuild_routine_cards():
        for widget in routine_cards.winfo_children():
            widget.destroy()
        num_columns = 5
        for column in range(num_columns):
            routine_cards.grid_columnconfigure(column, weight=1, uniform='routine')
        for index, task in enumerate(bot.routine_tasks):
            card = ttk.Frame(routine_cards, padding=3, relief='groove')
            card.grid(
                row=index // num_columns,
                column=index % num_columns,
                sticky='nsew',
                padx=2,
                pady=2,
            )
            enabled_var = tk.BooleanVar(value=task.get("enabled", True))
            ttk.Checkbutton(
                card,
                text=bot.get_routine_task_name(task),
                variable=enabled_var,
                command=lambda task_id=task["id"], var=enabled_var: bot.set_routine_enabled(task_id, var.get()),
            ).pack(anchor='w')
            template_count = len(bot.get_routine_templates(task))
            ttk.Label(
                card,
                text=bot.tr('routine_templates', count=template_count),
                foreground="#666666",
                font=("Arial", 8),
            ).pack(anchor='w', padx=20)

    root.refresh_routine_summary = rebuild_routine_cards
    rebuild_routine_cards()

    routine_buttons = ttk.Frame(routine_frame)
    routine_buttons.pack(fill=tk.X, pady=(3, 0))
    routine_start_button = tk.Button(
        routine_buttons,
        text=bot.tr('routine_start'),
        command=lambda: [bot.start_routines(), update_status()],
        width=18,
        bg="#2e8b57",
        fg="white",
        activebackground="#246f46",
        activeforeground="white",
        font=("Arial", 10, "bold"),
    )
    routine_start_button.pack(side=tk.LEFT, padx=3)
    root.routine_start_button = routine_start_button
    ttk.Button(
        routine_buttons,
        text=bot.tr('routine_settings'),
        command=lambda: RoutineTasksDialog(root, bot).show(),
    ).pack(side=tk.LEFT, padx=3)
    ttk.Button(
        routine_buttons,
        text=bot.tr('routine_clear_selection'),
        command=lambda: [bot.clear_routine_selection(), rebuild_routine_cards()],
    ).pack(side=tk.LEFT, padx=3)
    ttk.Button(
        routine_buttons,
        text=bot.tr('routine_reset_marches'),
        command=bot.reset_routine_marches,
    ).pack(side=tk.LEFT, padx=3)
    routine_marches_var.set(
        bot.tr(
            'routine_marches',
            active=bot.get_active_marches(),
            maximum=bot.routine_max_marches,
        )
    )

    settings_frame = ttk.LabelFrame(root, text=bot.tr('settings'), padding=5)
    settings_frame.pack(fill=tk.X, padx=5, pady=2)

    settings_row1 = ttk.Frame(settings_frame)
    settings_row1.pack(fill=tk.X, pady=2)

    work_subframe = ttk.LabelFrame(settings_row1, text=bot.tr('work_area'), padding=5)
    work_subframe.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    work_inner = ttk.Frame(work_subframe)
    work_inner.pack()
    ttk.Label(work_inner, text=bot.tr('work_area')+':').pack(side=tk.LEFT, padx=2)
    work_area_var = tk.StringVar(value=bot.work_area_type)
    area_choices = [('fullscreen', bot.tr('fullscreen'))]
    for i in range(len(bot.monitors)):
        area_choices.append((f'monitor{i+1}', f"{bot.tr('monitor')} {i+1}"))
    area_choices.append(('selected', bot.tr('selected_region')))
    work_area_combo = ttk.Combobox(work_inner, textvariable=work_area_var, width=15, state='readonly')
    work_area_combo['values'] = [text for code, text in area_choices]
    for index, (code, text) in enumerate(area_choices):
        if code == bot.work_area_type:
            work_area_combo.current(index)
            work_area_var.set(text)
            break
    else:
        work_area_combo.current(0)
        work_area_var.set(area_choices[0][1])
    work_area_combo.pack(side=tk.LEFT, padx=2)
    def on_area_select(event):
        idx = work_area_combo.current()
        if idx >= 0:
            code = area_choices[idx][0]
            bot.set_work_area(code)
    work_area_combo.bind('<<ComboboxSelected>>', on_area_select)
    select_work_btn = tk.Button(work_inner, text=bot.tr('select'), command=lambda: bot.select_area(root, for_work_area=True))
    select_work_btn.pack(side=tk.LEFT, padx=2)
    root.work_area_var = work_area_var
    root.work_area_combo = work_area_combo
    root.work_area_choices = area_choices

    scale_subframe = ttk.LabelFrame(settings_row1, text=bot.tr('scaling'), padding=5)
    scale_subframe.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    scale_inner = ttk.Frame(scale_subframe)
    scale_inner.pack()
    scale_enabled_var = tk.BooleanVar(value=bot.scale_enabled)
    scale_cb = ttk.Checkbutton(scale_inner, text=bot.tr('scaling_enable'), variable=scale_enabled_var,
                               command=lambda: update_scaling())
    scale_cb.pack(side=tk.LEFT, padx=2)
    ttk.Label(scale_inner, text=bot.tr('scaling_range')).pack(side=tk.LEFT, padx=2)
    scale_min_var = tk.DoubleVar(value=bot.scale_min)
    scale_max_var = tk.DoubleVar(value=bot.scale_max)
    scale_min_spin = ttk.Spinbox(scale_inner, from_=0.5, to=1.5, increment=0.05, width=5,
                                  textvariable=scale_min_var)
    scale_min_spin.pack(side=tk.LEFT, padx=1)
    ttk.Label(scale_inner, text="-").pack(side=tk.LEFT)
    scale_max_spin = ttk.Spinbox(scale_inner, from_=0.5, to=1.5, increment=0.05, width=5,
                                  textvariable=scale_max_var)
    scale_max_spin.pack(side=tk.LEFT, padx=1)
    def update_scaling():
        enabled = scale_enabled_var.get()
        min_val = scale_min_var.get()
        max_val = scale_max_var.get()
        if min_val > max_val:
            min_val, max_val = max_val, min_val
        bot.set_scaling(enabled, min_val, max_val)
    scale_apply = tk.Button(scale_inner, text=bot.tr('apply'), command=update_scaling)
    scale_apply.pack(side=tk.LEFT, padx=2)

    backend_row = ttk.Frame(settings_frame)
    backend_row.pack(fill=tk.X, pady=2)
    backend_subframe = ttk.LabelFrame(backend_row, text=bot.tr('input_backend'), padding=5)
    backend_subframe.pack(fill=tk.X, padx=5, expand=True)
    backend_inner = ttk.Frame(backend_subframe)
    backend_inner.pack()
    backend_choices = [
        ('screen', bot.tr('input_screen')),
        ('adb', bot.tr('input_adb')),
    ]
    backend_var = tk.StringVar()
    backend_combo = ttk.Combobox(
        backend_inner,
        textvariable=backend_var,
        values=[label for _code, label in backend_choices],
        state='readonly',
        width=18,
    )
    selected_backend_index = 1 if bot.input_backend == 'adb' else 0
    backend_combo.current(selected_backend_index)
    backend_combo.pack(side=tk.LEFT, padx=3)
    ttk.Label(backend_inner, text=bot.tr('adb_serial')).pack(side=tk.LEFT, padx=(8, 2))
    adb_serial_var = tk.StringVar(value=bot.adb_serial)
    ttk.Entry(backend_inner, textvariable=adb_serial_var, width=18).pack(side=tk.LEFT, padx=2)
    backend_status_var = tk.StringVar(
        value=bot.tr('adb_connected' if bot.input_backend == 'adb' else 'ready', serial=bot.adb_serial)
    )

    def apply_input_backend(check_connection=False):
        selected_index = backend_combo.current()
        backend_code = backend_choices[selected_index if selected_index >= 0 else 0][0]
        bot.set_input_backend(backend_code, serial=adb_serial_var.get())
        if backend_code == 'adb' and check_connection:
            connected = bot.check_runtime_environment(notify=True)
            backend_status_var.set(bot.get_environment_summary())
        else:
            backend_status_var.set(bot.tr('input_screen') if backend_code == 'screen' else bot.adb_serial)

    ttk.Button(
        backend_inner,
        text=bot.tr('apply'),
        command=lambda: apply_input_backend(False),
    ).pack(side=tk.LEFT, padx=3)
    ttk.Button(
        backend_inner,
        text=bot.tr('adb_check'),
        command=lambda: apply_input_backend(True),
    ).pack(side=tk.LEFT, padx=3)
    ttk.Label(backend_inner, textvariable=backend_status_var, foreground='#555555').pack(side=tk.LEFT, padx=8)

    settings_row2 = ttk.Frame(settings_frame)
    settings_row2.pack(fill=tk.X, pady=2)

    interval_subframe = ttk.LabelFrame(settings_row2, text=bot.tr('intervals'), padding=5)
    interval_subframe.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    interval_inner = ttk.Frame(interval_subframe)
    interval_inner.pack()
    ttk.Label(interval_inner, text=bot.tr('found')).pack(side=tk.LEFT, padx=2)
    found_var = tk.DoubleVar(value=bot.sleep_found)
    found_spin = ttk.Spinbox(interval_inner, from_=0.0, to=5.0, increment=0.05,
                             textvariable=found_var, width=5)
    found_spin.pack(side=tk.LEFT, padx=2)
    ttk.Label(interval_inner, text=bot.tr('not_found')).pack(side=tk.LEFT, padx=2)
    not_found_var = tk.DoubleVar(value=bot.sleep_not_found)
    not_found_spin = ttk.Spinbox(interval_inner, from_=0.0, to=2.0, increment=0.01,
                                  textvariable=not_found_var, width=5)
    not_found_spin.pack(side=tk.LEFT, padx=2)
    ttk.Button(interval_inner, text=bot.tr('apply'),
               command=lambda: bot.set_sleeps(found_var.get(), not_found_var.get())).pack(side=tk.LEFT, padx=2)

    anti_loop_var = tk.BooleanVar(value=bot.anti_loop_enabled)
    def toggle_anti_loop():
        bot.anti_loop_enabled = anti_loop_var.get()
        bot.save_config()
    anti_loop_cb = ttk.Checkbutton(interval_inner, text=bot.tr('anti_loop'),
                                   variable=anti_loop_var, command=toggle_anti_loop)
    anti_loop_cb.pack(side=tk.LEFT, padx=10)

    orb_var = tk.BooleanVar(value=bot.orb_enabled)
    def toggle_orb():
        bot.orb_enabled = orb_var.get()
        bot.save_config()
    orb_cb = ttk.Checkbutton(interval_inner, text=bot.tr('orb_check'),
                             variable=orb_var, command=toggle_orb)
    orb_cb.pack(side=tk.LEFT, padx=10)

    diagnostic_var = tk.BooleanVar(value=bot.diagnostic_enabled)
    def toggle_diagnostics():
        bot.diagnostic_enabled = diagnostic_var.get()
        bot.save_config()
        bot.sync_status_message()
    diagnostic_cb = ttk.Checkbutton(
        interval_inner,
        text=bot.tr('diagnostic_mode'),
        variable=diagnostic_var,
        command=toggle_diagnostics,
    )
    diagnostic_cb.pack(side=tk.LEFT, padx=10)

    # Группы (стабильные 5 колонок с прокруткой)
    groups_frame = ttk.LabelFrame(root, text=bot.tr('groups'), padding=5)
    groups_frame.pack(fill=tk.X, padx=5, pady=2)

    groups_canvas = tk.Canvas(groups_frame, highlightthickness=0, height=150, bg='white')
    groups_scrollbar = ttk.Scrollbar(groups_frame, orient=tk.VERTICAL, command=groups_canvas.yview)
    groups_inner = ttk.Frame(groups_canvas)

    groups_inner.bind(
        "<Configure>",
        lambda e: groups_canvas.configure(scrollregion=groups_canvas.bbox("all"))
    )

    groups_canvas.create_window((0, 0), window=groups_inner, anchor="nw")
    groups_canvas.configure(yscrollcommand=groups_scrollbar.set)

    groups_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    groups_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def on_group_mousewheel(event):
        groups_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    groups_canvas.bind("<MouseWheel>", on_group_mousewheel)
    groups_inner.bind("<MouseWheel>", on_group_mousewheel)

    root.groups_inner = groups_inner
    root.groups_num_cols = 5

    def refresh_groups_panel():
        for widget in groups_inner.winfo_children():
            widget.destroy()
        groups = sorted(bot.groups.items(), key=lambda x: x[0].lower())
        num_cols = getattr(root, 'groups_num_cols', 5)
        for col in range(num_cols):
            groups_inner.grid_columnconfigure(col, weight=1, uniform='groups')
        for i, (gname, enabled) in enumerate(groups):
            row = i // num_cols
            col = i % num_cols
            var = tk.BooleanVar(value=enabled)
            cb = ttk.Checkbutton(groups_inner, text=gname, variable=var,
                                 command=lambda name=gname, v=var: toggle_group(name, v))
            cb.grid(row=row, column=col, sticky='w', padx=5, pady=2)
        if not groups:
            ttk.Label(groups_inner, text=bot.tr('no_groups')).grid(row=0, column=0, padx=5)

    def toggle_group(name, var):
        bot.groups[name] = var.get()
        bot.save_config()

    refresh_groups_panel()

    # Активные области
    active_frame = ttk.LabelFrame(root, text=bot.tr('active_areas'), padding=5)
    active_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    list_frame = ttk.Frame(active_frame)
    list_frame.pack(fill=tk.BOTH, expand=True)

    scrollbar = ttk.Scrollbar(list_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    active_list = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=4,
                             font=("Arial", 9), selectmode=tk.SINGLE)
    active_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scrollbar.config(command=active_list.yview)

    def on_mousewheel(event):
        active_list.yview_scroll(int(-1*(event.delta/120)), "units")
    active_list.bind("<MouseWheel>", on_mousewheel)

    button_frame = tk.Frame(active_frame)
    button_frame.pack(pady=2)

    def get_visible_active_images():
        visible = []
        for img in bot.search_images:
            active = img["enabled"]
            if img["group"] and img["group"] in bot.groups:
                active = active and bot.groups[img["group"]]
            if active:
                visible.append(img)
        return visible

    def edit_selected_area():
        selection = active_list.curselection()
        if not selection:
            return
        visible = get_visible_active_images()
        if selection[0] >= len(visible):
            return
        AreaManager(root, bot).show(highlight_uid=visible[selection[0]].get("uid"))

    def delete_selected_areas():
        selection = active_list.curselection()
        if not selection:
            return
        if messagebox.askyesno(bot.tr('warning'), bot.tr('delete_confirm', count=1)):
            visible = get_visible_active_images()
            if selection[0] >= len(visible):
                return
            img = visible[selection[0]]
            deleted = False
            try:
                if os.path.exists(img["path"]):
                    deleted = bool(bot._delete_image(img))
            except Exception as e:
                logger.error(f"Ошибка удаления файла {img['path']}: {e}")
            if img in bot.search_images:
                bot.search_images.remove(img)
                bot.save_config()
                if bot.root:
                    bot.root.event_generate("<<GroupsChanged>>")
                if deleted:
                    bot._show_notification('success', 'moved_to_trash', count=1)
                else:
                    bot._show_notification('warning', 'delete_failed', failed=1)

    edit_area_btn = tk.Button(button_frame, text=bot.tr('edit'), command=edit_selected_area)
    edit_area_btn.pack(side=tk.LEFT, padx=2)

    delete_area_btn = tk.Button(button_frame, text=bot.tr('delete'), command=delete_selected_areas)
    delete_area_btn.pack(side=tk.LEFT, padx=2)

    last_selection = None

    def update_active_list():
        nonlocal last_selection
        if root.active_after_id:
            root.after_cancel(root.active_after_id)
        # Сохраняем текущую позицию прокрутки
        try:
            yview = active_list.yview()
        except:
            yview = (0.0, 1.0)
        current_selection = active_list.curselection()
        active_list.delete(0, tk.END)
        for img in bot.search_images:
            active = img["enabled"]
            if img["group"] and img["group"] in bot.groups:
                active = active and bot.groups[img["group"]]
            if active:
                numbers = f" [{', '.join(img['numbers'])}]" if img.get("numbers") else ""
                group_info = f" ({img['group']})" if img.get("group") else ""
                active_list.insert(tk.END, f"{img['description']}{group_info}{numbers}")
        for idx in current_selection:
            if idx < active_list.size():
                active_list.selection_set(idx)
        # Восстанавливаем позицию прокрутки
        active_list.yview_moveto(yview[0])
        root.active_after_id = root.after(2000, update_active_list)

    root.active_after_id = None
    update_active_list()

    info_frame = ttk.LabelFrame(root, text=bot.tr('hotkeys'), padding=5)
    info_frame.pack(fill=tk.X, padx=5, pady=2)

    ttk.Label(info_frame, text=bot.tr('hotkeys_text'), font=("Arial", 8), justify='center').pack()


def change_language(root, bot, new_lang):
    if new_lang == bot.lang:
        return
    if hasattr(root, 'status_after_id') and root.status_after_id:
        root.after_cancel(root.status_after_id)
        root.status_after_id = None
    if hasattr(root, 'active_after_id') and root.active_after_id:
        root.after_cancel(root.active_after_id)
        root.active_after_id = None
    if hasattr(root, 'monitor_after_id') and root.monitor_after_id:
        root.after_cancel(root.monitor_after_id)
        root.monitor_after_id = None
    bot.lang = new_lang
    bot.save_config()
    build_compact_ui(root, bot)


def on_closing(root, bot):
    if bot.is_running or bot.multi_emulator_workers:
        bot.stop_all_emulators()
    bot.stop_remote_control()
    bot.stop_schedule_thread()
    root.destroy()


def should_autostart_routines(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--autostart" for arg in args)


def should_start_fresh_pass(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--fresh-pass" for arg in args)


def should_autostart_merchant_only(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--merchant-only" for arg in args)


def should_autostart_login_only(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--login-only" for arg in args)


def should_autostart_fence_only(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--fence-only" for arg in args)


def should_autostart_processing_only(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--processing-only" for arg in args)


def should_autostart_boost_only(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--boost-only" for arg in args)


def should_autostart_all_emulators(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--autostart-all" for arg in args)


def should_run_multi_worker(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return any(str(arg).strip().lower() == "--worker" for arg in args)


def should_run_smoke_test(argv=None):
    args = sys.argv[1:] if argv is None else argv
    env_enabled = os.environ.get("BUZZBOT_SMOKE_TEST", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return env_enabled or any(str(arg).strip().lower() == "--smoke-test" for arg in args)


def validate_smoke_test_layout(app_dir=APP_DIR):
    app_dir = Path(app_dir)
    config_path = app_dir / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Portable config is missing: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    images = config.get("images", [])
    if not images:
        raise RuntimeError("Portable config contains no templates.")
    missing = []
    for image in images:
        configured = Path(str(image.get("path") or ""))
        resolved = configured if configured.is_absolute() else app_dir / configured
        if not resolved.is_file():
            missing.append(str(image.get("description") or configured))
    if missing:
        raise FileNotFoundError(
            f"Portable build is missing {len(missing)} templates: {', '.join(missing[:5])}"
        )
    return len(images)


def main():
    if should_run_smoke_test():
        template_count = validate_smoke_test_layout()
        logger.info(
            "Smoke test passed for BuZzbot %s: %s configured templates",
            APP_VERSION,
            template_count,
        )
        (APP_DIR / "smoke-test.ok").write_text(
            f"BuZzbot {APP_VERSION}: {template_count} templates\n",
            encoding="utf-8",
        )
        return
    enable_windows_high_dpi()
    root = tk.Tk()
    is_multi_worker = should_run_multi_worker()
    if is_multi_worker:
        root.withdraw()
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except tk.TclError:
        pass
    install_exception_logging(logger, root)
    logger.info(
        "Запуск BuZzbot %s | frozen=%s | app_dir=%s | runtime_dir=%s | worker=%s",
        APP_VERSION,
        bool(getattr(sys, 'frozen', False)),
        APP_DIR,
        RUNTIME_DIR,
        is_multi_worker,
    )
    root.geometry("1000x1000")
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 1000) // 2
    y = (root.winfo_screenheight() - 1000) // 2
    root.geometry(f"1000x1000+{x}+{y}")

    IMG_DIR.mkdir(parents=True, exist_ok=True)

    bot = AutoClicker(root)

    def hotkey_stop(event=None):
        if bot.is_running:
            bot.stop_hotkey_pressed = True
            bot.stop_all_emulators()
    root.bind('<Control-0>', hotkey_stop)

    def hotkey_pause(event=None):
        if bot.is_running:
            bot.toggle_pause()
    root.bind('<Control-p>', hotkey_pause)
    root.bind('<Control-P>', hotkey_pause)

    def refresh_groups_panel():
        if not hasattr(root, 'groups_inner'):
            return
        for widget in root.groups_inner.winfo_children():
            widget.destroy()
        groups = sorted(bot.groups.items(), key=lambda x: x[0].lower())
        num_cols = getattr(root, 'groups_num_cols', 5)
        for col in range(num_cols):
            root.groups_inner.grid_columnconfigure(col, weight=1, uniform='groups')
        for i, (gname, enabled) in enumerate(groups):
            row = i // num_cols
            col = i % num_cols
            var = tk.BooleanVar(value=enabled)
            cb = ttk.Checkbutton(root.groups_inner, text=gname, variable=var,
                                 command=lambda name=gname, v=var: toggle_group(name, v))
            cb.grid(row=row, column=col, sticky='w', padx=5, pady=2)
        if not groups:
            ttk.Label(root.groups_inner, text=bot.tr('no_groups')).grid(row=0, column=0, padx=5)

    def toggle_group(name, var):
        bot.groups[name] = var.get()
        bot.save_config()

    def refresh_group_related_panels(_event=None):
        refresh_groups_panel()
        if hasattr(root, 'refresh_routine_summary'):
            root.refresh_routine_summary()

    root.bind("<<GroupsChanged>>", refresh_group_related_panels)
    bot.refresh_groups_callback = refresh_groups_panel

    root.status_after_id = None
    root.active_after_id = None
    root.monitor_after_id = None
    root.open_area_manager = lambda: AreaManager(root, bot).show()
    root.open_group_schedule = lambda: GroupScheduleDialog(root, bot).show()

    build_compact_ui(root, bot)

    if is_multi_worker:
        root.withdraw()
        control_path = RUNTIME_DIR / "control.json"
        last_control_sequence = {"value": -1}

        def poll_parent_command():
            try:
                payload = json.loads(control_path.read_text(encoding="utf-8"))
                sequence = int(payload.get("sequence", -1))
                command = str(payload.get("command") or "").strip().lower()
            except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
                sequence = -1
                command = ""
            if sequence > last_control_sequence["value"]:
                last_control_sequence["value"] = sequence
                if command == "pause":
                    bot.pause()
                elif command == "resume":
                    bot.resume()
                elif command == "stop":
                    if bot.is_running:
                        bot.stop()
                    bot.stop_schedule_thread()
                    root.after(100, root.destroy)
                    return
            root.after(400, poll_parent_command)

        root.after(400, poll_parent_command)

    if should_autostart_all_emulators() and not is_multi_worker:
        logger.info("Autostart-all requested: starting selected tasks on every LDPlayer")
        root.after(1500, bot.start_all_emulators)
    elif should_autostart_merchant_only():
        logger.info("Merchant-only diagnostic requested: all other tasks are suspended")
        root.after(1500, lambda: bot.start_task_only("mysterious_merchant"))
    elif should_autostart_login_only():
        logger.info("Login-only diagnostic requested: all other tasks are suspended")
        root.after(1500, lambda: bot.start_task_only("game_login"))
    elif should_autostart_fence_only():
        logger.info("Fence-only diagnostic requested: all other tasks are suspended")
        root.after(1500, lambda: bot.start_task_only("fence_survivors"))
    elif should_autostart_processing_only():
        logger.info("Processing-only diagnostic requested: all other tasks are suspended")
        root.after(1500, lambda: bot.start_task_only("processing_factory"))
    elif should_autostart_boost_only():
        logger.info("Boost-only diagnostic requested: all other tasks are suspended")
        root.after(1500, lambda: bot.start_task_only("gathering_boost"))
    elif should_autostart_routines():
        if should_start_fresh_pass():
            logger.info(
                "Fresh-pass autostart requested: resetting the current account pass"
            )

            def start_fresh_pass():
                if not bot.select_account_profile(
                    bot.current_account_id,
                    save=True,
                    start_fresh_pass=True,
                ):
                    logger.error("Fresh-pass autostart could not select current account")
                    return
                bot.start_routines(resume=True)

            root.after(1500, start_fresh_pass)
        else:
            logger.info("Autostart requested: resuming selected routine tasks")
            root.after(1500, lambda: bot.start_routines(resume=True))

    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, bot))
    root.mainloop()


if __name__ == "__main__":
    main()
