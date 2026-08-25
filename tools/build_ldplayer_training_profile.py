from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from buzzbot.routines import (
    RESOURCE_RESULT_SEARCH_REGION,
    default_routine_tasks,
    is_radar_task_id,
    upgrade_radar_runtime_metadata,
    upgrade_prize_hunt_metadata,
    upgrade_repeatable_claim_metadata,
    upgrade_resource_runtime_metadata,
    upgrade_strict_runtime_metadata,
)
from buzzbot.version import APP_VERSION


TRAINING_DIR = PROJECT_ROOT / "build" / "training"
DEFAULT_PROFILE = TRAINING_DIR / "BuZzbot_Phoenix675_1280x720.zip"
PROFILE_NAMESPACE = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
SYSTEM_GROUP = "Системные окна"
ACCOUNT_SWITCH_GROUP = "Переключение аккаунта"
WASTELAND_GROUP = "Исследование пустоши"
RESOURCE_RESULT_LEVEL_TEMPLATES = {
    6: ("resource_level6_result.png", (628, 391, 661, 425)),
    7: ("resource_level7_result.png", (628, 391, 661, 425)),
}

RESOURCE_DATA = {
    "food": {
        "group": "Еда",
        "icon_source": "Phoenix675_panel_stable.png",
        "icon_box": (495, 552, 604, 665),
        "selected_source": "Phoenix675_food_selected_stable.png",
        "search_box": (455, 443, 641, 490),
        "target_source": "Phoenix675_food_node_collapsed.png",
        "target_box": (590, 310, 700, 401),
    },
    "wood": {
        "group": "Дерево",
        "icon_source": "Phoenix675_panel_stable.png",
        "icon_box": (660, 552, 771, 665),
        "selected_source": "Phoenix675_wood_selected.png",
        "search_box": (620, 443, 807, 490),
        "target_source": "Phoenix675_wood_node.png",
        "target_box": (585, 305, 685, 401),
    },
    "metal": {
        "group": "Металл",
        "icon_source": "Phoenix675_panel_stable.png",
        "icon_box": (822, 552, 933, 665),
        "selected_source": "Phoenix675_metal_selected.png",
        "search_box": (785, 443, 971, 490),
        "target_source": "Phoenix675_metal_node.png",
        "target_box": (585, 305, 690, 401),
    },
    "oil": {
        "group": "Нефть",
        "icon_source": "Phoenix675_food_selected_stable.png",
        "icon_box": (992, 552, 1102, 665),
        "selected_source": "Phoenix675_oil_selected.png",
        "search_box": (950, 443, 1136, 490),
        "target_source": "Phoenix675_oil_node.png",
        "target_box": (598, 305, 690, 401),
    },
}

COMMON_STEPS = (
    ("region", "Открыть регион", "Phoenix675_base_stable.png", (9, 590, 121, 718), (0, 0), False),
    ("world_search", "Открыть поиск", "Phoenix675_region_stable.png", (9, 413, 77, 480), (0, 0), False),
    ("gather", "Собрать ресурс", "Phoenix675_food_actions.png", (864, 476, 1066, 523), (0, 0), False),
    ("create_squad", "Создать отряд", "Phoenix675_squad.png", (878, 219, 1063, 270), (0, 0), False),
    ("march", "Отправить в поход", "Phoenix675_create_squad.png", (836, 618, 1065, 669), (0, 0), False),
)

SYSTEM_STEPS = (
    (
        "connection_interrupted",
        "Повторить вход после разрыва соединения",
        "zZuB2_connection_interrupted.png",
        (344, 294, 936, 540),
        (0, 91),
        False,
    ),
    (
        "loading_error_reload",
        "Перезагрузить страницу после ошибки загрузки",
        "zZuB1_loading_error_reload.png",
        (526, 449, 753, 518),
        (0, 0),
        False,
    ),
    (
        "last_igg_login",
        "Войти в последний IGG Account",
        "zZuB1_last_igg_login.png",
        (504, 504, 599, 603),
        (0, 0),
        False,
    ),
    (
        "idle_collect_confirm",
        "Подтвердить автосбор",
        "current_screen.png",
        (668, 618, 980, 670),
        (0, 0),
        False,
    ),
    (
        "glory_league_close",
        "Закрыть стартовый баннер",
        "Phoenix675_after_resume_confirm.png",
        (430, 300, 820, 390),
        (520, -235),
        False,
    ),
    (
        "beast_taming_close",
        "Закрыть акцию «Приручение зверей»",
        "Phoenix675_beast_taming_popup.png",
        (690, 108, 1142, 166),
        (266, -60),
        False,
    ),
    (
        "limited_quantity_offer_close",
        "Закрыть предложение с ограниченным набором",
        "zZuB1_limited_quantity_offer.png",
        (215, 90, 1065, 140),
        (453, 50),
        False,
    ),
    (
        "google_play_cancel",
        "Закрыть предложение Google Play Games",
        "zZuB4_google_play_profile.png",
        (159, 68, 320, 124),
        (0, 0),
        False,
    ),
    (
        "limited_trial_forward",
        "Продолжить ограниченное испытание",
        "radar_limited_trial_live.png",
        (398, 62, 882, 110),
        (-70, 470),
        False,
    ),
)

WASTELAND_STEPS = (
    (
        "event_entry",
        "Открыть исследование пустоши",
        "wasteland_event_entry.png",
        (775, 138, 865, 230),
        (0, 0),
        5.0,
        # Event tiles are reflowed as promotions appear and disappear. Keep
        # the search within the top event tray, but cover both observed rows.
        (350, 20, 650, 260),
    ),
    (
        "unavailable",
        "Аккаунт не допущен к исследованию пустоши",
        "wasteland_unavailable.png",
        (420, 485, 860, 530),
        (0, 0),
        0.5,
        (350, 430, 580, 130),
    ),
    (
        "intro_map",
        "Начать путь из безопасного лагеря",
        "wasteland_intro_map.png",
        (365, 535, 525, 650),
        (0, -10),
        1.5,
        (200, 430, 450, 260),
    ),
    (
        "attack",
        "Атаковать встречу пустоши",
        "wasteland_attack.png",
        (1035, 495, 1200, 665),
        (0, -12),
        3.0,
        (980, 430, 280, 280),
    ),
    (
        "bypass",
        "Обойти встречу после атаки",
        "wasteland_bypass.png",
        (865, 440, 975, 535),
        (0, 0),
        1.8,
        (820, 360, 220, 230),
    ),
    (
        "completed",
        "Исследовать найденный беспорядок",
        "wasteland_completed.png",
        (1040, 490, 1200, 670),
        (0, -12),
        1.8,
        (980, 430, 280, 280),
    ),
    (
        "collect",
        "Собрать сундук пустоши",
        "wasteland_collect.png",
        (1040, 490, 1200, 670),
        (0, -12),
        1.8,
        (980, 430, 280, 280),
    ),
    (
        "reward_close",
        "Закрыть награду исследования пустоши",
        "wasteland_reward.png",
        (420, 560, 860, 615),
        (0, 62),
        1.0,
        (350, 530, 580, 130),
    ),
    (
        "explore",
        "Разведать пустошь",
        "wasteland_base.png",
        (1035, 490, 1200, 670),
        (0, -12),
        2.0,
        (980, 430, 280, 280),
    ),
    (
        "stamina_empty",
        "Завершить проход без выносливости",
        "wasteland_stamina_empty.png",
        (465, 65, 820, 110),
        (428, -3),
        1.0,
        (350, 40, 750, 120),
    ),
)

ACCOUNT_SWITCH_STEPS = (
    ("profile", "Открыть профиль командира", "base_live_now.png", (18, 8, 91, 96), (0, 0), False),
    ("settings", "Открыть настройки", "profile_menu.png", (132, 603, 235, 704), (0, 0), False),
    ("account", "Открыть настройки аккаунта", "game_settings.png", (188, 284, 388, 459), (0, 0), False),
    ("switch", "Открыть смену аккаунта", "account_settings.png", (507, 594, 773, 642), (0, 0), False),
    ("google", "Выбрать вход Google", "account_switch_list.png", (774, 137, 868, 226), (0, 0), False),
    ("igg", "Выбрать вход IGG", "account_switch_list.png", (974, 137, 1078, 226), (0, 0), False),
    ("chooser", "Выбрать строку аккаунта Google", "google_account_chooser.png", (486, 179, 797, 214), (0, 0), False),
)

MARCH_OBSERVER_STEPS = (
    (1, "food_live_sent.png"),
    (2, "wood_sent_actual.png"),
    (3, "metal_sequence_result.png"),
    (4, "four_marches.png"),
    (5, "five_marches.png"),
)

