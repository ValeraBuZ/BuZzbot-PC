from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time
import uuid


PROFILE_NAMESPACE = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
RADAR_TASK_IDS = ("radar_rewards", "radar_quick", "radar_marches")
LEGACY_RADAR_TASK_ID = "radar"
PRIZE_HUNT_SAFE_EXIT_UID = str(
    uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:safe_exit")
)
PRIZE_HUNT_REPEAT_UIDS = {
    str(uuid.uuid5(PROFILE_NAMESPACE, f"prize_hunt:{step_id}"))
    for step_id in ("again", "match", "confirm")
}
RESOURCE_TASK_IDS = ("food", "wood", "metal", "oil")
RESOURCE_RESULT_LEVELS = (6, 7)
RESOURCE_RESULT_SEARCH_REGION = (570, 340, 150, 120)
RESOURCE_STEP_IDS = (
    "region",
    "world_search",
    "resource_icon",
    "search_button",
    "gather",
    "create_squad",
    "march",
)
STRICT_RUNTIME_SEQUENCES = {
    "heal": ("open_wounded", "start_healing"),
    "train_infantry": ("queue", "building", "train"),
    "train_riders": ("queue", "building", "train"),
    "train_shooters": ("queue", "building", "train"),
    "train_vehicles": ("queue", "building", "train"),
    "zombie_hunt": (
        "world_search",
        "zombie_icon",
        "search",
        "attack",
        "create_squad",
        "march",
    ),
    "collective_mind": (
        "world_search",
        "leader_icon",
        "search",
        "rally",
        "confirm_rally",
        "march",
    ),
}
TRAINING_QUEUE_ORDINALS = {
    "train_infantry": 1,
    "train_riders": 2,
    "train_shooters": 3,
    "train_vehicles": 4,
}
TRAINING_RADIAL_TARGETS = {
    "train_infantry": (758, 487),
    "train_riders": (758, 487),
    "train_shooters": (758, 487),
    "train_vehicles": (780, 465),
}
RADAR_STEP_PRIORITIES = {
    "radar_screen_guard": 1,
    "card_guard": 1,
    "forward_guard": 1,
    "open_radar": 2,
    "collect_completed": 3,
    "wait_in_progress": 5,
    "open_any_task": 10,
    "open_supply": 10,
    "open_car": 10,
    "open_zombie": 10,
    "collect_supply": 20,
    "attack_zombie": 20,
    "rescue_survivors": 20,
    "transport_supplies": 21,
    "confirm_transport": 22,
    "create_squad": 30,
    "march": 40,
    "close_region_search": 45,
    "return_shelter": 50,
    "task_person_gold_reward": 57,
    "task_car_generic_shape": 58,
    "task_person_generic_shape": 59,
    "task_special_generic_shape": 61,
    "task_supply_reward_final": 62,
    "task_car_unstarted_final": 63,
    "task_special_reward_followup": 64,
    "task_car_reward_followup": 65,
    "task_person_unstarted_followup": 66,
    "task_supply_unstarted_followup": 67,
    "task_car_unstarted_live": 70,
    "task_special_unstarted_live": 71,
    "task_skull_unstarted_live": 72,
    "task_survivor_current_live": 73,
    "task_skull_reward_current": 74,
    "task_skull_reward": 75,
    "task_car_reward": 76,
    "task_supply_ready": 77,
    "task_car_ready": 78,
    "task_zombie_ready": 79,
    "task_supply": 80,
    "task_car": 81,
    "task_zombie": 82,
    "task_car_current": 83,
    "task_skull_current": 84,
    "task_special_current": 85,
    "task_fist_current": 86,
}
LEGACY_RADAR_TEMPLATE_UIDS = frozenset(
    str(uuid.uuid5(PROFILE_NAMESPACE, f"{LEGACY_RADAR_TASK_ID}:{step_id}"))
    for step_id in RADAR_STEP_PRIORITIES
)

RADAR_CARD_RUNTIME_STEPS = frozenset(
    {
        "radar_marker",
        "radar_forward",
        "radar_action",
        "radar_squad",
        "radar_march",
    }
)