DAILY_TASK_STEPS = {
    "alliance_help": (
        (
            "help_all",
            "Помочь всем участникам альянса",
            "base_live_now.png",
            (1208, 495, 1279, 561),
            (0, 0),
            False,
        ),
    ),
    "fence_survivors": (
        (
            "collect_question",
            "Собрать награду выжившего у забора",
            "home_promos_collapsed.png",
            (1163, 518, 1229, 592),
            (0, 0),
            False,
        ),
    ),
    "processing_factory": (
        (
            "pan_north",
            "Переместить камеру к заводу",
            "refinery_home_clear.png",
            (15, 415, 75, 476),
            (0, 0),
            False,
        ),
        (
            "select_refinery",
            "Найти свободный Завод по обработке",
            "refinery_pan_top.png",
            (800, 175, 960, 305),
            (0, 0),
            True,
        ),
        (
            "select_refinery_active",
            "Найти работающий Завод по обработке",
            "refinery_north_boundary.png",
            (800, 420, 1000, 610),
            (-40, 55),
            True,
        ),
        (
            "open_refinery",
            "Открыть Завод по обработке",
            "refinery_selected.png",
            (789, 292, 854, 370),
            (0, 0),
            False,
        ),
        (
            "open_refinery_boundary",
            "Открыть Завод по обработке после выравнивания камеры",
            "manual_select_retry.png",
            (785, 480, 855, 565),
            (0, 0),
            False,
        ),
        (
            "factory_guard",
            "Экран Завода по обработке открыт",
            "refinery_open.png",
            (81, 18, 388, 62),
            (0, 0),
            True,
        ),
        (
            "open_slot",
            "Открыть свободную линию обработки",
            "refinery_open.png",
            (608, 159, 696, 250),
            (0, 0),
            False,
        ),
        (
            "process_all",
            "Запустить все свободные линии",
            "refinery_slot_open.png",
            (371, 450, 623, 504),
            (0, 0),
            False,
        ),
    ),
    "processing_contest": (
        (
            "pan_north",
            "Переместить камеру к заводу",
            "refinery_home_clear.png",
            (15, 415, 75, 476),
            (0, 0),
            False,
        ),
        (
            "select_refinery",
            "Найти свободный Завод по обработке",
            "refinery_pan_top.png",
            (800, 175, 960, 305),
            (0, 0),
            True,
        ),
        (
            "select_refinery_active",
            "Найти работающий Завод по обработке",
            "refinery_north_boundary.png",
            (800, 420, 1000, 610),
            (-40, 55),
            True,
        ),
        (
            "open_refinery",
            "Открыть Завод по обработке",
            "refinery_selected.png",
            (789, 292, 854, 370),
            (0, 0),
            False,
        ),
        (
            "open_refinery_boundary",
            "Открыть Завод по обработке после выравнивания камеры",
            "manual_select_retry.png",
            (785, 480, 855, 565),
            (0, 0),
            False,
        ),
        (
            "open_contest",
            "Открыть Конкурс по обработке",
            "refinery_open.png",
            (7, 245, 130, 370),
            (0, 0),
            False,
        ),
        (
            "contest_guard",
            "Экран Конкурса по обработке открыт",
            "refinery_contest_after_claim.png",
            (80, 17, 465, 64),
            (0, 0),
            True,
        ),
        (
            "collect_all",
            "Собрать все награды конкурса",
            "refinery_contest.png",
            (570, 630, 880, 681),
            (0, 0),
            False,
        ),
    ),
    "mail_rewards": (
        (
            "open_mail",
            "Открыть почту",
            "home_mail_quests_live.png",
            (1214, 570, 1268, 626),
            (0, 0),
            False,
        ),
        (
            "select_system",
            "Открыть системные письма",
            "mail_screen_live.png",
            (384, 32, 486, 59),
            (0, 0),
            True,
        ),
        (
            "claim_system",
            "Прочитать и получить все системные письма",
            "mail_screen_live.png",
            (31, 657, 213, 708),
            (0, 0),
            False,
        ),
        (
            "close_rewards",
            "Закрыть страницу полученных наград",
            "mail_after_claim_all_live.png",
            (279, 120, 1001, 184),
            (0, 439),
            False,
        ),
        (
            "select_alliance",
            "Открыть письма альянса",
            "mail_screen_live.png",
            (221, 32, 309, 59),
            (0, 0),
            True,
        ),
        (
            "claim_alliance",
            "Прочитать и получить все письма альянса",
            "mail_alliance_tab_live.png",
            (31, 657, 213, 708),
            (0, 0),
            False,
        ),
        (
            "select_reports",
            "Открыть боевые отчёты",
            "mail_alliance_tab_live.png",
            (61, 32, 132, 59),
            (0, 0),
            True,
        ),
        (
            "claim_reports",
            "Прочитать все боевые отчёты",
            "mail_reports_tab_live.png",
            (31, 657, 213, 708),
            (0, 0),
            False,
        ),
    ),
    "completed_tasks": (
        (
            "open_tasks",
            "Открыть список заданий",
            "home_mail_quests_live.png",
            (14, 521, 84, 570),
            (0, 0),
            False,
        ),
        (
            "claim_main",
            "Получить награду основной миссии",
            "completed_tasks_screen_live.png",
            (1026, 356, 1207, 407),
            (0, 0),
            False,
        ),
        (
            "select_daily",
            "Открыть ежедневные миссии",
            "completed_tasks_screen_live.png",
            (19, 226, 145, 274),
            (0, 0),
            True,
        ),
        (
            "claim_daily",
            "Получить награду ежедневной миссии",
            "daily_tasks_screen_live.png",
            (1026, 374, 1207, 423),
            (0, 0),
            False,
        ),
        *(
            (
                f"scroll_daily_{index}",
                f"Прокрутить ежедневные миссии ({index}/4)",
                "daily_tasks_screen_live.png",
                (19, 226, 145, 274),
                (0, 0),
                True,
            )
            for index in range(1, 5)
        ),
        *(
            (
                f"scroll_top_{index}",
                f"Вернуться к наградам активности ({index}/4)",
                "daily_tasks_screen_live.png",
                (19, 226, 145, 274),
                (0, 0),
                True,
            )
            for index in range(1, 5)
        ),
        (
            "claim_activity_20",
            "Получить сундук активности 20",
            "daily_activity_rewards_live.png",
            (492, 158, 569, 248),
            (0, 0),
            False,
        ),
        (
            "claim_activity_40",
            "Получить сундук активности 40",
            "daily_activity_rewards_live.png",
            (650, 158, 727, 248),
            (0, 0),
            False,
        ),
        (
            "close_rewards",
            "Закрыть награды активности",
            "daily_chest20_after_live.png",
            (279, 120, 1001, 184),
            (0, 439),
            False,
        ),
    ),
    "vip_rewards": (
        (
            "open_vip",
            "Открыть VIP",
            "base_live_now.png",
            # Exclude the account-specific VIP level number from the template.
            (96, 40, 136, 77),
            (0, 0),
            False,
        ),
        (
            "claim_chest",
            "Получить ежедневную VIP-награду",
            "vip_live.png",
            (1025, 136, 1150, 255),
            (0, 0),
            False,
        ),
        (
            "dismiss_info",
            "Закрыть сведения о VIP-награде",
            "vip_after_chest.png",
            (327, 291, 630, 333),
            (632, 308),
            False,
        ),
        (
            "receive_free",
            "Получить бесплатную ежедневную VIP-награду",
            "vip_again.png",
            (638, 581, 875, 632),
            (0, 0),
            False,
        ),
        (
            "close_vip",
            "Закрыть VIP",
            "vip_live.png",
            (1159, 52, 1218, 114),
            (0, 0),
            False,
        ),
    ),
    "alliance_donations": (
        (
            "open_alliance",
            "Открыть альянс",
            "base_live_now.png",
            (940, 627, 997, 681),
            (0, 0),
            False,
        ),
        (
            "open_technology",
            "Открыть технологии альянса",
            "alliance_retry.png",
            (958, 551, 1060, 677),
            (0, 0),
            False,
        ),
        (
            "select_marked_project",
            "Выбрать отмеченный проект пожертвований",
            "alliance_technology_now.png",
            (88, 20, 323, 63),
            (0, 0),
            True,
        ),
        (
            "select_project_construction",
            "Проверить проект: строительство убежища",
            "alliance_technology_now.png",
            (630, 137, 720, 232),
            (0, 0),
            False,
        ),
        (
            "select_project_research",
            "Проверить проект: скорость исследований",
            "alliance_technology_now.png",
            (630, 270, 720, 365),
            (0, 0),
            False,
        ),
        (
            "select_project_zombies",
            "Проверить проект: охота на зомби",
            "alliance_technology_now.png",
            (630, 407, 720, 502),
            (0, 0),
            False,
        ),
        (
            "select_project_elite",
            "Проверить проект: план элиты",
            "alliance_technology_now.png",
            (630, 542, 720, 637),
            (0, 0),
            False,
        ),
        (
            "select_project_fire_water",
            "Проверить проект: сквозь огонь и воду",
            "alliance_technology_now.png",
            (248, 478, 338, 573),
            (0, 0),
            False,
        ),
        (
            "select_project_gathering_elite",
            "Проверить проект: сбор элиты",
            "alliance_technology_now.png",
            (248, 198, 338, 293),
            (0, 0),
            False,
        ),
        (
            "donate_resources",
            "Пожертвовать за обычные ресурсы",
            "alliance_donation_candidate.png",
            (858, 555, 1124, 606),
            (0, 0),
            False,
        ),
        (
            "close_project",
            "Закрыть проект без доступного пожертвования",
            "alliance_donation_candidate.png",
            (1094, 48, 1151, 96),
            (0, 0),
            False,
        ),
    ),
    "radar": (
        (
            "open_radar",
            "Открыть радарную станцию",
            "donation_run_start.png",
            (88, 426, 132, 471),
            (0, 0),
            False,
        ),
        (
            "radar_screen_guard",
            "Экран радарной станции открыт",
            "radar_map_current_live.png",
            (86, 18, 195, 61),
            (0, 0),
            False,
        ),
        (
            "task_supply",
            "Выбрать задание со сбросом припасов",
            "radar_after_supply.png",
            (842, 480, 892, 541),
            (0, 0),
            False,
        ),
        (
            "task_car",
            "Выбрать автомобильное задание",
            "radar_after_supply.png",
            (705, 446, 773, 526),
            (0, 0),
            False,
        ),
        (
            "task_car_current",
            "Выбрать текущее автомобильное задание",
            "radar_map_current_live.png",
            (762, 440, 830, 520),
            (0, 0),
            False,
        ),
        (
            "task_car_unstarted_live",
            "Выбрать непройденное автомобильное задание",
            "radar_map_unstarted_followup_live.png",
            (895, 132, 972, 229),
            (0, 0),
            False,
        ),
        (
            "task_special_unstarted_live",
            "Выбрать непройденное специальное задание",
            "radar_map_unstarted_followup_live.png",
            (798, 187, 874, 289),
            (0, 0),
            False,
        ),
        (
            "task_special_reward_followup",
            "Забрать награду специального задания",
            "radar_special_reward_live.png",
            (797, 184, 877, 292),
            (0, 0),
            False,
        ),
        (
            "task_car_reward_followup",
            "Забрать награду задания транспортировки",
            "radar_car_reward_followup_live.png",
            (894, 129, 976, 232),
            (0, 0),
            False,
        ),
        (
            "task_person_unstarted_followup",
            "Выбрать новое боевое задание",
            "radar_new_followup_tasks_live.png",
            (688, 354, 762, 454),
            (0, 0),
            False,
        ),
        (
            "task_supply_unstarted_followup",
            "Выбрать новый сброс припасов",
            "radar_new_followup_tasks_live.png",
            (957, 178, 1035, 274),
            (0, 0),
            False,
        ),
        (
            "task_supply_reward_final",
            "Забрать финальную награду сброса припасов",
            "radar_final_followup_live.png",
            (970, 331, 1054, 430),
            (0, 0),
            False,
        ),
        (
            "task_car_unstarted_final",
            "Выбрать финальное автомобильное задание",
            "radar_final_followup_live.png",
            (957, 177, 1036, 274),
            (0, 0),
            False,
        ),
        (
            "task_person_gold_reward",
            "Забрать золотую награду задания радара",
            "radar_gold_remaining_live.png",
            (708, 321, 792, 426),
            (0, 0),
            False,
        ),
        (
            "task_car_generic_shape",
            "Выбрать коричневое автомобильное задание",
            "radar_generic_shapes_live.png",
            (894, 132, 974, 233),
            (0, 0),
            False,
        ),
        (
            "task_person_generic_shape",
            "Выбрать красное боевое задание",
            "radar_generic_shapes_live.png",
            (713, 326, 787, 426),
            (0, 0),
            False,
        ),
        (
            "task_special_generic_shape",
            "Выбрать фиолетовое специальное задание",
            "radar_special_generic_live.png",
            (797, 185, 876, 291),
            (0, 0),
            False,
        ),
        (
            "task_zombie",
            "Выбрать боевое задание",
            "radar_after_supply.png",
            (608, 346, 674, 430),
            (0, 0),
            False,
        ),
        (
            "task_skull_current",
            "Выбрать текущее боевое задание",
            "radar_map_after_march_live.png",
            (707, 320, 789, 415),
            (0, 0),
            False,
        ),
        (
            "task_skull_unstarted_live",
            "Выбрать непройденное боевое задание",
            "radar_map_remaining_second_live.png",
            (752, 236, 826, 331),
            (0, 0),
            False,
        ),
        (
            "task_survivor_current_live",
            "Выбрать непройденное задание выживших",
            "radar_map_remaining_second_live.png",
            (697, 325, 764, 430),
            (0, 0),
            False,
        ),
        (
            "task_skull_reward",
            "Забрать награду готового боевого задания",
            "radar_completed_card_live.png",
            (703, 335, 792, 441),
            (0, 0),
            False,
        ),
        (
            "task_skull_reward_current",
            "Забрать текущую награду боевого задания",
            "radar_map_remaining_live.png",
            (655, 328, 747, 440),
            (0, 0),
            False,
        ),
        (
            "task_special_current",
            "Выбрать текущее особое задание",
            "radar_map_after_march_live.png",
            (355, 506, 426, 600),
            (0, 0),
            False,
        ),
        (
            "task_fist_current",
            "Выбрать текущее задание схватки",
            "radar_map_remaining_live.png",
            (832, 476, 906, 570),
            (0, 0),
            False,
        ),
        (
            "task_supply_ready",
            "Выбрать готовый сброс припасов",
            "radar_ready_markers_live.png",
            (576, 145, 646, 231),
            (0, 0),
            False,
        ),
        (
            "task_car_ready",
            "Выбрать готовое автомобильное задание",
            "radar_ready_markers_live.png",
            (656, 212, 730, 305),
            (0, 0),
            False,
        ),
        (
            "task_car_reward",
            "Забрать награду автомобильного задания",
            "radar_map_after_march_live.png",
            (645, 227, 724, 326),
            (0, 0),
            False,
        ),
        (
            "task_zombie_ready",
            "Выбрать готовое боевое задание",
            "radar_ready_markers_live.png",
            (605, 442, 682, 539),
            (0, 0),
            False,
        ),
        (
            "open_supply",
            "Перейти к сбросу припасов",
            "radar_task_supply.png",
            (68, 151, 425, 197),
            (-2, 447),
            False,
        ),
        (
            "open_any_task",
            "Перейти к открытому заданию радара",
            "radar_task_supply.png",
            (112, 597, 375, 645),
            (0, 0),
            False,
        ),
        (
            "open_car",
            "Запустить автомобильное задание",
            "radar_task_car.png",
            (68, 151, 425, 197),
            (-2, 447),
            False,
        ),
        (
            "open_zombie",
            "Перейти к боевому заданию",
            "radar_task_person.png",
            (68, 151, 425, 197),
            (-2, 447),
            False,
        ),
        (
            "card_guard",
            "Карточка задания радара открыта",
            "radar_task_supply.png",
            (78, 410, 280, 454),
            (0, 0),
            False,
        ),
        (
            "forward_guard",
            "Кнопка ВПЕРЕД в карточке радара",
            "radar_task_supply.png",
            (112, 597, 375, 645),
            (0, 0),
            False,
        ),
        (
            "wait_in_progress",
            "Ожидать завершения задания радара",
            "radar_wait_running_live.png",
            (136, 597, 263, 635),
            (0, 0),
            False,
        ),
        (
            "collect_completed",
            "Получить награду выполненного задания радара",
            "radar_completed_card_live.png",
            (112, 596, 377, 646),
            (0, 0),
            False,
        ),
        (
            "collect_supply",
            "Собрать сброшенные припасы",
            "radar_supply_go.png",
            (855, 496, 1081, 544),
            (0, 0),
            False,
        ),
        (
            "attack_zombie",
            "Атаковать зомби по заданию радара",
            "radar_person_go.png",
            (868, 509, 1064, 553),
            (0, 0),
            False,
        ),
        (
            "rescue_survivors",
            "Спасти выживших по заданию радара",
            "radar_rescue_survivors_live.png",
            (855, 495, 1081, 543),
            (0, 0),
            False,
        ),
        (
            "transport_supplies",
            "Транспортировать припасы по заданию радара",
            "radar_transport_panel_live.png",
            (855, 544, 1080, 594),
            (0, 0),
            False,
        ),
        (
            "confirm_transport",
            "Подтвердить транспортировку припасов",
            "radar_transport_confirm_live.png",
            (443, 174, 832, 211),
            (152, 314),
            False,
        ),
        (
            "create_squad",
            "Создать отряд для задания радара",
            "radar_create_squad_current_live.png",
            (880, 221, 1061, 269),
            (0, 0),
            False,
        ),
        (
            "march",
            "Отправить отряд на задание радара",
            "radar_squad_screen_live.png",
            (838, 618, 1064, 667),
            (0, 0),
            False,
        ),
        (
            "no_deployable_squad",
            "Нет доступного отряда для задания радара",
            "radar_no_deployable_squad_live.png",
            (862, 614, 1065, 668),
            (0, 0),
            True,
        ),
        (
            "close_region_search",
            "Закрыть поиск региона после задания радара",
            "Phoenix675_radar_region_search_stuck.png",
            (25, 265, 410, 338),
            (-177, -264),
            False,
        ),
        (
            "return_shelter",
            "Вернуться в убежище после задания радара",
            "radar_supply_go.png",
            (8, 598, 122, 718),
            (0, 0),
            False,
        ),
    ),
    "heal": (
        (
            "collect_finished",
            "Собрать вылеченные войска",
            "hospital_finished_base.png",
            (1048, 137, 1094, 180),
            (0, 0),
            False,
        ),
        (
            "collect_finished_alt_1",
            "Открыть панель лечения",
            "LDPlayer0_heal_finished_alt.png",
            (1200, 490, 1280, 570),
            (0, 0),
            False,
        ),
        (
            "open_wounded",
            "Открыть госпиталь с ранеными",
            "base_pan_north.png",
            (1058, 134, 1108, 179),
            (0, 0),
            True,
        ),
        (
            "start_healing",
            "Начать лечение обычными ресурсами",
            "hospital_found.png",
            (903, 594, 1152, 643),
            (0, 0),
            False,
        ),
    ),
}