DEFAULT_ROUTINE_TASKS = (
    {
        "id": "game_login",
        "name": "Вход в игру",
        "group": "Вход в игру",
        "category": "startup",
        "enabled": False,
        "uses_march": False,
        "priority": 1,
        "interval_minutes": 1440.0,
        "timeout_seconds": 330.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "settings": {},
    },
    {
        "id": "alliance_help",
        "name": "Помощь другим игрокам",
        "group": "Помощь альянсу",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 10,
        "interval_minutes": 1.0,
        "timeout_seconds": 8.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "empty_home_is_success": True,
        "settings": {},
    },
    {
        "id": "fence_survivors",
        "name": "Выжившие у забора",
        "group": "Выжившие у забора",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 12,
        "interval_minutes": 15.0,
        "timeout_seconds": 8.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "empty_home_is_success": True,
        "settings": {},
    },
    {
        "id": "processing_factory",
        "name": "Завод по обработке",
        "group": "Завод по обработке",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 13,
        "interval_minutes": 180.0,
        "timeout_seconds": 25.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "complete_when_idle": True,
        "idle_confirmations": 1,
        "idle_completion_guard_uid": str(
            uuid.uuid5(PROFILE_NAMESPACE, "processing_factory:factory_guard")
        ),
        "settings": {},
    },
    {
        "id": "processing_contest",
        "name": "Конкурс по обработке",
        "group": "Конкурс по обработке",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 14,
        "interval_minutes": 180.0,
        "timeout_seconds": 25.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "complete_when_idle": True,
        "idle_confirmations": 1,
        "idle_completion_guard_uid": str(
            uuid.uuid5(PROFILE_NAMESPACE, "processing_contest:contest_guard")
        ),
        "settings": {},
    },
    {
        "id": "mail_rewards",
        "name": "Награды почты",
        "group": "Награды почты",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 15,
        "interval_minutes": 30.0,
        "timeout_seconds": 10.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "completion_runtime_step": "claim_reports",
        "settings": {},
    },
    {
        "id": "completed_tasks",
        "name": "Выполненные задания",
        "group": "Выполненные задания",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 18,
        "interval_minutes": 30.0,
        "timeout_seconds": 10.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "completion_runtime_step": "scroll_top_4",
        "settings": {},
    },
    {
        "id": "vip_rewards",
        "name": "Награды VIP",
        "group": "Награды VIP",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 20,
        "interval_minutes": 720.0,
        "timeout_seconds": 30.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "empty_home_is_success": True,
        "settings": {},
    },
    {
        "id": "alliance_donations",
        "name": "Пожертвования альянсу",
        "group": "Пожертвования альянсу",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 25,
        # One spent attempt is restored by the game roughly every 20 minutes.
        "interval_minutes": 20.0,
        "timeout_seconds": 45.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        # Completion is driven by the project-check limit. This sentinel prevents
        # merely opening the technology tree from being treated as success.
        "completion_runtime_step": "all_projects_checked",
        "settings": {
            "max_donations": 100,
            "max_project_checks": 6,
            "avoid_gems": True,
        },
    },
    {
        "id": "radar_rewards",
        "name": "Радар: награды",
        "group": "Радар - награды",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 30,
        "interval_minutes": 720.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "complete_when_idle": True,
        "idle_confirmations": 2,
        "manual_screen_required": False,
        "idle_completion_guard_uid": str(
            uuid.uuid5(PROFILE_NAMESPACE, "radar_rewards:radar_screen_guard")
        ),
        "settings": {
            "fixed_utc_hours": [0, 12],
            "in_progress_retry_minutes": 5,
            "visual_fallback": True,
        },
    },
    {
        "id": "radar_quick",
        "name": "Радар: быстрые задания",
        "group": "Радар - быстрые задания",
        "category": "daily",
        "enabled": False,
        "uses_march": False,
        "priority": 31,
        "interval_minutes": 720.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "complete_when_idle": True,
        "idle_confirmations": 2,
        "manual_screen_required": False,
        "idle_completion_guard_uid": str(
            uuid.uuid5(PROFILE_NAMESPACE, "radar_quick:radar_screen_guard")
        ),
        "settings": {
            "fixed_utc_hours": [0, 12],
            "in_progress_retry_minutes": 5,
            "visual_fallback": True,
        },
    },
    {
        "id": "radar_marches",
        "name": "Радар: задания с отрядом",
        "group": "Радар - задания с отрядом",
        "category": "daily",
        "enabled": False,
        "uses_march": True,
        "priority": 32,
        "interval_minutes": 720.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "march_completion_runtime_step": "radar_march",
        "completion_uid": "",
        "complete_when_idle": True,
        "idle_confirmations": 2,
        "manual_screen_required": False,
        "idle_completion_guard_uid": str(
            uuid.uuid5(PROFILE_NAMESPACE, "radar_marches:radar_screen_guard")
        ),
        "settings": {
            "fixed_utc_hours": [0, 12],
            "in_progress_retry_minutes": 5,
            "visual_fallback": True,
        },
    },
    {
        "id": "research",
        "name": "Исследования",
        "group": "Исследования",
        "category": "development",
        "enabled": False,
        "uses_march": False,
        "priority": 35,
        "interval_minutes": 5.0,
        "timeout_seconds": 15.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "empty_home_is_success": True,
        "settings": {
            "branch": "off",
            "use_speedups": False,
            "max_lab_checks": 2,
        },
    },
    {
        "id": "gathering_boost",
        "name": "Усиление сбора ресурсов",
        "group": "Усиление сбора ресурсов",
        "category": "development",
        "enabled": False,
        "uses_march": False,
        "priority": 40,
        "interval_minutes": 480.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "settings": {
            "boost_hours": 8,
        },
    },
    {
        "id": "heal",
        "name": "Лечение войск",
        "group": "Лечение войск",
        "category": "army",
        "enabled": False,
        "uses_march": False,
        "priority": 45,
        "interval_minutes": 0.1,
        "timeout_seconds": 8.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "empty_home_is_success": True,
        "settings": {
            "troop_count": 2500,
            "collection_delay_seconds": 2,
            "repeat_delay_seconds": 2,
            "collect_finished": True,
            "repeat": True,
        },
    },
    {
        "id": "train_infantry",
        "name": "Производство: пехота",
        "group": "Производство пехоты",
        "category": "training",
        "enabled": False,
        "uses_march": False,
        "priority": 50,
        "interval_minutes": 2.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "settings": {"highest_tier": True, "collect_finished": True, "max_queue_checks": 5},
    },
    {
        "id": "train_riders",
        "name": "Производство: райдеры",
        "group": "Производство райдеров",
        "category": "training",
        "enabled": False,
        "uses_march": False,
        "priority": 50,
        "interval_minutes": 2.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "settings": {"highest_tier": True, "collect_finished": True, "max_queue_checks": 5},
    },
    {
        "id": "train_shooters",
        "name": "Производство: стрелки",
        "group": "Производство стрелков",
        "category": "training",
        "enabled": False,
        "uses_march": False,
        "priority": 50,
        "interval_minutes": 2.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "settings": {"highest_tier": True, "collect_finished": True, "max_queue_checks": 5},
    },
    {
        "id": "train_vehicles",
        "name": "Производство: машинки",
        "group": "Производство машин",
        "category": "training",
        "enabled": False,
        "uses_march": False,
        "priority": 50,
        "interval_minutes": 2.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "settings": {"highest_tier": True, "collect_finished": True, "max_queue_checks": 5},
    },
    {
        "id": "prize_hunt",
        "name": "Охота за призом",
        "group": "Охота за призом",
        "category": "marches",
        "enabled": False,
        "standalone": True,
        "uses_march": False,
        "priority": 55,
        "interval_minutes": 1.0,
        "timeout_seconds": 1800.0,
        "march_duration_minutes": 10.0,
        "completion_uid": "",
        "settings": {
            "repeat_until_stopped": True,
            "squad": 1,
        },
    },
    {
        "id": "wasteland_exploration",
        "name": "Исследование пустоши",
        "group": "Исследование пустоши",
        "category": "event",
        "enabled": False,
        "uses_march": False,
        "priority": 58,
        "interval_minutes": 1440.0,
        "timeout_seconds": 120.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "completion_runtime_step": "stamina_empty",
        "empty_home_is_success": False,
        "settings": {
            # The live event starts at 04:00 Moscow time (01:00 UTC).
            "fixed_utc_hours": [1],
            "max_encounters": 40,
            "stamina_retry_minutes": 12,
        },
    },
    {
        "id": "zombie_hunt",
        "name": "Убийство зомби",
        "group": "Убийство зомби",
        "category": "marches",
        "enabled": False,
        "uses_march": True,
        "priority": 60,
        "interval_minutes": 0.1,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 10.0,
        "completion_uid": "",
        "march_completion_runtime_step": "march",
        "settings": {
            "fallback_levels": 3,
            "not_found_retry_seconds": 60,
            "stamina_reserve": 0,
            "use_stamina_items": True,
            "stamina_item_amount": "auto",
            "max_attacks": 0,
        },
    },
    {
        "id": "collective_mind",
        "name": "Коллективный разум",
        "group": "Коллективный разум",
        "category": "marches",
        "enabled": False,
        "uses_march": True,
        "priority": 65,
        "interval_minutes": 5.0,
        "timeout_seconds": 12.0,
        "march_duration_minutes": 30.0,
        "completion_uid": "",
        "settings": {"repeat": True, "level": 6},
    },
    {
        "id": "food",
        "name": "Еда",
        "group": "Еда",
        "category": "resources",
        "enabled": False,
        "uses_march": True,
        "priority": 100,
        "interval_minutes": 0.1,
        "timeout_seconds": 30.0,
        "march_duration_minutes": 240.0,
        "completion_uid": "",
        "settings": {"resource_level": 7},
    },
    {
        "id": "wood",
        "name": "Дерево",
        "group": "Дерево",
        "category": "resources",
        "enabled": False,
        "uses_march": True,
        "priority": 100,
        "interval_minutes": 0.1,
        "timeout_seconds": 30.0,
        "march_duration_minutes": 240.0,
        "completion_uid": "",
        "settings": {"resource_level": 7},
    },
    {
        "id": "metal",
        "name": "Металл",
        "group": "Металл",
        "category": "resources",
        "enabled": False,
        "uses_march": True,
        "priority": 100,
        "interval_minutes": 0.1,
        "timeout_seconds": 30.0,
        "march_duration_minutes": 240.0,
        "completion_uid": "",
        "settings": {"resource_level": 7},
    },
    {
        "id": "oil",
        "name": "Нефть",
        "group": "Нефть",
        "category": "resources",
        "enabled": False,
        "uses_march": True,
        "priority": 100,
        "interval_minutes": 0.1,
        "timeout_seconds": 10.0,
        "march_duration_minutes": 240.0,
        "completion_uid": "",
        "settings": {"resource_level": 7},
    },
)


TASK_SETTING_SPECS = {
    "alliance_donations": (
        {"key": "max_donations", "label": "Максимум пожертвований", "kind": "int", "min": 1, "max": 100},
        {"key": "max_project_checks", "label": "Проектов за цикл", "kind": "int", "min": 1, "max": 20},
        {"key": "avoid_gems", "label": "Не тратить алмазы", "kind": "bool"},
    ),
    "research": (
        {
            "key": "branch",
            "label": "Приоритет",
            "kind": "choice",
            "choices": (("off", "Отключено"), ("economy", "Экономика"), ("war", "Война"), ("any", "Любое")),
        },
        {"key": "use_speedups", "label": "Использовать ускорения", "kind": "bool"},
    ),
    "gathering_boost": (
        {
            "key": "boost_hours",
            "label": "Длительность усиления",
            "kind": "choice",
            "choices": ((8, "8 часов"), (24, "24 часа")),
        },
    ),
    "heal": (
        {"key": "troop_count", "label": "Количество войск", "kind": "int", "min": 1, "max": 1000000},
        {
            "key": "collection_delay_seconds",
            "label": "Проверять сбор через, сек",
            "kind": "int",
            "min": 1,
            "max": 3600,
        },
        {
            "key": "repeat_delay_seconds",
            "label": "Повтор задачи через, сек",
            "kind": "int",
            "min": 1,
            "max": 3600,
        },
        {"key": "collect_finished", "label": "Собирать вылеченных", "kind": "bool"},
        {"key": "repeat", "label": "Повторять лечение", "kind": "bool"},
    ),
    "prize_hunt": (
        {"key": "repeat_until_stopped", "label": "Повторять до остановки", "kind": "bool"},
        {"key": "squad", "label": "Номер отряда", "kind": "int", "min": 1, "max": 5},
    ),
    "wasteland_exploration": (
        {
            "key": "max_encounters",
            "label": "Встреч за проход (0 = до конца выносливости)",
            "kind": "int",
            "min": 0,
            "max": 1000,
        },
        {
            "key": "stamina_retry_minutes",
            "label": "Повтор после окончания выносливости, мин",
            "kind": "int",
            "min": 1,
            "max": 1440,
        },
    ),
    "zombie_hunt": (
        {"key": "fallback_levels", "label": "Понижений от уровня в игре", "kind": "int", "min": 0, "max": 10},
        {
            "key": "not_found_retry_seconds",
            "label": "Повтор, если зомби нет (сек)",
            "kind": "int",
            "min": 10,
            "max": 3600,
        },
        {"key": "stamina_reserve", "label": "Оставлять выносливости", "kind": "int", "min": 0, "max": 10000},
        {"key": "use_stamina_items", "label": "Использовать предметы выносливости", "kind": "bool"},
        {
            "key": "stamina_item_amount",
            "label": "Предмет выносливости",
            "kind": "choice",
            "choices": (
                ("auto", "Авто: +50 -> +100 -> +500 -> +1000"),
                ("50", "+50"),
                ("100", "+100"),
                ("500", "+500"),
                ("1000", "+1000"),
            ),
        },
        {"key": "max_attacks", "label": "Максимум атак (0 = без лимита)", "kind": "int", "min": 0, "max": 1000},
    ),
    "collective_mind": (
        {"key": "repeat", "label": "Повторять сбор", "kind": "bool"},
        {
            "key": "level",
            "label": "Уровень",
            "kind": "choice",
            "choices": ((6, "6"), (7, "7")),
        },
    ),
    "food": ({"key": "resource_level", "label": "Уровень клетки", "kind": "int", "min": 1, "max": 7},),
    "wood": ({"key": "resource_level", "label": "Уровень клетки", "kind": "int", "min": 1, "max": 7},),
    "metal": ({"key": "resource_level", "label": "Уровень клетки", "kind": "int", "min": 1, "max": 7},),
    "oil": ({"key": "resource_level", "label": "Уровень клетки", "kind": "int", "min": 1, "max": 7},),
}