_RADAR_ALL_STEPS = DAILY_TASK_STEPS.pop("radar")
_RADAR_COMMON_STEP_IDS = {
    "radar_screen_guard",
    "card_guard",
    "forward_guard",
    "wait_in_progress",
    "close_region_search",
    "return_shelter",
}
_RADAR_REWARD_STEP_IDS = {
    "task_special_reward_followup",
    "task_car_reward_followup",
    "task_supply_reward_final",
    "task_person_gold_reward",
    "task_skull_reward",
    "task_skull_reward_current",
    "task_car_reward",
    "task_supply_ready",
    "task_car_ready",
    "task_zombie_ready",
    "collect_completed",
}
_RADAR_QUICK_STEP_IDS = {
    "task_supply",
    "task_car",
    "task_car_current",
    "task_car_unstarted_live",
    "task_special_unstarted_live",
    "task_supply_unstarted_followup",
    "task_car_unstarted_final",
    "task_car_generic_shape",
    "task_special_generic_shape",
    "open_any_task",
    "open_supply",
    "open_car",
    "collect_supply",
    "transport_supplies",
    "confirm_transport",
}
_RADAR_MARCH_STEP_IDS = {
    "task_person_unstarted_followup",
    "task_person_generic_shape",
    "task_zombie",
    "task_skull_current",
    "task_skull_unstarted_live",
    "task_survivor_current_live",
    "task_special_current",
    "task_fist_current",
    "open_any_task",
    "open_zombie",
    "attack_zombie",
    "rescue_survivors",
    "create_squad",
    "march",
    "no_deployable_squad",
}