def default_routine_tasks():
    return deepcopy(list(DEFAULT_ROUTINE_TASKS))


def is_radar_task_id(task_id):
    return str(task_id or "") in {*RADAR_TASK_IDS, LEGACY_RADAR_TASK_ID}


def task_setting_specs(task_id):
    return deepcopy(list(TASK_SETTING_SPECS.get(task_id, ())))


def runtime_step_is_ready(image, completed_steps):
    """Return whether an image's prerequisite runtime steps were completed."""
    completed = {str(step) for step in completed_steps}
    own_step = str(image.get("runtime_step") or "")
    if own_step and own_step in completed and not image.get("repeat_runtime_step", False):
        return False
    disabled_after = image.get("disabled_after_runtime_steps", ())
    if isinstance(disabled_after, str):
        disabled_after = (disabled_after,)
    if any(str(step) in completed for step in disabled_after if str(step)):
        return False
    required = image.get("requires_runtime_steps", ())
    if isinstance(required, str):
        required = (required,)
    required = tuple(str(step) for step in required if str(step))
    if not required:
        return True
    # Strict UI flows may be resumed while the game is already showing a later
    # dialog (for example, the squad screen after a slow map transition).
    if not completed and image.get("allow_runtime_resume", False):
        return True
    if image.get("runtime_step_mode") == "any":
        return any(step in completed for step in required)
    return all(step in completed for step in required)


def healing_pending_allows_image(image, task):
    """Allow collection entry but block a new treatment while one is pending."""
    if str((task or {}).get("id") or "") != "heal":
        return True
    settings = (task or {}).get("settings", {})
    if not settings.get("_collection_pending", False):
        return True
    return str((image or {}).get("runtime_step") or "") not in {
        "healing_overview",
        "start_healing",
    }


def setting_requirement_matches(image, settings):
    """Check a template setting, optionally allowing a safer longer duration."""
    key = str(image.get("required_setting_key") or "")
    if not key:
        return True
    required = image.get("required_setting_value")
    current = (settings or {}).get(key)
    if str(current) == str(required):
        return True
    if not image.get("allow_higher_setting_fallback"):
        return False
    try:
        return float(required) > float(current)
    except (TypeError, ValueError):
        return False


def gathering_boost_duration_hours(completed_steps, configured_hours=8.0):
    """Return the duration that was actually selected for a gathering boost."""
    completed = {str(step) for step in (completed_steps or ())}
    if "boost_24h" in completed:
        return 24.0
    if "boost_8h" in completed:
        return 8.0
    try:
        return max(1.0, float(configured_hours))
    except (TypeError, ValueError):
        return 8.0