def _radar_steps(step_ids):
    allowed = _RADAR_COMMON_STEP_IDS | set(step_ids)
    return tuple(step for step in _RADAR_ALL_STEPS if step[0] in allowed)


DAILY_TASK_STEPS.update(
    {
        "radar_rewards": _radar_steps(_RADAR_REWARD_STEP_IDS),
        "radar_quick": _radar_steps(_RADAR_QUICK_STEP_IDS),
        "radar_marches": _radar_steps(_RADAR_MARCH_STEP_IDS),
    }
)

TRAINING_DATA = {
    "train_infantry": {
        "selection_source": "left_crosshair.png",
        "title_box": (526, 193, 690, 228),
        "train_target": (758, 487),
        "screen_source": "infantry_train.png",
    },
    "train_riders": {
        "selection_source": "training_next.png",
        "title_box": (526, 193, 690, 228),
        "train_target": (758, 487),
        "screen_source": "riders_train.png",
    },
    "train_shooters": {
        "selection_source": "training_third.png",
        "title_box": (526, 193, 690, 228),
        "train_target": (758, 487),
        "screen_source": "shooters_train.png",
        "alternate_selections": (
            ("zZuB1_shooter_radial.png", (526, 193, 690, 228), (758, 487)),
            ("training_radial_generic.png", (526, 193, 690, 228), (758, 487)),
        ),
    },
    "train_vehicles": {
        "selection_source": "vehicle_radial.png",
        "title_box": (522, 193, 690, 228),
        "train_target": (780, 465),
        "screen_source": "vehicles_train.png",
        "alternate_selections": (
            ("zZuB1_vehicle_radial.png", (526, 193, 690, 228), (758, 487)),
        ),
    },
}

RESEARCH_STEPS = {
    "queue_box": (12, 218, 87, 278),
    "guard_source": "research_lab_radial.png",
    "guard_box": (526, 183, 690, 234),
    "research_target": (755, 475),
    "alternate_guards": (
        ("zZuB1_research_radial.png", (526, 183, 690, 234), (755, 475)),
    ),
    "menu_source": "research_menu.png",
    "menu_box": (430, 18, 850, 62),
    "confirm_source": "research_detail.png",
    "confirm_box": (855, 554, 1118, 604),
}

GATHERING_BOOST_STEPS = {
    "active": ("FocusFarm_boost_active.png", (89, 125, 143, 181)),
    "open_bag": ("base_live_now.png", (837, 601, 919, 707)),
    "boost_category": ("bag.png", (0, 267, 165, 347)),
    # Inventory counts change between accounts, so keep them outside the match crop.
    "boost_8h": ("boosts.png", (606, 123, 725, 205)),
    "boost_24h": ("boosts.png", (746, 123, 858, 205)),
    "use": ("boost_gather_selected.png", (943, 633, 1208, 681)),
}

ZOMBIE_STEPS = (
    ("region", "Открыть регион", "Phoenix675_base_stable.png", (9, 590, 121, 718), (0, 0), False),
    ("world_search", "Открыть поиск", "Phoenix675_region_stable.png", (9, 413, 77, 480), (0, 0), False),
    ("zombie_icon", "Выбрать поиск зомби", "zombie_search_panel.png", (180, 540, 240, 630), (0, 0), False),
    ("search", "Найти зомби заданного уровня", "zombie_search_panel.png", (126, 443, 307, 489), (0, 0), False),
    ("attack", "Атаковать найденных зомби", "zombie_actions.png", (868, 539, 1064, 583), (0, 0), False),
    ("create_squad", "Создать отряд для охоты", "radar_zombie_attack.png", (880, 187, 1061, 268), (0, 0), False),
    ("march", "Отправить отряд на зомби", "hivemind_squad.png", (839, 620, 1062, 667), (0, 0), False),
)

HIVEMIND_STEPS = (
    ("region", "Открыть регион", "Phoenix675_base_stable.png", (9, 590, 121, 718), (0, 0), False),
    ("world_search", "Открыть поиск", "Phoenix675_region_stable.png", (9, 413, 77, 480), (0, 0), False),
    ("leader_icon", "Выбрать коллективный разум", "leader_search_panel.png", (350, 565, 415, 640), (0, 0), False),
    ("search", "Найти коллективный разум", "leader_search_panel.png", (291, 443, 475, 489), (0, 0), False),
    ("no_result", "Коллективный разум выбранного уровня не найден", "FocusFarm_collective_no_result.png", (161, 113, 1120, 167), (0, 0), True),
    ("rally", "Создать сбор на коллективный разум", "hivemind_actions.png", (990, 519, 1169, 565), (0, 0), False),
    ("confirm_rally", "Подтвердить сбор на 5 минут", "hivemind_rally_setup_free.png", (814, 257, 992, 304), (0, 0), False),
    ("march", "Отправить отряд на совместную атаку", "hivemind_squad.png", (839, 620, 1062, 667), (0, 0), False),
)

PRIZE_HUNT_STEPS = (
    ("campaign", "Открыть кампанию", "hivemind_rally_started.png", (742, 601, 824, 708), (0, 0), False),
    ("event", "Открыть охоту за призом", "campaign_menu.png", (905, 516, 1175, 579), (0, 0), False),
    ("enter", "Войти в охоту за призом", "prize_hunt_menu.png", (465, 500, 811, 584), (0, 0), False),
    ("open_squad", "Запустить охоту или настроить отряд", "prize_hunt_pairing.png", (535, 515, 746, 567), (0, 0), True),
    ("prepare", "Заполнить отряд для охоты", "prize_hunt_ready.png", (861, 619, 1063, 667), (0, 0), False),
    (
        "no_deployable_squad",
        "Нет развертываемого отряда для охоты",
        "prize_hunt_no_deployable_squad.png",
        (370, 299, 910, 369),
        (0, 175),
        True,
    ),
    ("deploy", "Отправить отряд на охоту", "prize_hunt_manual_fill.png", (862, 619, 1063, 667), (0, 0), False),
    ("safe_exit", "Выйти после поражения без возрождения", "prize_hunt_result_after_exit.png", (615, 581, 871, 652), (0, 0), False),
    ("safe_exit_current", "Выйти после поражения без возрождения", "FocusFarm_prize_defeat.png", (430, 335, 598, 485), (0, 0), False),
    ("again", "Повторить охоту", "prize_hunt_result_after_exit.png", (934, 581, 1192, 652), (0, 0), False),
    ("match", "Начать повторный подбор", "prize_hunt_again.png", (465, 500, 811, 584), (0, 0), False),
    ("confirm", "Подтвердить повторный подбор", "prize_hunt_repeat_result.png", (651, 485, 917, 534), (0, 0), False),
)