def gathering_boost_active_until(task, now=None):
    """Return a future persisted boost deadline, or zero when it is inactive."""
    try:
        deadline = float((task or {}).get("settings", {}).get("active_until", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    current = time.time() if now is None else float(now)
    return deadline if deadline > current else 0.0


def completed_runtime_steps_for_image(image):
    """Return the current step and any predecessors implied by its screen."""
    implied = image.get("implied_runtime_steps", ())
    if isinstance(implied, str):
        implied = (implied,)
    completed = {str(step) for step in implied if str(step)}
    own_step = str(image.get("runtime_step") or "")
    if own_step:
        completed.add(own_step)
    return completed


def reset_radar_card_runtime_steps(completed_steps):
    """Forget the previous radar card before opening another marker."""
    completed_steps.difference_update(RADAR_CARD_RUNTIME_STEPS)


def image_is_allowed_for_routine(image, task_id, routine_started=False):
    """Return whether a shared system template may run in this routine."""
    task_id = str(task_id or "")
    only = image.get("only_routine_ids", ())
    if isinstance(only, str):
        only = (only,)
    only_ids = {str(item) for item in only if str(item)}
    if only_ids and task_id not in only_ids:
        return False
    # Startup banners are intentionally handled only by the opt-in login task.
    # Matching them during healing or training can open the rotating event tile.
    if image.get("startup_only", False) and task_id != "game_login":
        return False
    if routine_started and image.get("startup_only", False):
        return False
    disabled = image.get("disabled_routine_ids", ())
    if isinstance(disabled, str):
        disabled = (disabled,)
    disabled_ids = {str(item) for item in disabled if str(item)}
    return task_id not in disabled_ids


def prize_hunt_branch_allows_image(image, repeat_until_stopped):
    """Keep the mutually exclusive Exit and Again result branches separate."""
    uid = str(image.get("uid") or "")
    if uid == PRIZE_HUNT_SAFE_EXIT_UID:
        return not bool(repeat_until_stopped)
    if uid in PRIZE_HUNT_REPEAT_UIDS:
        return bool(repeat_until_stopped)
    return True


def no_action_retry_delay(task):
    """Use a bounded retry delay when a task timed out without any action."""
    interval_seconds = float(task.get("interval_minutes", 1.0)) * 60.0
    if task.get("id") == "heal":
        settings = task.get("settings", {})
        if settings.get("_collection_pending", False):
            return healing_collection_delay(task)
        return healing_repeat_delay(task)
    return max(30.0, min(300.0, interval_seconds))


def healing_collection_delay(task):
    """Return the per-account delay before checking a started healing batch."""
    settings = task.get("settings", {})
    try:
        delay = float(settings.get("collection_delay_seconds", 2) or 2)
    except (TypeError, ValueError):
        delay = 2.0
    return max(1.0, min(3600.0, delay))


def healing_repeat_delay(task):
    """Return the per-account delay before the healing task runs again."""
    settings = task.get("settings", {})
    try:
        delay = float(settings.get("repeat_delay_seconds", 2) or 2)
    except (TypeError, ValueError):
        delay = 2.0
    return max(1.0, min(3600.0, delay))


def unavailable_retry_delay(task):
    """Keep finished-healing collection responsive without rushing other tasks."""
    settings = task.get("settings", {})
    if task.get("id") == "heal" and settings.get("_collection_pending", False):
        return healing_collection_delay(task)
    return max(60.0, no_action_retry_delay(task))


def format_wait_duration(seconds, language="ru"):
    """Format scheduler waits without exposing unwieldy raw second counts."""
    total = max(0, int(float(seconds) + 0.999))
    if total < 60:
        return f"{total} {'sec' if language == 'en' else 'сек'}"
    if total < 3600:
        minutes, remaining = divmod(total, 60)
        if remaining:
            suffix = "min" if language == "en" else "мин"
            seconds_suffix = "sec" if language == "en" else "сек"
            return f"{minutes} {suffix} {remaining} {seconds_suffix}"
        return f"{minutes} {'min' if language == 'en' else 'мин'}"
    hours, remainder = divmod(total, 3600)
    minutes = (remainder + 59) // 60
    if minutes >= 60:
        hours += 1
        minutes = 0
    hours_suffix = "h" if language == "en" else "ч"
    if not minutes:
        return f"{hours} {hours_suffix}"
    return f"{hours} {hours_suffix} {minutes} {'min' if language == 'en' else 'мин'}"


def routine_home_recovery_due(task, had_action, attempted, idle_seconds):
    """Recover a newly started task from an unrelated leftover screen."""
    timeout = max(1.0, float(task.get("timeout_seconds", 8.0) or 8.0))
    recovery_delay = min(12.0, timeout)
    can_recover = bool(task.get("uses_march", False)) or task.get("id") in {
        "heal",
        "radar_rewards",
        "radar_quick",
        "radar_marches",
        "research",
        "wasteland_exploration",
        "train_infantry",
        "train_riders",
        "train_shooters",
        "train_vehicles",
    }
    return bool(
        can_recover
        and not task.get("manual_screen_required", False)
        and not had_action
        and not attempted
        and float(idle_seconds) >= recovery_delay
    )


def routine_idle_screen_recovery_due(
    task,
    had_action,
    guard_visible,
    attempted,
    outside_seconds,
):
    """Recover an idle-completion task that became stuck on another screen."""
    timeout = max(1.0, float(task.get("timeout_seconds", 8.0) or 8.0))
    if str(task.get("id") or "") in RADAR_TASK_IDS:
        recovery_delay = max(8.0, min(20.0, timeout))
    else:
        recovery_delay = max(45.0, min(90.0, timeout * 3.0))
    return bool(
        task.get("complete_when_idle")
        and had_action
        and not guard_visible
        and not attempted
        and float(outside_seconds) >= recovery_delay
    )


def routine_missing_followup_is_unavailable(task, completed_steps, idle_seconds):
    """Detect an opened feature whose optional event entry is not present."""
    task_id = str(task.get("id") or "")
    completed = {str(step) for step in completed_steps}
    timeout = max(1.0, float(task.get("timeout_seconds", 8.0) or 8.0))
    if task_id == "processing_contest":
        if "open_refinery" not in completed or "open_contest" in completed:
            return False
        return float(idle_seconds) >= timeout
    if task_id == "gathering_boost":
        has_category = "boost_category" in completed
        has_item = bool({"boost_8h", "boost_24h", "use"}.intersection(completed))
        return has_category and not has_item and float(idle_seconds) >= timeout
    if task_id == "wasteland_exploration":
        followup_steps = completed.difference({"event_entry"})
        return (
            "event_entry" in completed
            and not followup_steps
            and float(idle_seconds) >= min(20.0, timeout)
        )
    return False


def routine_requires_settlement(task):
    """Return whether a task must run inside the player's settlement."""
    if task.get("manual_screen_required", False):
        return False
    return str(task.get("category") or "") in {
        "daily",
        "development",
        "army",
        "training",
    }


def routine_march_context_key(input_backend, adb_serial, account_id):
    """Build a stable scope for locally estimated march deadlines."""
    backend = "adb" if str(input_backend or "").lower() == "adb" else "screen"
    serial = str(adb_serial or "desktop").strip() or "desktop"
    account = str(account_id or "default").strip() or "default"
    return f"{backend}:{serial}:{account}"


def effective_active_marches(observed, estimated, confirmed_floor, now, grace_until):
    """Prefer the visible game counter over local duration estimates."""
    estimated = max(0, int(estimated))
    if observed is None:
        return estimated
    observed = max(0, int(observed))
    if observed == 0 and estimated and float(now) < float(grace_until):
        return max(estimated, max(0, int(confirmed_floor)))
    return observed


def reconcile_march_deadlines(deadlines, observed, now, grace_until):
    """Drop reservations immediately when the visible counter disproves them."""
    active = [float(deadline) for deadline in deadlines if float(deadline) > float(now)]
    if observed is None:
        return active
    observed = max(0, int(observed))
    if observed == 0 and active and float(now) < float(grace_until):
        return active
    if observed >= len(active):
        return active
    return active[:observed]


def no_available_squad_wait_exceeded(task, completed_steps, idle_seconds, grace_seconds=8.0):
    """Detect a squad screen that never exposes the final march button."""
    completed = {str(step) for step in completed_steps}
    return bool(
        task.get("uses_march", False)
        and "create_squad" in completed
        and "march" not in completed
        and float(idle_seconds) >= float(grace_seconds)
    )


def resource_search_retry_due(task, completed_steps, attempts, max_attempts=3):
    """Retry a resource search when the selected map cell cannot be gathered."""
    completed = {str(step) for step in completed_steps}
    return bool(
        task.get("id") in RESOURCE_TASK_IDS
        and "search_button" in completed
        and "gather" not in completed
        and int(attempts) < int(max_attempts)
    )


def zombie_fallback_levels(settings, maximum=10):
    """Return the bounded number of lower zombie levels to try."""
    try:
        configured = int((settings or {}).get("fallback_levels", maximum))
    except (TypeError, ValueError):
        configured = int(maximum)
    return min(int(maximum), max(0, configured))


def radar_marker_was_confirmed(uid, x, y, confirmed_keys, radius=32):
    """Match an animated radar marker to a previously confirmed deployment."""
    marker_uid = str(uid or "")
    radius_squared = float(radius) ** 2
    for key in confirmed_keys:
        if not isinstance(key, (tuple, list)) or len(key) != 3:
            continue
        key_uid, key_x, key_y = key
        if str(key_uid or "") not in {marker_uid, "*"}:
            continue
        if (float(key_x) - float(x)) ** 2 + (float(key_y) - float(y)) ** 2 <= radius_squared:
            return True
    return False


def radar_marker_requires_notification(image, task_id):
    """Radar map markers are actionable without the unrelated pass-shop badge."""
    if is_radar_task_id(task_id):
        return False
    configured = image.get("requires_radar_notification")
    if configured is not None:
        return bool(configured)
    return False


def upgrade_resource_runtime_metadata(images, tasks):
    """Apply the current resource sequence to both fresh and older profiles."""
    images_by_uid = {str(image.get("uid") or ""): image for image in images}
    upgraded = 0
    for level in RESOURCE_RESULT_LEVELS:
        observer_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"resource_result_level:{level}"))
        observer = images_by_uid.get(observer_uid)
        if observer is not None:
            observer["search_region"] = list(RESOURCE_RESULT_SEARCH_REGION)
            observer["confidence"] = 0.65

    for task_id in RESOURCE_TASK_IDS:
        previous_step = None
        prior_runtime_steps = []
        world_search_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:world_search"))
        for step_id in RESOURCE_STEP_IDS:
            uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:{step_id}"))
            image = images_by_uid.get(uid)
            if image is None:
                previous_step = "world_search" if step_id == "region" else step_id
                continue
            runtime_step = "world_search" if step_id == "region" else step_id
            image["runtime_step"] = runtime_step
            image["allow_runtime_resume"] = True
            # Every free march reuses the same resource buttons. Keep anti-loop
            # protection within one pass without blocking the next scheduled pass.
            image["allow_repeat"] = True
            image["block_seconds"] = 2.0
            image["implied_runtime_steps"] = list(dict.fromkeys(prior_runtime_steps))
            image.pop("requires_runtime_steps", None)
            if step_id not in {"region", "world_search"} and previous_step:
                image["requires_runtime_steps"] = [previous_step]
            if step_id == "search_button":
                # A selected resource icon has a different appearance, so the
                # visible search button is also a safe resume point.
                image["requires_runtime_steps"] = ["world_search"]
            if step_id == "region":
                image["action"] = "open_world_search"
                image["next_template_uid"] = world_search_uid
                image["delay"] = 0.8
                image["settlement_screen_marker"] = True
                image["search_region"] = [0, 560, 150, 160]
            if step_id == "gather":
                image["expected_result_level_setting"] = "resource_level"
                image["result_level_template_uids"] = {
                    str(level): str(
                        uuid.uuid5(PROFILE_NAMESPACE, f"resource_result_level:{level}")
                    )
                    for level in RESOURCE_RESULT_LEVELS
                }
            if step_id == "march":
                image["confirm_disappears"] = True
            previous_step = runtime_step
            prior_runtime_steps.append(runtime_step)
            upgraded += 1

    for task in tasks:
        if task.get("id") in RESOURCE_TASK_IDS:
            settings = task.setdefault("settings", {})
            settings["resource_level"] = min(
                7,
                max(1, int(settings.get("resource_level", 7) or 7)),
            )
            task["timeout_seconds"] = max(30.0, float(task.get("timeout_seconds", 0.0) or 0.0))
    return upgraded


def select_best_resource_result_level(matches, raw_matches=None):
    """Return the strongest safe level match, including an unambiguous fallback."""
    candidates = []
    for level, confidence in matches:
        try:
            candidates.append((float(confidence), int(level)))
        except (TypeError, ValueError):
            continue
    if candidates:
        return max(candidates)[1]

    fallback = []
    for level, confidence in raw_matches or ():
        try:
            fallback.append((float(confidence), int(level)))
        except (TypeError, ValueError):
            continue
    fallback.sort(reverse=True)
    if not fallback or fallback[0][0] < 0.62:
        return None
    runner_up = fallback[1][0] if len(fallback) > 1 else -1.0
    if fallback[0][0] - runner_up < 0.12:
        return None
    return fallback[0][1]


def upgrade_repeatable_claim_metadata(images, tasks):
    """Keep claim screens open until every available free action is exhausted."""
    images_by_uid = {str(image.get("uid") or ""): image for image in images}
    upgraded = 0

    alliance_donate_uid = str(
        uuid.uuid5(PROFILE_NAMESPACE, "alliance_donations:donate_resources")
    )
    alliance_close_uid = str(
        uuid.uuid5(PROFILE_NAMESPACE, "alliance_donations:close_project")
    )
    alliance_open_uid = str(
        uuid.uuid5(PROFILE_NAMESPACE, "alliance_donations:open_alliance")
    )
    alliance_technology_uid = str(
        uuid.uuid5(PROFILE_NAMESPACE, "alliance_donations:open_technology")
    )
    alliance_marked_uid = str(
        uuid.uuid5(PROFILE_NAMESPACE, "alliance_donations:select_marked_project")
    )
    alliance_project_uids = [
        str(uuid.uuid5(PROFILE_NAMESPACE, f"alliance_donations:{step_id}"))
        for step_id in (
            "select_project_construction",
            "select_project_research",
            "select_project_zombies",
            "select_project_elite",
            "select_project_fire_water",
            "select_project_gathering_elite",
        )
    ]
    vip_claim_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "vip_rewards:claim_chest"))
    vip_dismiss_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "vip_rewards:dismiss_info"))
    vip_receive_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "vip_rewards:receive_free"))
    vip_close_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "vip_rewards:close_vip"))

    repeatable = {
        alliance_donate_uid: 0.8,
        vip_claim_uid: 1.0,
        vip_dismiss_uid: 0.8,
        vip_receive_uid: 1.0,
    }
    for uid, block_seconds in repeatable.items():
        image = images_by_uid.get(uid)
        if image is None:
            continue
        image["allow_repeat"] = True
        image["block_seconds"] = block_seconds
        if uid == vip_receive_uid:
            image["completes_routine"] = True
        upgraded += 1

    guarded_closers = {
        alliance_close_uid: [alliance_donate_uid],
        vip_close_uid: [vip_claim_uid, vip_dismiss_uid, vip_receive_uid],
    }
    for uid, guard_uids in guarded_closers.items():
        image = images_by_uid.get(uid)
        if image is None:
            continue
        existing = image.get("skip_if_visible_uids") or []
        if isinstance(existing, str):
            existing = [existing]
        image["skip_if_visible_uids"] = list(dict.fromkeys([*existing, *guard_uids]))
        if uid == alliance_close_uid:
            image["runtime_step"] = "project_closed"
            image["repeat_runtime_step"] = True
        upgraded += 1

    donation_priorities = {
        alliance_open_uid: 5,
        alliance_technology_uid: 10,
        alliance_marked_uid: 15,
        alliance_donate_uid: 30,
        alliance_close_uid: 40,
    }
    donation_priorities.update(
        {uid: 20 + index for index, uid in enumerate(alliance_project_uids)}
    )
    for uid, priority in donation_priorities.items():
        image = images_by_uid.get(uid)
        if image is None:
            continue
        image["routine_priority"] = priority
        if uid == alliance_marked_uid:
            image.update(
                {
                    "action": "alliance_marked_project",
                    "confidence": 0.78,
                    "orb_match_threshold": 3,
                    "delay": 1.5,
                }
            )
            image.pop("allow_repeat", None)
        if uid in alliance_project_uids:
            image["confidence"] = min(
                0.74,
                float(image.get("confidence", 0.88) or 0.88),
            )
            image["orb_match_threshold"] = min(
                3,
                int(image.get("orb_match_threshold", 3) or 3),
            )
        upgraded += 1

    for task in tasks:
        if task.get("id") == "alliance_donations":
            settings = task.setdefault("settings", {})
            settings["max_donations"] = max(
                100,
                int(settings.get("max_donations", 0) or 0),
            )
            settings["max_project_checks"] = max(
                6,
                int(settings.get("max_project_checks", 0) or 0),
            )
            task["timeout_seconds"] = max(
                45.0,
                float(task.get("timeout_seconds", 45.0) or 45.0),
            )
            task["completion_runtime_step"] = "all_projects_checked"
        elif task.get("id") == "collective_mind":
            settings = task.setdefault("settings", {})
            level = int(settings.get("level", 6) or 6)
            settings["level"] = 7 if level == 7 else 6

    return upgraded


def donation_exhaustion_is_complete(task, completed_steps, idle_seconds):
    """Finish donation scans after an exhausted project yields no next target."""
    if str(task.get("id") or "") != "alliance_donations":
        return False
    if "project_closed" not in {str(step) for step in completed_steps}:
        return False
    timeout = max(1.0, float(task.get("timeout_seconds", 30.0) or 30.0))
    return float(idle_seconds) >= timeout


def upgrade_processing_runtime_metadata(images, tasks):
    """Keep refinery camera movement incremental across different settlements."""
    images_by_uid = {str(image.get("uid") or ""): image for image in images}
    upgraded = 0
    for task_id in ("processing_factory", "processing_contest"):
        pan_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:pan_north"))
        pan_image = images_by_uid.get(pan_uid)
        if pan_image is not None:
            pan_image["swipe_repeat_count"] = 2
            pan_image["swipe_repeat_pause"] = 0.2
            upgraded += 1
        for task in tasks:
            if task.get("id") == task_id:
                task["timeout_seconds"] = max(
                    30.0,
                    float(task.get("timeout_seconds", 25.0) or 25.0),
                )
                break
    return upgraded