def load_image(name):
    image = cv2.imread(str(TRAINING_DIR / name), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(TRAINING_DIR / name)
    if image.shape[:2] != (720, 1280):
        raise ValueError(f"Unexpected image size for {name}: {image.shape[1]}x{image.shape[0]}")
    return image


def crop_image(source_name, box):
    source = load_image(source_name)
    left, top, right, bottom = box
    crop = source[top:bottom, left:right].copy()
    if crop.size == 0:
        raise ValueError(f"Empty crop: {source_name} {box}")
    return source, crop


def verify_crop(source, crop, grayscale):
    if grayscale:
        source = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(source, crop, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    if score < 0.99:
        raise ValueError(f"Template verification failed: {score:.3f}")
    return float(score)


def image_config(uid, entry_name, group, description, offset, grayscale, delay):
    return {
        "uid": uid,
        "path": entry_name,
        "action": "click",
        "delay": delay,
        "confidence": 0.88,
        "grayscale": grayscale,
        "description": description,
        "enabled": True,
        "click_offset": list(offset),
        "numbers": [],
        "click_sequence": [],
        "last_used": 0,
        "cooldown": 0.5,
        "group": group,
        "use_scaling": False,
    }


def build_profile(destination):
    destination = Path(destination)
    staging = TRAINING_DIR / "profile_templates"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    tasks = default_routine_tasks()
    for task in tasks:
        if task["id"] in RESOURCE_DATA:
            task["timeout_seconds"] = 30.0
            task["march_duration_minutes"] = 240.0
        elif task["id"] == "prize_hunt":
            task["enabled"] = False

    manifest = {
        "format": "doomsday-training-profile",
        "format_version": 1,
        "app_version": APP_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_screen": {"width": 1280, "height": 720},
        "routine_tasks": tasks,
        "routine_max_marches": 5,
        "groups": {
            **{task["group"]: task["enabled"] for task in tasks},
            SYSTEM_GROUP: True,
            ACCOUNT_SWITCH_GROUP: True,
        },
        "matching": {"scale_enabled": False, "scale_min": 0.9, "scale_max": 1.2},
        "images": [],
    }
    payloads = []

    for level, (source_name, box) in RESOURCE_RESULT_LEVEL_TEMPLATES.items():
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"resource_result_level:{level}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, True)
        output_path = staging / f"resource_result_level_{level}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        level_image = image_config(
            uid,
            entry_name,
            SYSTEM_GROUP,
            f"Подтверждение найденного ресурса уровня {level}",
            (0, 0),
            True,
            0.0,
        )
        level_image.update(
            {
                "enabled": False,
                "observer_only": True,
                "guard_only": True,
                "confidence": 0.65,
                "search_region": list(RESOURCE_RESULT_SEARCH_REGION),
            }
        )
        manifest["images"].append(level_image)
        payloads.append((output_path, entry_name))
        print(f"{'resource_level':15s} {level!s:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    for step_id, description, source_name, box, offset, grayscale in SYSTEM_STEPS:
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"system:{step_id}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, grayscale)
        output_path = staging / f"system_{step_id}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        system_image = image_config(uid, entry_name, SYSTEM_GROUP, description, offset, grayscale, 0.8)
        system_image["allow_repeat"] = True
        system_image["block_seconds"] = 3.0
        if step_id in {
            "connection_interrupted",
            "loading_error_reload",
            "last_igg_login",
            "glory_league_close",
            "beast_taming_close",
            "limited_quantity_offer_close",
            "limited_trial_forward",
            "google_play_cancel",
        }:
            system_image["startup_only"] = True
        if step_id in {
            "connection_interrupted",
            "loading_error_reload",
            "last_igg_login",
            "google_play_cancel",
        }:
            system_image["delay"] = 8.0
        manifest["images"].append(system_image)
        payloads.append((output_path, entry_name))
        print(f"system {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    for march_count, source_name in MARCH_OBSERVER_STEPS:
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"system:marches:{march_count}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, (1194, 150, 1274, 188))
        score = verify_crop(source, crop, True)
        output_path = staging / f"system_marches_{march_count}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        observer = image_config(
            uid,
            entry_name,
            SYSTEM_GROUP,
            f"Занято походов: {march_count}/5",
            (0, 0),
            True,
            0.0,
        )
        observer["observer_only"] = True
        observer["march_count"] = march_count
        observer["observer_confidence"] = 0.70
        manifest["images"].append(observer)
        payloads.append((output_path, entry_name))
        print(f"system marches_{march_count: <7} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    for step_id, description, source_name, box, offset, grayscale in ACCOUNT_SWITCH_STEPS:
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"account_switch:{step_id}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, grayscale)
        output_path = staging / f"account_switch_{step_id}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        configured_image = image_config(
            uid, entry_name, ACCOUNT_SWITCH_GROUP, description, offset, grayscale, 1.0
        )
        configured_image["use_orb"] = False
        if step_id == "chooser":
            configured_image["action"] = "google_account_select"
        if step_id in {"google", "chooser"}:
            configured_image["required_setting_key"] = "login_method"
            configured_image["required_setting_value"] = "google"
        elif step_id == "igg":
            configured_image["required_setting_key"] = "login_method"
            configured_image["required_setting_value"] = "igg"
        manifest["images"].append(configured_image)
        payloads.append((output_path, entry_name))
        print(f"{'account_switch':15s} {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    for step_id, description, source_name, box, offset, delay, search_region in WASTELAND_STEPS:
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"wasteland_exploration:{step_id}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, False)
        output_path = staging / f"wasteland_exploration_{step_id}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        configured_image = image_config(
            uid,
            entry_name,
            WASTELAND_GROUP,
            description,
            offset,
            False,
            delay,
        )
        configured_image.update(
            {
                "runtime_step": step_id,
                "repeat_runtime_step": step_id not in {"event_entry", "intro_map", "unavailable"},
                "allow_repeat": step_id not in {"event_entry", "intro_map", "unavailable"},
                "block_seconds": max(0.8, min(3.0, delay)),
                "confidence": 0.82,
                "search_region": list(search_region),
                "use_orb": True,
                "orb_match_threshold": 3,
            }
        )
        if step_id == "reward_close":
            configured_image["limit_key"] = "max_encounters"
        elif step_id == "stamina_empty":
            configured_image["completes_routine"] = True
        elif step_id == "unavailable":
            configured_image["action"] = "observe"
            configured_image["defer_routine_reason"] = (
                "аккаунт не зарегистрирован в исследовании пустоши"
            )
        manifest["images"].append(configured_image)
        payloads.append((output_path, entry_name))
        print(
            f"{'wasteland':15s} {step_id:15s} "
            f"score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}"
        )

    for task_id, steps in DAILY_TASK_STEPS.items():
        task = next(item for item in tasks if item["id"] == task_id)
        completion_uid = ""
        for step_id, description, source_name, box, offset, grayscale in steps:
            uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:{step_id}"))
            entry_name = f"templates/{uid}.png"
            source, crop = crop_image(source_name, box)
            score = verify_crop(source, crop, grayscale)
            output_path = staging / f"{task_id}_{step_id}.png"
            if not cv2.imwrite(str(output_path), crop):
                raise OSError(f"Could not write {output_path}")
            configured_image = image_config(
                uid,
                entry_name,
                task["group"],
                description,
                offset,
                grayscale,
                0.8,
            )
            if task_id == "alliance_donations" and step_id == "donate_resources":
                configured_image["limit_key"] = "max_donations"
                configured_image["allow_repeat"] = True
                configured_image["block_seconds"] = 0.8
            if task_id == "alliance_donations" and step_id == "select_marked_project":
                configured_image.update(
                    {
                        "action": "alliance_marked_project",
                        "routine_priority": 15,
                        "confidence": 0.78,
                        "orb_match_threshold": 3,
                        "delay": 1.5,
                    }
                )
            if task_id == "alliance_donations" and step_id == "close_project":
                configured_image["limit_key"] = "max_project_checks"
                configured_image["allow_repeat"] = True
                configured_image["block_seconds"] = 1.0
                configured_image["skip_if_visible_uids"] = [
                    str(uuid.uuid5(PROFILE_NAMESPACE, "alliance_donations:donate_resources"))
                ]
            if task_id == "alliance_donations" and step_id == "open_alliance":
                configured_image["home_screen_marker"] = True
            if task_id == "vip_rewards" and step_id in {"claim_chest", "dismiss_info", "receive_free"}:
                configured_image["allow_repeat"] = True
                configured_image["block_seconds"] = 0.8 if step_id == "dismiss_info" else 1.0
                configured_image["routine_priority"] = {
                    "claim_chest": 20,
                    "dismiss_info": 30,
                    "receive_free": 40,
                }[step_id]
                if step_id == "receive_free":
                    configured_image["completes_routine"] = True
            if task_id == "vip_rewards" and step_id == "open_vip":
                configured_image["routine_priority"] = 10
            if task_id == "vip_rewards" and step_id == "close_vip":
                configured_image["routine_priority"] = 50
                configured_image["skip_if_visible_uids"] = [
                    str(uuid.uuid5(PROFILE_NAMESPACE, "vip_rewards:claim_chest")),
                    str(uuid.uuid5(PROFILE_NAMESPACE, "vip_rewards:dismiss_info")),
                    str(uuid.uuid5(PROFILE_NAMESPACE, "vip_rewards:receive_free")),
                ]
            if is_radar_task_id(task_id):
                configured_image["allow_repeat"] = True
                configured_image["block_seconds"] = 2.0
                configured_image["confidence"] = 0.82
                configured_image["orb_match_threshold"] = 5
                card_guard_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "radar:card_guard"))
                forward_guard_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "radar:forward_guard"))
                if step_id in {"radar_screen_guard", "card_guard", "forward_guard"}:
                    configured_image["guard_only"] = True
                if step_id == "open_radar":
                    configured_image["requires_settlement_screen"] = True
                if step_id == "open_any_task":
                    configured_image["requires_visible_uid"] = card_guard_uid
                if step_id in {"open_supply", "open_car", "open_zombie"}:
                    configured_image["requires_visible_uid"] = forward_guard_uid
                if step_id.startswith("task_"):
                    configured_image["skip_if_uid_visible"] = card_guard_uid
                    configured_image["prevents_idle_completion"] = True
                    # Radar markers vary slightly between accounts and map positions.
                    # Keep color matching strict, but accept a small ORB keypoint set.
                    configured_image["orb_match_threshold"] = 3
                if step_id == "wait_in_progress":
                    configured_image["action"] = "radar_defer_in_progress"
                    configured_image["delay"] = 0.5
                if step_id == "attack_zombie":
                    configured_image["action"] = "zombie_attack"
                if step_id in {
                    "collect_completed",
                    "collect_supply",
                    "attack_zombie",
                    "rescue_survivors",
                    "transport_supplies",
                    "confirm_transport",
                }:
                    configured_image["requires_runtime_steps"] = ["radar_forward"]
                    configured_image["delay"] = 1.5
                    if task_id == "radar_rewards" and step_id == "collect_completed":
                        configured_image["requires_runtime_steps"] = ["radar_marker"]
                if step_id == "create_squad":
                    configured_image["runtime_step"] = "radar_squad"
                    configured_image["requires_runtime_steps"] = ["radar_action"]
                    configured_image["allow_runtime_resume"] = True
                if step_id == "march":
                    configured_image["runtime_step"] = "radar_march"
                    configured_image["requires_runtime_steps"] = [
                        "radar_squad",
                        "radar_action",
                    ]
                    configured_image["runtime_step_mode"] = "any"
                    configured_image["allow_runtime_resume"] = True
                if step_id == "no_deployable_squad":
                    configured_image["action"] = "observe"
                    configured_image["defer_routine_reason"] = (
                        "нет доступного отряда для задания радара"
                    )
                    configured_image["confidence"] = 0.80
                if step_id == "close_region_search":
                    configured_image["requires_runtime_steps"] = [
                        "radar_action",
                        "radar_march",
                    ]
                    configured_image["runtime_step_mode"] = "any"
                if step_id == "return_shelter":
                    configured_image["action"] = "radar_return_shelter"
                    configured_image["requires_runtime_steps"] = [
                        "radar_action",
                        "radar_march",
                    ]
                    configured_image["runtime_step_mode"] = "any"
            if task_id == "heal" and step_id == "open_wounded":
                configured_image["confidence"] = 0.74
                configured_image["orb_match_threshold"] = 3
            if task_id == "fence_survivors":
                configured_image["allow_repeat"] = True
                configured_image["block_seconds"] = 2.0
                configured_image["confidence"] = 0.80
                configured_image["orb_match_threshold"] = 3
            if task_id in {"processing_factory", "processing_contest"}:
                actionable_steps = ["pan_north", "select_refinery", "open_refinery"]
                actionable_steps.append(
                    "open_slot" if task_id == "processing_factory" else "open_contest"
                )
                actionable_steps.append(
                    "process_all" if task_id == "processing_factory" else "collect_all"
                )
                if step_id.endswith("_guard"):
                    configured_image["guard_only"] = True
                    configured_image["confidence"] = 0.75
                    configured_image["orb_match_threshold"] = 3
                else:
                    runtime_step = (
                        "select_refinery"
                        if step_id.startswith("select_refinery")
                        else "open_refinery"
                        if step_id.startswith("open_refinery")
                        else step_id
                    )
                    step_index = actionable_steps.index(runtime_step)
                    configured_image["runtime_step"] = runtime_step
                    configured_image["routine_priority"] = 10 + step_index * 10
                    if step_index:
                        configured_image["requires_runtime_steps"] = [
                            actionable_steps[step_index - 1]
                        ]
                if step_id.startswith("pan_north"):
                    configured_image.update(
                        {
                            "action": "swipe",
                            "swipe_from": [650, 260],
                            "swipe_to": [650, 610],
                            "swipe_duration_ms": 350,
                            "swipe_repeat_count": 6,
                            "swipe_repeat_pause": 0.2,
                            "home_screen_marker": True,
                            "confidence": 0.75,
                            "orb_match_threshold": 3,
                        }
                    )
                elif step_id.startswith("select_refinery"):
                    configured_image["confidence"] = 0.68
                    configured_image["orb_match_threshold"] = 3
                elif step_id.startswith("open_refinery"):
                    configured_image["confidence"] = 0.75
                    configured_image["orb_match_threshold"] = 3
                elif step_id in {"open_slot", "process_all", "collect_all"}:
                    configured_image["confidence"] = 0.80
                    configured_image["orb_match_threshold"] = 3
            if task_id == "mail_rewards":
                mail_sequence = (
                    "open_mail",
                    "select_system",
                    "claim_system",
                    "select_alliance",
                    "claim_alliance",
                    "select_reports",
                    "claim_reports",
                )
                mail_requirements = {
                    "select_system": ["open_mail"],
                    "claim_system": ["select_system"],
                    "select_alliance": ["select_system"],
                    "claim_alliance": ["select_alliance"],
                    "select_reports": ["select_alliance"],
                    "claim_reports": ["select_reports"],
                }
                if step_id == "close_rewards":
                    configured_image["routine_priority"] = 1
                    configured_image["allow_repeat"] = True
                    configured_image["block_seconds"] = 2.0
                    configured_image["delay"] = 1.5
                else:
                    step_index = mail_sequence.index(step_id)
                    configured_image["routine_priority"] = 10 + step_index * 10
                    configured_image["runtime_step"] = step_id
                    required_steps = mail_requirements.get(step_id)
                    if required_steps:
                        configured_image["requires_runtime_steps"] = required_steps
                    if step_id.startswith("select_"):
                        configured_image["confidence"] = 0.70
                        configured_image["orb_match_threshold"] = 3
                if step_id == "open_mail":
                    configured_image["home_screen_marker"] = True
            if task_id == "completed_tasks":
                configured_image["runtime_step"] = step_id
                if step_id == "close_rewards":
                    configured_image.pop("runtime_step", None)
                    configured_image.update(
                        {
                            "routine_priority": 1,
                            "allow_repeat": True,
                            "block_seconds": 2.0,
                            "delay": 1.5,
                        }
                    )
                elif step_id == "open_tasks":
                    configured_image["routine_priority"] = 10
                    configured_image["home_screen_marker"] = True
                elif step_id == "claim_main":
                    configured_image.update(
                        {
                            "routine_priority": 20,
                            "requires_runtime_steps": ["open_tasks"],
                            "repeat_runtime_step": True,
                            "allow_repeat": True,
                            "block_seconds": 0.8,
                        }
                    )
                elif step_id == "select_daily":
                    configured_image["routine_priority"] = 30
                    configured_image["requires_runtime_steps"] = ["open_tasks"]
                    configured_image["confidence"] = 0.70
                    configured_image["orb_match_threshold"] = 3
                elif step_id == "claim_daily":
                    configured_image.update(
                        {
                            "routine_priority": 40,
                            "requires_runtime_steps": ["select_daily"],
                            "repeat_runtime_step": True,
                            "allow_repeat": True,
                            "block_seconds": 0.8,
                        }
                    )
                elif step_id.startswith("scroll_daily_"):
                    scroll_index = int(step_id.rsplit("_", 1)[1])
                    configured_image.update(
                        {
                            "routine_priority": 50 + scroll_index,
                            "requires_runtime_steps": [
                                "open_tasks" if scroll_index == 1 else f"scroll_daily_{scroll_index - 1}"
                            ],
                            "action": "swipe",
                            "swipe_from": [900, 600],
                            "swipe_to": [900, 330],
                            "swipe_duration_ms": 500,
                            "confidence": 0.70,
                            "orb_match_threshold": 3,
                        }
                    )
                    if scroll_index == 1:
                        configured_image["implied_runtime_steps"] = ["select_daily"]
                elif step_id.startswith("scroll_top_"):
                    scroll_index = int(step_id.rsplit("_", 1)[1])
                    configured_image.update(
                        {
                            "routine_priority": 60 + scroll_index,
                            "requires_runtime_steps": [
                                "scroll_daily_4" if scroll_index == 1 else f"scroll_top_{scroll_index - 1}"
                            ],
                            "action": "swipe",
                            "swipe_from": [900, 330],
                            "swipe_to": [900, 620],
                            "swipe_duration_ms": 500,
                            "confidence": 0.70,
                            "orb_match_threshold": 3,
                        }
                    )
                elif step_id.startswith("claim_activity_"):
                    activity_level = int(step_id.rsplit("_", 1)[1])
                    configured_image.update(
                        {
                            "routine_priority": 70 + activity_level,
                            "requires_runtime_steps": ["scroll_top_4"],
                        }
                    )
            if task_id == "heal" and step_id == "collect_finished":
                configured_image["action"] = "collect_healed_troops"
                configured_image["grayscale"] = True
                configured_image["confidence"] = min(
                    0.70,
                    float(configured_image.get("confidence", 0.88) or 0.88),
                )
                configured_image["search_region"] = [120, 70, 1040, 550]
                configured_image["required_setting_key"] = "collect_finished"
                configured_image["required_setting_value"] = True
                configured_image["allow_repeat"] = True
                configured_image["block_seconds"] = 1.0
            if task_id == "heal" and step_id == "collect_finished_alt_1":
                configured_image["action"] = "click"
                configured_image["confidence"] = min(
                    0.78,
                    float(configured_image.get("confidence", 0.88) or 0.88),
                )
                configured_image["grayscale"] = True
                configured_image["search_region"] = [1150, 430, 130, 190]
                configured_image["runtime_step"] = "healing_overview"
                configured_image["allow_runtime_resume"] = True
                configured_image["allow_repeat"] = True
                configured_image["block_seconds"] = 1.0
            if task_id == "heal" and step_id == "start_healing":
                configured_image["action"] = "heal_troops"
            if task_id in {"zombie_hunt", "collective_mind"}:
                # Hunt dialog buttons are small text crops and may contain fewer
                # than ten ORB points even on a perfect match.
                configured_image["orb_match_threshold"] = 3
            manifest["images"].append(configured_image)
            payloads.append((output_path, entry_name))
            if (
                task_id not in {"alliance_donations", "mail_rewards", "completed_tasks"}
                and not is_radar_task_id(task_id)
            ):
                completion_uid = uid
            print(f"{task_id:15s} {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")
        task["completion_uid"] = completion_uid

    for task_id, training in TRAINING_DATA.items():
        task = next(item for item in tasks if item["id"] == task_id)
        group = task["group"]
        guard_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:building"))

        queue_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:queue"))
        queue_entry = f"templates/{queue_uid}.png"
        source, crop = crop_image("left_crosshair.png", (12, 294, 87, 350))
        score = verify_crop(source, crop, False)
        queue_output = staging / f"{task_id}_queue.png"
        if not cv2.imwrite(str(queue_output), crop):
            raise OSError(f"Could not write {queue_output}")
        queue_image = image_config(
            queue_uid,
            queue_entry,
            group,
            "Найти учебное здание через свободную очередь",
            (0, 0),
            False,
            0.64,
        )
        queue_image.update(
            {
                "action": "select_training_queue",
                "allow_repeat": True,
                "block_seconds": 0.7,
                "repeat_runtime_step": True,
                "skip_if_uid_visible": guard_uid,
                "training_queue_region": True,
            }
        )
        manifest["images"].append(queue_image)
        payloads.append((queue_output, queue_entry))
        print(f"{task_id:15s} {'queue':15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

        guard_entry = f"templates/{guard_uid}.png"
        source, crop = crop_image(training["selection_source"], training["title_box"])
        score = verify_crop(source, crop, False)
        guard_output = staging / f"{task_id}_building.png"
        if not cv2.imwrite(str(guard_output), crop):
            raise OSError(f"Could not write {guard_output}")
        left, top, right, bottom = training["title_box"]
        center = ((left + right) // 2, (top + bottom) // 2)
        target_x, target_y = training["train_target"]
        manifest["images"].append(
            image_config(
                guard_uid,
                guard_entry,
                group,
                "Открыть обучение нужного типа войск",
                (target_x - center[0], target_y - center[1]),
                False,
                0.8,
            )
        )
        payloads.append((guard_output, guard_entry))
        print(f"{task_id:15s} {'building':15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

        for alternate_index, alternate_selection in enumerate(
            training.get("alternate_selections", ()),
            start=1,
        ):
            source_name, alternate_box, alternate_target = alternate_selection
            alternate_uid = str(
                uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:building_alternate_{alternate_index}")
            )
            alternate_entry = f"templates/{alternate_uid}.png"
            source, crop = crop_image(source_name, alternate_box)
            score = verify_crop(source, crop, False)
            alternate_output = staging / f"{task_id}_building_alternate_{alternate_index}.png"
            if not cv2.imwrite(str(alternate_output), crop):
                raise OSError(f"Could not write {alternate_output}")
            left, top, right, bottom = alternate_box
            center = ((left + right) // 2, (top + bottom) // 2)
            target_x, target_y = alternate_target
            alternate_image = image_config(
                alternate_uid,
                alternate_entry,
                group,
                "Открыть обучение нужного типа войск (младшая казарма)",
                (target_x - center[0], target_y - center[1]),
                False,
                0.8,
            )
            alternate_image.update(
                {
                    "runtime_step": "building",
                    "routine_priority": 5 + alternate_index,
                    "allow_runtime_resume": True,
                    "implied_runtime_steps": ["queue"],
                }
            )
            manifest["images"].append(alternate_image)
            payloads.append((alternate_output, alternate_entry))
            print(
                f"{task_id:15s} {f'building_alt_{alternate_index}':15s} score={score:.3f} "
                f"size={crop.shape[1]}x{crop.shape[0]}"
            )

        final_uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:train"))
        final_entry = f"templates/{final_uid}.png"
        final_box = (430, 42, 850, 83)
        source, crop = crop_image(training["screen_source"], final_box)
        score = verify_crop(source, crop, False)
        final_output = staging / f"{task_id}_train.png"
        if not cv2.imwrite(str(final_output), crop):
            raise OSError(f"Could not write {final_output}")
        final_image = image_config(
            final_uid,
            final_entry,
            group,
            "Выбрать максимальный уровень и начать обучение",
            (423, 564),
            False,
            1.5,
        )
        final_image["action"] = "train_highest"
        manifest["images"].append(final_image)
        payloads.append((final_output, final_entry))
        task["completion_uid"] = final_uid
        print(f"{task_id:15s} {'train':15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    research_task = next(item for item in tasks if item["id"] == "research")
    research_group = "Исследования"
    research_task["group"] = research_group
    research_guard_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:lab"))
    research_alternate_guard_uids = [
        str(uuid.uuid5(PROFILE_NAMESPACE, f"research:lab_alternate_{index}"))
        for index, _alternate in enumerate(RESEARCH_STEPS.get("alternate_guards", ()), start=1)
    ]

    research_queue_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:queue"))
    research_queue_entry = f"templates/{research_queue_uid}.png"
    source, crop = crop_image("research_lab_radial.png", RESEARCH_STEPS["queue_box"])
    score = verify_crop(source, crop, False)
    research_queue_output = staging / "research_queue.png"
    if not cv2.imwrite(str(research_queue_output), crop):
        raise OSError(f"Could not write {research_queue_output}")
    research_queue_image = image_config(
        research_queue_uid,
        research_queue_entry,
        research_group,
        "Найти свободную личную лабораторию",
        (0, 0),
        False,
        0.8,
    )
    research_queue_image.update(
        {
            "allow_repeat": True,
            "block_seconds": 0.7,
            "skip_if_uid_visible": research_guard_uid,
            "skip_if_visible_uids": [research_guard_uid, *research_alternate_guard_uids],
            "limit_key": "max_lab_checks",
            "defer_when_limit_reached": True,
        }
    )
    manifest["images"].append(research_queue_image)
    payloads.append((research_queue_output, research_queue_entry))
    print(f"{'research':15s} {'queue':15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    research_guard_entry = f"templates/{research_guard_uid}.png"
    source, crop = crop_image(RESEARCH_STEPS["guard_source"], RESEARCH_STEPS["guard_box"])
    score = verify_crop(source, crop, False)
    research_guard_output = staging / "research_lab.png"
    if not cv2.imwrite(str(research_guard_output), crop):
        raise OSError(f"Could not write {research_guard_output}")
    left, top, right, bottom = RESEARCH_STEPS["guard_box"]
    center = ((left + right) // 2, (top + bottom) // 2)
    target_x, target_y = RESEARCH_STEPS["research_target"]
    manifest["images"].append(
        image_config(
            research_guard_uid,
            research_guard_entry,
            research_group,
            "Открыть личные исследования",
            (target_x - center[0], target_y - center[1]),
            False,
            0.8,
        )
    )
    payloads.append((research_guard_output, research_guard_entry))
    print(f"{'research':15s} {'lab':15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    for alternate_index, alternate_guard in enumerate(
        RESEARCH_STEPS.get("alternate_guards", ()),
        start=1,
    ):
        source_name, alternate_box, alternate_target = alternate_guard
        alternate_uid = research_alternate_guard_uids[alternate_index - 1]
        alternate_entry = f"templates/{alternate_uid}.png"
        source, crop = crop_image(source_name, alternate_box)
        score = verify_crop(source, crop, False)
        alternate_output = staging / f"research_lab_alternate_{alternate_index}.png"
        if not cv2.imwrite(str(alternate_output), crop):
            raise OSError(f"Could not write {alternate_output}")
        left, top, right, bottom = alternate_box
        center = ((left + right) // 2, (top + bottom) // 2)
        target_x, target_y = alternate_target
        manifest["images"].append(
            image_config(
                alternate_uid,
                alternate_entry,
                research_group,
                "Открыть личные исследования (лаборатория младшего уровня)",
                (target_x - center[0], target_y - center[1]),
                False,
                0.8,
            )
        )
        payloads.append((alternate_output, alternate_entry))
        print(
            f"{'research':15s} {f'lab_alt_{alternate_index}':15s} "
            f"score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}"
        )

    research_menu_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:select"))
    research_menu_entry = f"templates/{research_menu_uid}.png"
    source, crop = crop_image(RESEARCH_STEPS["menu_source"], RESEARCH_STEPS["menu_box"])
    score = verify_crop(source, crop, False)
    research_menu_output = staging / "research_select.png"
    if not cv2.imwrite(str(research_menu_output), crop):
        raise OSError(f"Could not write {research_menu_output}")
    research_menu_image = image_config(
        research_menu_uid,
        research_menu_entry,
        research_group,
        "Выбрать доступное исследование по приоритету",
        (0, 0),
        False,
        1.0,
    )
    research_menu_image["action"] = "research_select"
    manifest["images"].append(research_menu_image)
    payloads.append((research_menu_output, research_menu_entry))
    print(f"{'research':15s} {'select':15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    research_confirm_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:confirm"))
    research_confirm_entry = f"templates/{research_confirm_uid}.png"
    source, crop = crop_image(RESEARCH_STEPS["confirm_source"], RESEARCH_STEPS["confirm_box"])
    score = verify_crop(source, crop, False)
    research_confirm_output = staging / "research_confirm.png"
    if not cv2.imwrite(str(research_confirm_output), crop):
        raise OSError(f"Could not write {research_confirm_output}")
    manifest["images"].append(
        image_config(
            research_confirm_uid,
            research_confirm_entry,
            research_group,
            "Запустить обычное исследование",
            (0, 0),
            False,
            1.5,
        )
    )
    payloads.append((research_confirm_output, research_confirm_entry))
    research_task["completion_uid"] = research_confirm_uid
    print(f"{'research':15s} {'confirm':15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")

    boost_task = next(item for item in tasks if item["id"] == "gathering_boost")
    boost_group = boost_task["group"]
    boost_steps = (
        ("active", "Усиление сбора уже активно", (0, 0), None),
        ("open_bag", "Открыть сумку", (0, 0), None),
        ("boost_category", "Открыть раздел усилений", (0, 0), None),
        ("boost_8h", "Выбрать усиление сбора на 8 часов", (0, 0), 8),
        ("boost_24h", "Выбрать усиление сбора на 24 часа", (0, 0), 24),
        ("use", "Использовать усиление сбора", (0, 0), None),
    )
    boost_completion_uid = ""
    for step_id, description, offset, required_hours in boost_steps:
        source_name, box = GATHERING_BOOST_STEPS[step_id]
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"gathering_boost:{step_id}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, False)
        output_path = staging / f"gathering_boost_{step_id}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        configured_image = image_config(uid, entry_name, boost_group, description, offset, False, 0.8)
        configured_image["runtime_step"] = step_id
        if step_id == "active":
            configured_image["action"] = "observe"
            configured_image["completes_routine"] = True
            configured_image["confidence"] = 0.75
            configured_image["orb_match_threshold"] = 3
            configured_image["routine_priority"] = 1
        elif step_id == "boost_category":
            configured_image["requires_runtime_steps"] = ["open_bag"]
            configured_image["delay"] = 2.5
        elif step_id in {"boost_8h", "boost_24h"}:
            configured_image["requires_runtime_steps"] = ["boost_category"]
            configured_image["delay"] = 1.8
        elif step_id == "use":
            configured_image["requires_runtime_steps"] = ["boost_8h", "boost_24h"]
            configured_image["runtime_step_mode"] = "any"
            configured_image["delay"] = 1.2
        if required_hours is not None:
            configured_image["required_setting_key"] = "boost_hours"
            configured_image["required_setting_value"] = required_hours
        manifest["images"].append(configured_image)
        payloads.append((output_path, entry_name))
        boost_completion_uid = uid
        print(f"{'gathering_boost':15s} {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")
    boost_task["completion_uid"] = boost_completion_uid

    zombie_task = next(item for item in tasks if item["id"] == "zombie_hunt")
    zombie_completion_uid = ""
    for step_id, description, source_name, box, offset, grayscale in ZOMBIE_STEPS:
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"zombie_hunt:{step_id}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, grayscale)
        output_path = staging / f"zombie_hunt_{step_id}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        configured_image = image_config(
            uid, entry_name, zombie_task["group"], description, offset, grayscale, 0.8
        )
        configured_image["orb_match_threshold"] = 3
        if step_id == "search":
            configured_image["action"] = "zombie_search"
        if step_id == "attack":
            configured_image["action"] = "zombie_attack"
        if step_id == "world_search":
            configured_image["confidence"] = 0.82
        if step_id == "zombie_icon":
            configured_image["confidence"] = 0.78
        if step_id == "march":
            configured_image["limit_key"] = "max_attacks"
            zombie_completion_uid = uid
        manifest["images"].append(configured_image)
        payloads.append((output_path, entry_name))
        print(f"{'zombie_hunt':15s} {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")
    zombie_task["completion_uid"] = zombie_completion_uid

    hivemind_task = next(item for item in tasks if item["id"] == "collective_mind")
    hivemind_completion_uid = ""
    for step_id, description, source_name, box, offset, grayscale in HIVEMIND_STEPS:
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"collective_mind:{step_id}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, grayscale)
        output_path = staging / f"collective_mind_{step_id}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        configured_image = image_config(
            uid, entry_name, hivemind_task["group"], description, offset, grayscale, 0.8
        )
        configured_image["orb_match_threshold"] = 3
        if step_id == "search":
            configured_image["action"] = "hivemind_search"
            configured_image["no_result_template_uid"] = str(
                uuid.uuid5(PROFILE_NAMESPACE, "collective_mind:no_result")
            )
        if step_id == "no_result":
            configured_image["enabled"] = False
            configured_image["observer_only"] = True
            configured_image["confidence"] = 0.72
        if step_id == "world_search":
            configured_image["confidence"] = 0.82
        if step_id == "march":
            hivemind_completion_uid = uid
        manifest["images"].append(configured_image)
        payloads.append((output_path, entry_name))
        print(f"{'collective_mind':15s} {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")
    hivemind_task["completion_uid"] = hivemind_completion_uid

    prize_task = next(item for item in tasks if item["id"] == "prize_hunt")
    for step_id, description, source_name, box, offset, grayscale in PRIZE_HUNT_STEPS:
        uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"prize_hunt:{step_id}"))
        entry_name = f"templates/{uid}.png"
        source, crop = crop_image(source_name, box)
        score = verify_crop(source, crop, grayscale)
        output_path = staging / f"prize_hunt_{step_id}.png"
        if not cv2.imwrite(str(output_path), crop):
            raise OSError(f"Could not write {output_path}")
        configured_image = image_config(
            uid, entry_name, prize_task["group"], description, offset, grayscale, 0.8
        )
        configured_image["orb_match_threshold"] = 3
        configured_image["allow_repeat"] = True
        configured_image["block_seconds"] = 1.5
        if step_id == "open_squad":
            configured_image["action"] = "prize_start_or_prepare"
        if step_id == "prepare":
            configured_image["action"] = "prize_prepare"
        if step_id in {"again", "match", "confirm"}:
            configured_image["required_setting_key"] = "repeat_until_stopped"
            configured_image["required_setting_value"] = True
        if step_id == "safe_exit":
            configured_image["required_setting_key"] = "repeat_until_stopped"
            configured_image["required_setting_value"] = False
            configured_image["complete_if_setting_false"] = "repeat_until_stopped"
        manifest["images"].append(configured_image)
        payloads.append((output_path, entry_name))
        print(f"{'prize_hunt':15s} {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")
    prize_task["completion_uid"] = ""

    for task_id, resource in RESOURCE_DATA.items():
        group = resource["group"]
        steps = [
            *COMMON_STEPS[:2],
            ("resource_icon", f"Выбрать ресурс: {group}", resource["icon_source"], resource["icon_box"], (0, 0), False),
            ("search_button", f"Найти ресурс: {group}", resource["selected_source"], resource["search_box"], (0, 0), False),
            *COMMON_STEPS[2:],
        ]
        completion_uid = ""
        for step_id, description, source_name, box, offset, grayscale in steps:
            uid = str(uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:{step_id}"))
            entry_name = f"templates/{uid}.png"
            source, crop = crop_image(source_name, box)
            score = verify_crop(source, crop, grayscale)
            output_path = staging / f"{task_id}_{step_id}.png"
            if not cv2.imwrite(str(output_path), crop):
                raise OSError(f"Could not write {output_path}")
            delay = 2.0 if step_id == "march" else 0.8
            configured_image = image_config(uid, entry_name, group, description, offset, grayscale, delay)
            if step_id == "world_search":
                configured_image["confidence"] = 0.82
            runtime_step = "world_search" if step_id == "region" else step_id
            configured_image["runtime_step"] = runtime_step
            step_index = next(index for index, item in enumerate(steps) if item[0] == step_id)
            if step_id not in {"region", "world_search"}:
                previous_id = steps[step_index - 1][0]
                configured_image["requires_runtime_steps"] = [
                    "world_search" if previous_id == "region" else previous_id
                ]
            if step_id == "region":
                configured_image["action"] = "open_world_search"
                configured_image["next_template_uid"] = str(
                    uuid.uuid5(PROFILE_NAMESPACE, f"{task_id}:world_search")
                )
            if step_id == "search_button":
                configured_image["action"] = "resource_search"
            manifest["images"].append(configured_image)
            payloads.append((output_path, entry_name))
            print(f"{task_id:5s} {step_id:15s} score={score:.3f} size={crop.shape[1]}x{crop.shape[0]}")
            if step_id == "march":
                completion_uid = uid
        next(task for task in tasks if task["id"] == task_id)["completion_uid"] = completion_uid

    upgrade_resource_runtime_metadata(manifest["images"], tasks)
    upgrade_strict_runtime_metadata(manifest["images"], tasks)
    upgrade_prize_hunt_metadata(manifest["images"], tasks)
    upgrade_radar_runtime_metadata(manifest["images"], tasks)
    upgrade_repeatable_claim_metadata(manifest["images"], tasks)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("profile.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for source_path, entry_name in payloads:
            archive.write(source_path, entry_name)
    return destination, manifest


def install_profile(profile_path, install_root):
    install_root = Path(install_root)
    config_path = install_root / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    preserved_runtime = {
        key: deepcopy(config[key])
        for key in (
            "scale_enabled",
            "input_backend",
            "adb_serial",
            "adb_path",
            "account_profiles",
            "current_account_id",
            "account_rotation_enabled",
        )
        if key in config
    }
    existing_tasks = {
        task.get("id"): task
        for task in config.get("routine_tasks", [])
        if task.get("id")
    }

    with zipfile.ZipFile(profile_path, "r") as archive:
        manifest = json.loads(archive.read("profile.json").decode("utf-8"))
        routine_groups = set(manifest["groups"])
        config["images"] = [
            image for image in config.get("images", [])
            if image.get("group") not in routine_groups
        ]
        for image in manifest["images"]:
            task_id = next(
                (
                    task["id"] for task in manifest["routine_tasks"]
                    if task["group"] == image["group"]
                ),
                "system",
            )
            target_dir = install_root / "img" / task_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{image['uid']}.png"
            target_path.write_bytes(archive.read(image["path"]))
            installed = deepcopy(image)
            installed["path"] = str(target_path.relative_to(install_root))
            config["images"].append(installed)

    config["routine_tasks"] = deepcopy(manifest["routine_tasks"])
    for task in config["routine_tasks"]:
        existing = existing_tasks.get(task["id"], {})
        task["enabled"] = existing.get("enabled", task.get("enabled", False))
        task["settings"] = deepcopy(existing.get("settings", task.get("settings", {})))
    config["routine_max_marches"] = manifest["routine_max_marches"]
    config["routine_march_deadlines"] = []
    config["routine_next_run"] = {}
    config.setdefault("groups", {}).update(manifest["groups"])
    config["scale_enabled"] = False
    config["input_backend"] = "adb"
    config["adb_serial"] = "emulator-5564"
    config["adb_path"] = str(Path(r"C:\LDPlayer\LDPlayer9\adb.exe"))
    config["account_profiles"] = [
        {
            "id": "phoenix675",
            "name": "Phoenix675",
            "enabled": True,
            "ldplayer_index": 5,
            "adb_serial": "emulator-5564",
            "session_minutes": 30.0,
            "login_method": "igg",
            "chooser_index": 1,
            "google_login": "",
            "igg_login": "",
            "auto_login": False,
            "switch_group": "Аккаунт: Phoenix675",
            "switch_completion_uid": "",
            "task_enabled": {task["id"]: task["enabled"] for task in manifest["routine_tasks"]},
            "task_settings": {task["id"]: task.get("settings", {}) for task in manifest["routine_tasks"]},
            "routine_next_run": {},
        }
    ]
    config["current_account_id"] = "phoenix675"
    config["account_rotation_enabled"] = False
    config.update(preserved_runtime)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--install-root", type=Path)
    args = parser.parse_args()
    profile_path, manifest = build_profile(args.output)
    if args.install_root:
        install_profile(profile_path, args.install_root)
    print(f"Profile: {profile_path}")
    print(f"Templates: {len(manifest['images'])}")


if __name__ == "__main__":
    main()