def upgrade_strict_runtime_metadata(images, tasks):
    """Apply safe step ordering to healing, training and hunt routines."""
    images_by_uid = {str(image.get("uid") or ""): image for image in images}
    upgraded = 0

    collect_finished = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "heal:collect_finished"))
    )
    if collect_finished is not None:
        collect_finished.update(
            {
                "action": "collect_healed_troops",
                "observer_only": True,
                "confidence": min(
                    0.70,
                    float(collect_finished.get("confidence", 0.88) or 0.88),
                ),
                "grayscale": True,
                "search_region": [120, 70, 1040, 550],
                "orb_match_threshold": 3,
                "routine_priority": 1,
                "required_setting_key": "collect_finished",
                "required_setting_value": True,
                "allow_repeat": True,
                "block_seconds": 1.0,
                "requires_settlement_screen": True,
            }
        )
        upgraded += 1

    healing_overview = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "heal:collect_finished_alt_1"))
    )
    if healing_overview is not None:
        healing_overview.update(
            {
                "action": "click",
                "description": "Открыть панель лечения",
                "confidence": min(
                    0.78,
                    float(healing_overview.get("confidence", 0.88) or 0.88),
                ),
                "grayscale": True,
                "search_region": [1150, 430, 130, 190],
                "orb_match_threshold": 3,
                "routine_priority": 2,
                "runtime_step": "healing_overview",
                "allow_runtime_resume": True,
                "allow_repeat": True,
                "block_seconds": 1.0,
                "requires_settlement_screen": True,
            }
        )
        healing_overview.pop("required_setting_key", None)
        healing_overview.pop("required_setting_value", None)
        upgraded += 1

    for task_id, sequence in STRICT_RUNTIME_SEQUENCES.items():
        is_hunt = task_id in {"zombie_hunt", "collective_mind"}
        if is_hunt:
            region_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:region"))
            world_search_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:world_search"))
            region_image = images_by_uid.get(region_uid)
            if region_image is not None:
                region_image.update(
                    {
                        "action": "open_world_search",
                        "next_template_uid": world_search_uid,
                        "runtime_step": "world_search",
                        "routine_priority": 9,
                        "allow_repeat": True,
                        "block_seconds": 2.0,
                    }
                )
                region_image.pop("requires_runtime_steps", None)
                upgraded += 1

        previous_step = None
        for index, step_id in enumerate(sequence):
            uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:{step_id}"))
            image = images_by_uid.get(uid)
            if image is None:
                previous_step = step_id
                continue
            image["runtime_step"] = step_id
            image["routine_priority"] = 10 + index * 10
            image["allow_runtime_resume"] = True
            image["implied_runtime_steps"] = list(sequence[:index])
            if is_hunt:
                # A new hunt pass legitimately reuses the same search controls
                # and screen coordinates after a squad has returned home.
                image["allow_repeat"] = True
                image["block_seconds"] = 2.0
            if step_id == "march":
                image["confirm_disappears"] = True
            if task_id.startswith("train_") and step_id == "queue":
                image["repeat_runtime_step"] = True
                image["dynamic_building_search"] = True
                image["limit_key"] = "max_queue_checks"
                image["defer_when_limit_reached"] = True
                image["action"] = "select_training_queue"
                image["training_queue_ordinal"] = TRAINING_QUEUE_ORDINALS[task_id]
                image["training_radial_target"] = list(
                    TRAINING_RADIAL_TARGETS[task_id]
                )
                # Counters and the sleeping marker change the icon enough to
                # lower its score. The fixed HUD-region guard keeps 0.64 safe.
                image["confidence"] = min(
                    0.64,
                    float(image.get("confidence", 0.88) or 0.88),
                )
                image["training_queue_region"] = True
            if task_id == "heal" and step_id == "open_wounded":
                # Opening the stable healing overview row also collects a
                # completed batch, so troop-specific collection icons are not
                # required.
                image["action"] = "open_healing_hospital"
                image["allow_repeat"] = True
                image["block_seconds"] = 0.5
            if task_id == "heal" and step_id == "start_healing":
                # The form is verified again after this short settle time, so
                # a longer generic template delay only slows tiny heal batches.
                image["delay"] = min(
                    0.6,
                    float(image.get("delay", 0.8) or 0.8),
                )
            image.pop("requires_runtime_steps", None)
            selected_training_building = (
                task_id.startswith("train_") and step_id == "building"
            )
            if previous_step and not selected_training_building:
                image["requires_runtime_steps"] = [previous_step]
            previous_step = step_id
            upgraded += 1

    research_queue_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:queue"))
    research_queue = images_by_uid.get(research_queue_uid)
    if research_queue is not None:
        research_queue.update(
            {
                "action": "select_research_queue",
                "limit_key": "max_lab_checks",
                "defer_when_limit_reached": True,
            }
        )
        upgraded += 1

    for step_id in ("lab", "lab_alt_1"):
        research_lab = images_by_uid.get(
            str(uuid.uuid5(PROFILE_NAMESPACE, f"research:{step_id}"))
        )
        if research_lab is None:
            continue
        # Building labels vary slightly between levels and animated overlays.
        # The selected laboratory remains distinctive inside the research group.
        research_lab["confidence"] = min(
            0.84,
            float(research_lab.get("confidence", 0.88) or 0.88),
        )
        upgraded += 1

    active_boost_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "gathering_boost:active"))
    active_boost = images_by_uid.get(active_boost_uid)
    if active_boost is not None:
        active_boost.update(
            {
                "confidence": 0.75,
                "orb_match_threshold": 3,
                "completes_routine": True,
                "routine_priority": 1,
            }
        )
        upgraded += 1

    boost_24h_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "gathering_boost:boost_24h"))
    boost_24h = images_by_uid.get(boost_24h_uid)
    if boost_24h is not None:
        # Never consume a 24-hour item when the user selected 8 hours.
        boost_24h.pop("allow_higher_setting_fallback", None)
        upgraded += 1

    for step_id in ("event_entry", "intro_map", "unavailable"):
        image = images_by_uid.get(
            str(uuid.uuid5(PROFILE_NAMESPACE, f"wasteland_exploration:{step_id}"))
        )
        if image is None:
            continue
        image["repeat_runtime_step"] = False
        image["allow_repeat"] = False
        upgraded += 1

    mail_requirements = {
        "open_mail": (),
        "select_system": ("open_mail",),
        "claim_system": ("select_system",),
        # Claim buttons are optional when a mailbox category is already empty.
        "select_alliance": ("select_system",),
        "claim_alliance": ("select_alliance",),
        "select_reports": ("select_alliance",),
        "claim_reports": ("select_reports",),
    }
    for index, (step_id, required_steps) in enumerate(mail_requirements.items()):
        image = images_by_uid.get(
            str(uuid.uuid5(PROFILE_NAMESPACE, f"mail_rewards:{step_id}"))
        )
        if image is None:
            continue
        image["runtime_step"] = step_id
        image["routine_priority"] = 10 + index * 10
        if required_steps:
            image["requires_runtime_steps"] = list(required_steps)
        else:
            image.pop("requires_runtime_steps", None)
        upgraded += 1

    for task in tasks:
        if task.get("id") == "heal":
            task["interval_minutes"] = 0.1
            task["timeout_seconds"] = min(
                8.0,
                max(5.0, float(task.get("timeout_seconds", 8.0) or 8.0)),
            )
            task["empty_home_is_success"] = True
        elif task.get("id") in STRICT_RUNTIME_SEQUENCES:
            task["timeout_seconds"] = max(
                20.0,
                float(task.get("timeout_seconds", 0.0) or 0.0),
            )
        if task.get("id") == "zombie_hunt":
            task["interval_minutes"] = 0.1
            settings = task.setdefault("settings", {})
            settings.pop("level_min", None)
            settings.pop("level_max", None)
            settings["fallback_levels"] = zombie_fallback_levels(settings)
            task["march_completion_runtime_step"] = "march"
        if str(task.get("id") or "").startswith("train_"):
            settings = task.setdefault("settings", {})
            settings["max_queue_checks"] = max(
                5,
                int(settings.get("max_queue_checks", 0) or 0),
            )
        if task.get("id") == "research":
            settings = task.setdefault("settings", {})
            settings["max_lab_checks"] = max(
                2,
                int(settings.get("max_lab_checks", 0) or 0),
            )
        if task.get("id") == "wasteland_exploration":
            # Opening the event tile can return directly to the settlement for
            # an ineligible account. That is not a successful exploration run.
            task["empty_home_is_success"] = False
            task["completion_runtime_step"] = "stamina_empty"
        if task.get("id") == "mail_rewards":
            task["completion_runtime_step"] = "claim_reports"

    # Claiming a main mission can move the game directly to the daily tab.
    # Allow the first guarded swipe to resume from that screen even when the
    # explicit select_daily click was therefore never observed.
    first_daily_scroll = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "completed_tasks:scroll_daily_1"))
    )
    if first_daily_scroll is not None:
        first_daily_scroll["requires_runtime_steps"] = ["open_tasks"]
        first_daily_scroll["implied_runtime_steps"] = ["select_daily"]
        upgraded += 1

    claim_main = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "completed_tasks:claim_main"))
    )
    if claim_main is not None:
        # Both tabs use the same claim button. After the daily tab opens, the
        # match must advance claim_daily instead of repeating claim_main.
        claim_main["disabled_after_runtime_steps"] = ["select_daily"]
        upgraded += 1
    return upgraded


def upgrade_prize_hunt_metadata(images, tasks):
    """Keep the defeat and repeat buttons on separate safe branches."""
    images_by_uid = {str(image.get("uid") or ""): image for image in images}
    upgraded = 0

    campaign = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:campaign"))
    )
    if campaign is not None:
        # Decorations and notification badges alter this fixed bottom button.
        # ORB and color checks still provide the strict secondary validation.
        campaign["confidence"] = min(
            0.84,
            float(campaign.get("confidence", 0.88) or 0.88),
        )
        upgraded += 1

    open_squad = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:open_squad"))
    )
    if open_squad is not None:
        open_squad.update(
            {
                "action": "prize_start_or_prepare",
                "description": "Запустить охоту или настроить отряд",
                "grayscale": True,
                "confidence": min(
                    0.84,
                    float(open_squad.get("confidence", 0.88) or 0.88),
                ),
            }
        )
        upgraded += 1

    prepare = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:prepare"))
    )
    if prepare is not None:
        prepare.update(
            {
                "action": "prize_prepare",
                "description": "Заполнить отряд для охоты",
            }
        )
        upgraded += 1

    no_deployable_squad = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:no_deployable_squad"))
    )
    if no_deployable_squad is not None:
        no_deployable_squad.update(
            {
                "description": "Нет развертываемого отряда для охоты",
                "defer_routine_reason": "нет развертываемого отряда",
                "confidence": min(
                    0.82,
                    float(no_deployable_squad.get("confidence", 0.88) or 0.88),
                ),
            }
        )
        upgraded += 1

    safe_exit = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:safe_exit"))
    )
    if safe_exit is not None:
        safe_exit.update(
            {
                "required_setting_key": "repeat_until_stopped",
                "required_setting_value": False,
                "complete_if_setting_false": "repeat_until_stopped",
                "routine_priority": 20,
            }
        )
        upgraded += 1

    revive_exit = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:safe_exit_current"))
    )
    if revive_exit is not None:
        revive_exit.pop("required_setting_key", None)
        revive_exit.pop("required_setting_value", None)
        revive_exit.pop("complete_if_setting_false", None)
        revive_exit["routine_priority"] = 10
        upgraded += 1

    for priority, step_id in enumerate(("again", "match", "confirm"), start=20):
        image = images_by_uid.get(
            str(uuid.uuid5(PROFILE_NAMESPACE, f"prize_hunt:{step_id}"))
        )
        if image is None:
            continue
        image.update(
            {
                "required_setting_key": "repeat_until_stopped",
                "required_setting_value": True,
                "routine_priority": priority,
            }
        )
        upgraded += 1

    step_requirements = {
        "campaign": (),
        "event": ("campaign",),
        "enter": ("event",),
        "open_squad": ("enter",),
        "prepare": ("open_squad",),
        "no_deployable_squad": ("prepare", "open_squad"),
        "deploy": ("prepare",),
        "safe_exit_current": ("deploy",),
        "safe_exit": ("safe_exit_current",),
        "again": ("safe_exit_current",),
        "match": ("again",),
        "confirm": ("match",),
    }
    repeatable_steps = {"safe_exit_current", "safe_exit", "again", "match", "confirm"}
    for priority, (step_id, required_steps) in enumerate(step_requirements.items(), start=10):
        image = images_by_uid.get(
            str(uuid.uuid5(PROFILE_NAMESPACE, f"prize_hunt:{step_id}"))
        )
        if image is None:
            continue
        image["runtime_step"] = step_id
        image["routine_priority"] = priority
        image["repeat_runtime_step"] = step_id in repeatable_steps
        image.pop("allow_runtime_resume", None)
        image.pop("requires_runtime_steps", None)
        if required_steps:
            image["requires_runtime_steps"] = list(required_steps)

    deploy_image = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:deploy"))
    )
    if deploy_image is not None:
        # A previously saved squad can enter immediately; an empty squad must
        # first pass through prize_prepare. Both states are valid.
        deploy_image["requires_runtime_steps"] = ["prepare", "open_squad"]
        deploy_image["runtime_step_mode"] = "any"

    if no_deployable_squad is not None:
        # The game can reject either the initial squad setup or the final
        # deployment when this account has no event-compatible squad.
        no_deployable_squad["requires_runtime_steps"] = ["prepare", "open_squad"]
        no_deployable_squad["runtime_step_mode"] = "any"
        no_deployable_squad["allow_runtime_resume"] = True
        no_deployable_squad["routine_priority"] = 1

    outcome_steps = ("safe_exit_current", "safe_exit", "again")
    for step_id in outcome_steps:
        image = images_by_uid.get(
            str(uuid.uuid5(PROFILE_NAMESPACE, f"prize_hunt:{step_id}"))
        )
        if image is None:
            continue
        image["allow_runtime_resume"] = True
        image["runtime_step_mode"] = "any"
        if step_id == "safe_exit_current":
            image["requires_runtime_steps"] = ["deploy", "enter"]
        else:
            image["requires_runtime_steps"] = ["safe_exit_current", "deploy", "enter"]

    enter_image = images_by_uid.get(
        str(uuid.uuid5(PROFILE_NAMESPACE, "prize_hunt:enter"))
    )
    if enter_image is not None:
        # The event periodically changes the button caption while retaining
        # the same card and placement. The strict event prerequisite prevents
        # this relaxed threshold from matching outside the hunt screen.
        enter_image["confidence"] = min(
            0.74,
            float(enter_image.get("confidence", 0.8) or 0.8),
        )

    for task in tasks:
        if task.get("id") == "prize_hunt":
            task["timeout_seconds"] = max(
                1800.0,
                float(task.get("timeout_seconds", 0.0) or 0.0),
            )
    return upgraded


def upgrade_radar_runtime_metadata(images, tasks):
    """Apply the guarded radar flow to every independently selectable mode."""
    images_by_uid = {str(image.get("uid") or ""): image for image in images}
    upgraded = 0
    radar_tasks = [task for task in tasks if is_radar_task_id(task.get("id"))]
    for task in radar_tasks:
        task_id = str(task.get("id") or "")
        card_guard_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:card_guard"))
        forward_guard_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:forward_guard"))
        for step_id, priority in RADAR_STEP_PRIORITIES.items():
            uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:{step_id}"))
            image = images_by_uid.get(uid)
            if image is None:
                continue
            image["routine_priority"] = priority
            if step_id == "open_radar":
                image["enabled"] = True
            if task_id == "radar_rewards" and step_id == "open_any_task":
                image["enabled"] = False
            if step_id == "wait_in_progress":
                image["action"] = "radar_defer_in_progress"
                image["delay"] = 0.5
            if step_id == "march":
                image["confirm_disappears"] = True
                image["confirms_radar_marker"] = True
            if image.get("limit_key") == "max_tasks":
                image.pop("limit_key", None)
            if step_id.startswith("task_"):
                image["runtime_step"] = "radar_marker"
                image["repeat_runtime_step"] = True
                image["prevents_idle_completion"] = True
                image["skip_if_uid_visible"] = card_guard_uid
                image["requires_radar_notification"] = False
                image["confidence"] = min(0.68, float(image.get("confidence", 0.82)))
                image["orb_match_threshold"] = min(
                    3,
                    int(image.get("orb_match_threshold", 3) or 3),
                )
                image["allow_repeat"] = True
                image["block_seconds"] = 8.0
            elif step_id in {"open_any_task", "open_supply", "open_car", "open_zombie"}:
                image["runtime_step"] = "radar_forward"
                image["repeat_runtime_step"] = True
                image["requires_runtime_steps"] = ["radar_marker"]
                image["requires_visible_uid"] = (
                    card_guard_uid if step_id == "open_any_task" else forward_guard_uid
                )
            elif step_id in {
                "collect_completed",
                "collect_supply",
                "attack_zombie",
                "rescue_survivors",
                "transport_supplies",
                "confirm_transport",
            }:
                image["runtime_step"] = "radar_action"
                image["repeat_runtime_step"] = True
                image["requires_runtime_steps"] = ["radar_forward"]
                image["delay"] = max(1.5, float(image.get("delay", 0.0) or 0.0))
                if task_id == "radar_rewards" and step_id == "collect_completed":
                    image["requires_runtime_steps"] = ["radar_marker"]
            elif step_id == "create_squad":
                image["runtime_step"] = "radar_squad"
                image["requires_runtime_steps"] = ["radar_action"]
                image["allow_runtime_resume"] = True
            elif step_id == "march":
                image["runtime_step"] = "radar_march"
                image["requires_runtime_steps"] = ["radar_squad", "radar_action"]
                image["runtime_step_mode"] = "any"
                image["allow_runtime_resume"] = True
            elif step_id == "close_region_search":
                image["requires_runtime_steps"] = ["radar_action", "radar_march"]
                image["runtime_step_mode"] = "any"
            elif step_id == "return_shelter":
                image["action"] = "radar_return_shelter"
                image["requires_runtime_steps"] = [
                    "radar_action",
                    "radar_march",
                ]
                image["runtime_step_mode"] = "any"
                image.pop("completes_routine", None)
            upgraded += 1

    for task in radar_tasks:
        task_id = str(task.get("id") or "")
        task["timeout_seconds"] = max(12.0, float(task.get("timeout_seconds", 0.0) or 0.0))
        task["interval_minutes"] = 720.0
        task["complete_when_idle"] = True
        task["manual_screen_required"] = False
        task["idle_confirmations"] = max(2, int(task.get("idle_confirmations", 0) or 0))
        task["idle_completion_guard_uid"] = str(
            uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:radar_screen_guard")
        )
        if task_id == "radar_marches":
            task["march_completion_runtime_step"] = "radar_march"
        task.setdefault("settings", {})["fixed_utc_hours"] = [0, 12]
        task["settings"].setdefault("in_progress_retry_minutes", 5)
        task["settings"]["visual_fallback"] = True
    return upgraded


def _positive_float(value, default, minimum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return max(float(minimum), parsed)


def _normalize_settings(source, default):
    result = deepcopy(default or {})
    supplied = source if isinstance(source, dict) else {}
    result.update(supplied)
    return result


def _normalize_task(source, default):
    task_id = str(source.get("id", default["id"])).strip() or default["id"]
    name = str(source.get("name", default.get("name", task_id))).strip() or task_id
    if task_id == "alliance_help" and name == "Помощь альянсу":
        name = "Помощь другим игрокам"
    group = str(source.get("group", default["group"])).strip() or default["group"]
    uses_march = bool(source.get("uses_march", default.get("uses_march", False)))
    if task_id == "prize_hunt":
        # Prize Hunt uses its own event squad and is available even when all
        # regular world marches are occupied. This also migrates old configs.
        uses_march = False
    timeout_seconds = _positive_float(
        source.get("timeout_seconds"),
        default.get("timeout_seconds", 8.0),
        1.0,
    )
    if task_id == "game_login":
        # Older configs used 90 seconds, but stuck-start recovery intentionally
        # begins later. Keep enough time for both automatic restart attempts.
        timeout_seconds = max(
            float(default.get("timeout_seconds", 330.0)),
            timeout_seconds,
        )
    settings = _normalize_settings(source.get("settings"), default.get("settings"))
    if task_id == "zombie_hunt":
        settings.pop("level_min", None)
        settings.pop("level_max", None)
        settings["fallback_levels"] = zombie_fallback_levels(settings)
    return {
        "id": task_id,
        "name": name,
        "group": group,
        "category": str(source.get("category", default.get("category", "custom"))),
        "enabled": bool(source.get("enabled", default.get("enabled", True))),
        "standalone": bool(source.get("standalone", default.get("standalone", False))),
        "uses_march": uses_march,
        "priority": int(_positive_float(source.get("priority"), default.get("priority", 100), 1)),
        "interval_minutes": (
            0.1
            if task_id == "zombie_hunt"
            else _positive_float(
                source.get("interval_minutes"),
                default.get("interval_minutes", 1.0),
                0.1,
            )
        ),
        "timeout_seconds": timeout_seconds,
        "march_duration_minutes": _positive_float(
            source.get("march_duration_minutes"),
            default.get("march_duration_minutes", 30.0),
            1.0,
        ),
        "completion_uid": str(source.get("completion_uid", "") or ""),
        "completion_runtime_step": (
            "stamina_empty"
            if task_id == "wasteland_exploration"
            else str(
                source.get(
                    "completion_runtime_step",
                    default.get("completion_runtime_step", ""),
                )
                or ""
            )
        ),
        "march_completion_runtime_step": (
            "march"
            if task_id == "zombie_hunt"
            else str(
                source.get(
                    "march_completion_runtime_step",
                    default.get("march_completion_runtime_step", ""),
                )
                or ""
            )
        ),
        "manual_screen_required": bool(
            source.get(
                "manual_screen_required",
                default.get("manual_screen_required", False),
            )
        ),
        "complete_when_idle": bool(
            source.get("complete_when_idle", default.get("complete_when_idle", False))
        ),
        "empty_home_is_success": False
        if task_id == "wasteland_exploration"
        else task_id in {
            "fence_survivors",
            "vip_rewards",
            "research",
        }
        or bool(
            source.get(
                "empty_home_is_success",
                default.get("empty_home_is_success", False),
            )
        ),
        "idle_confirmations": int(
            _positive_float(
                source.get("idle_confirmations"),
                default.get("idle_confirmations", 1),
                1,
            )
        ),
        "idle_completion_guard_uid": str(
            source.get(
                "idle_completion_guard_uid",
                default.get("idle_completion_guard_uid", ""),
            )
            or ""
        ),
        "settings": settings,
    }


def normalize_routine_tasks(raw_tasks):
    """Return safe built-in settings and preserve user-created scenarios."""
    raw_by_id = {}
    if isinstance(raw_tasks, list):
        raw_by_id = {
            item.get("id"): item
            for item in raw_tasks
            if isinstance(item, dict) and item.get("id")
        }

    normalized_by_id = {}
    built_in_ids = {item["id"] for item in DEFAULT_ROUTINE_TASKS}
    retired_built_in_ids = {LEGACY_RADAR_TASK_ID}
    for default in DEFAULT_ROUTINE_TASKS:
        source = raw_by_id.get(default["id"], {})
        normalized_by_id[default["id"]] = _normalize_task(source, default)

    normalized = []
    added_ids = set()
    if isinstance(raw_tasks, list):
        for source in raw_tasks:
            if not isinstance(source, dict):
                continue
            task_id = source.get("id")
            if not task_id or task_id in added_ids or task_id in retired_built_in_ids:
                continue
            if task_id in built_in_ids:
                normalized.append(normalized_by_id[task_id])
                added_ids.add(task_id)
                continue
            fallback = {
                "id": str(task_id or "custom"),
                "name": "Новая задача",
                "group": "Новая задача",
                "category": "custom",
                "enabled": True,
                "uses_march": False,
                "priority": 100,
                "interval_minutes": 1.0,
                "timeout_seconds": 8.0,
                "march_duration_minutes": 30.0,
                "settings": {},
            }
            normalized.append(_normalize_task(source, fallback))
            added_ids.add(task_id)

    # New built-in tasks are appended without disturbing the order chosen by
    # the user in an older configuration.
    for default in DEFAULT_ROUTINE_TASKS:
        task_id = default["id"]
        if task_id not in added_ids:
            normalized.append(normalized_by_id[task_id])
    return normalized


def reorder_routine_tasks(tasks, ordered_ids):
    """Return tasks in the requested order and keep omitted tasks at the end."""
    tasks_by_id = {
        task.get("id"): task
        for task in tasks
        if isinstance(task, dict) and task.get("id")
    }
    reordered = []
    added_ids = set()
    for task_id in ordered_ids or ():
        if task_id in tasks_by_id and task_id not in added_ids:
            reordered.append(tasks_by_id[task_id])
            added_ids.add(task_id)
    for task in tasks:
        task_id = task.get("id") if isinstance(task, dict) else None
        if task_id and task_id not in added_ids:
            reordered.append(task)
            added_ids.add(task_id)
    return reordered


def effective_task_group(task):
    if task.get("id") == "research":
        return "Исследования"
    return task.get("group", "")


def is_task_effectively_enabled(task):
    if not task.get("enabled", False):
        return False
    if task.get("id") == "research":
        return task.get("settings", {}).get("branch", "off") != "off"
    return True


def pick_due_task_index(tasks, next_run, start_index, now, active_marches=0, max_marches=5):
    """Pick the next due task in the user-defined cyclic order."""
    if not tasks:
        return None
    start_index = int(start_index or 0) % len(tasks)
    candidates = []
    for offset in range(len(tasks)):
        index = (start_index + offset) % len(tasks)
        task = tasks[index]
        if not is_task_effectively_enabled(task):
            continue
        if task.get("uses_march", False) and int(active_marches) >= int(max_marches):
            continue
        deadline = float(next_run.get(task["id"], 0.0))
        if deadline <= float(now):
            # Finish the first pass before repeating a task that has already
            # run, then follow the visible order from start_index.
            first_attempt = 0 if deadline <= 0.0 else 1
            candidates.append((first_attempt, offset, index))
    return min(candidates)[2] if candidates else None


def training_queue_match_is_safe(bbox, display_width, display_height):
    """Keep the low-confidence training queue match inside its fixed HUD slot."""
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        return False
    try:
        left, top, width, height = map(float, bbox)
        display_width = float(display_width)
        display_height = float(display_height)
    except (TypeError, ValueError):
        return False
    if display_width <= 0 or display_height <= 0 or width <= 0 or height <= 0:
        return False
    center_x = left + width / 2.0
    center_y = top + height / 2.0
    return (
        center_x <= display_width * 0.13
        and display_height * 0.34 <= center_y <= display_height * 0.55
    )


def next_due_task(tasks, next_run, now, active_marches=0, max_marches=5):
    enabled = [
        task for task in tasks
        if is_task_effectively_enabled(task)
        and (not task.get("uses_march", False) or int(active_marches) < int(max_marches))
    ]
    if not enabled:
        return None, None
    task = min(enabled, key=lambda item: float(next_run.get(item["id"], 0.0)))
    wait_seconds = max(0.0, float(next_run.get(task["id"], 0.0)) - float(now))
    return task, wait_seconds


def next_run_after_finish(task, now):
    fixed_utc_hours = task.get("settings", {}).get("fixed_utc_hours", ())
    if fixed_utc_hours:
        return next_fixed_utc_run(now, fixed_utc_hours)
    if task.get("id") == "heal":
        return float(now) + healing_repeat_delay(task)
    interval_seconds = float(task.get("interval_minutes", 1.0)) * 60.0
    return float(now) + max(6.0, interval_seconds)


def next_run_after_radar_pass(task, now, has_in_progress=False):
    """Retry deferred radar marches soon, otherwise wait for the fixed reset."""
    if is_radar_task_id(task.get("id")) and has_in_progress:
        retry_minutes = _positive_float(
            task.get("settings", {}).get("in_progress_retry_minutes"),
            5.0,
            1.0,
        )
        return float(now) + retry_minutes * 60.0
    return next_run_after_finish(task, now)


def next_fixed_utc_run(now, hours):
    """Return the next configured UTC hour, never the current occurrence."""
    normalized_hours = sorted({int(hour) % 24 for hour in hours})
    if not normalized_hours:
        return float(now)

    current = datetime.fromtimestamp(float(now), tz=timezone.utc)
    for day_offset in (0, 1):
        day = current.date() + timedelta(days=day_offset)
        for hour in normalized_hours:
            candidate = datetime(
                day.year,
                day.month,
                day.day,
                hour,
                tzinfo=timezone.utc,
            )
            if candidate > current:
                return candidate.timestamp()
    raise RuntimeError("Unable to calculate the next fixed UTC run")
