import unittest
from datetime import datetime, timezone
import time
import uuid

from buzzbot.routines import (
    PROFILE_NAMESPACE,
    RADAR_TASK_IDS,
    completed_runtime_steps_for_image,
    default_routine_tasks,
    effective_active_marches,
    effective_task_group,
    format_wait_duration,
    gathering_boost_active_until,
    gathering_boost_duration_hours,
    healing_pending_allows_image,
    image_is_allowed_for_routine,
    is_task_effectively_enabled,
    next_due_task,
    next_run_after_finish,
    next_run_after_radar_pass,
    next_fixed_utc_run,
    no_action_retry_delay,
    no_available_squad_wait_exceeded,
    normalize_routine_tasks,
    pick_due_task_index,
    prize_hunt_branch_allows_image,
    radar_marker_requires_notification,
    radar_marker_was_confirmed,
    reset_radar_card_runtime_steps,
    reconcile_march_deadlines,
    resource_search_retry_due,
    setting_requirement_matches,
    routine_home_recovery_due,
    routine_idle_screen_recovery_due,
    routine_missing_followup_is_unavailable,
    routine_requires_settlement,
    routine_march_context_key,
    runtime_step_is_ready,
    task_setting_specs,
    training_queue_match_is_safe,
    unavailable_retry_delay,
    upgrade_prize_hunt_metadata,
    upgrade_radar_runtime_metadata,
    upgrade_repeatable_claim_metadata,
    upgrade_resource_runtime_metadata,
    upgrade_strict_runtime_metadata,
    zombie_fallback_levels,
)


class RoutineTaskTests(unittest.TestCase):
    def test_defaults_cover_requested_routines(self):
        tasks = default_routine_tasks()
        ids = {task["id"] for task in tasks}
        self.assertTrue(
            {
                "game_login",
                "vip_rewards",
                "alliance_donations",
                "radar_rewards",
                "radar_quick",
                "radar_marches",
                "alliance_help",
                "fence_survivors",
                "processing_factory",
                "processing_contest",
                "mail_rewards",
                "completed_tasks",
                "research",
                "gathering_boost",
                "heal",
                "zombie_hunt",
                "collective_mind",
                "prize_hunt",
                "wasteland_exploration",
                "food",
                "wood",
                "metal",
                "oil",
                "train_infantry",
                "train_riders",
                "train_shooters",
                "train_vehicles",
            }.issubset(ids)
        )
        by_id = {task["id"]: task for task in tasks}
        self.assertNotIn("radar", by_id)
        self.assertEqual(
            tuple(task["id"] for task in tasks if task["id"] in RADAR_TASK_IDS),
            RADAR_TASK_IDS,
        )
        self.assertFalse(by_id["radar_rewards"]["uses_march"])
        self.assertFalse(by_id["radar_quick"]["uses_march"])
        self.assertTrue(by_id["radar_marches"]["uses_march"])
        self.assertEqual(
            by_id["radar_marches"]["march_completion_runtime_step"],
            "radar_march",
        )
        self.assertTrue(all(not by_id[task_id]["manual_screen_required"] for task_id in RADAR_TASK_IDS))
        self.assertTrue(all(by_id[task_id]["settings"]["visual_fallback"] for task_id in RADAR_TASK_IDS))
        self.assertFalse(by_id["game_login"]["enabled"])
        self.assertEqual(by_id["game_login"]["priority"], 1)
        self.assertEqual(by_id["game_login"]["timeout_seconds"], 330.0)
        self.assertEqual(by_id["mail_rewards"]["completion_runtime_step"], "claim_reports")
        self.assertEqual(by_id["completed_tasks"]["completion_runtime_step"], "scroll_top_4")
        self.assertEqual(by_id["fence_survivors"]["interval_minutes"], 15.0)
        self.assertTrue(by_id["fence_survivors"]["empty_home_is_success"])
        self.assertTrue(by_id["vip_rewards"]["empty_home_is_success"])
        self.assertTrue(by_id["alliance_help"]["empty_home_is_success"])
        self.assertTrue(by_id["research"]["empty_home_is_success"])
        self.assertEqual(by_id["processing_factory"]["interval_minutes"], 180.0)
        self.assertTrue(by_id["processing_factory"]["complete_when_idle"])
        self.assertTrue(by_id["processing_contest"]["complete_when_idle"])
        self.assertEqual(by_id["heal"]["settings"]["collection_delay_seconds"], 2)
        self.assertEqual(by_id["heal"]["settings"]["repeat_delay_seconds"], 2)
        heal_setting_keys = {
            spec["key"] for spec in task_setting_specs("heal")
        }
        self.assertIn("collection_delay_seconds", heal_setting_keys)
        self.assertIn("repeat_delay_seconds", heal_setting_keys)
        self.assertEqual(by_id["collective_mind"]["settings"]["level"], 6)
        collective_level = next(
            spec for spec in task_setting_specs("collective_mind") if spec["key"] == "level"
        )
        self.assertEqual(collective_level["choices"], ((6, "6"), (7, "7")))
        for task_id in ("food", "wood", "metal", "oil"):
            resource_level = next(
                spec for spec in task_setting_specs(task_id) if spec["key"] == "resource_level"
            )
            self.assertEqual(resource_level["max"], 7)

    def test_resources_are_individually_selectable(self):
        tasks = default_routine_tasks()
        resources = [task for task in tasks if task.get("category") == "resources"]
        self.assertEqual([task["id"] for task in resources], ["food", "wood", "metal", "oil"])
        self.assertTrue(all(not task["enabled"] and task["uses_march"] for task in resources))

    def test_legacy_research_config_keeps_busy_lab_as_safe_completion(self):
        research = next(
            task
            for task in normalize_routine_tasks(
                [{"id": "research", "empty_home_is_success": False}]
            )
            if task["id"] == "research"
        )
        self.assertTrue(research["empty_home_is_success"])

    def test_legacy_game_login_timeout_allows_automatic_restart(self):
        login = next(
            task
            for task in normalize_routine_tasks(
                [{"id": "game_login", "timeout_seconds": 90.0}]
            )
            if task["id"] == "game_login"
        )
        self.assertEqual(login["timeout_seconds"], 330.0)

    def test_normalization_preserves_radar_march_confirmation(self):
        radar = next(
            task
            for task in normalize_routine_tasks(
                [{"id": "radar_marches", "march_completion_runtime_step": "radar_march"}]
            )
            if task["id"] == "radar_marches"
        )

        self.assertEqual(radar["march_completion_runtime_step"], "radar_march")
        self.assertFalse(radar["manual_screen_required"])

    def test_long_waits_are_human_readable(self):
        self.assertEqual(format_wait_duration(42, "ru"), "42 сек")
        self.assertEqual(format_wait_duration(300, "ru"), "5 мин")
        self.assertEqual(format_wait_duration(9700, "ru"), "2 ч 42 мин")
        self.assertEqual(format_wait_duration(9700, "en"), "2 h 42 min")

    def test_resource_upgrade_clamps_legacy_level_to_seven(self):
        tasks = default_routine_tasks()
        oil = next(task for task in tasks if task["id"] == "oil")
        oil["settings"]["resource_level"] = 8

        upgrade_resource_runtime_metadata([], tasks)

        self.assertEqual(oil["settings"]["resource_level"], 7)

    def test_normalization_repairs_values_and_merges_settings(self):
        tasks = normalize_routine_tasks([
            {
                "id": "food",
                "group": "  Ферма еды  ",
                "interval_minutes": -1,
                "timeout_seconds": "bad",
                "settings": {"resource_level": 8},
            },
            {
                "id": "custom_daily",
                "name": "Ежедневная награда",
                "group": "Награды",
                "enabled": True,
            },
            {
                "id": "fence_survivors",
                "empty_home_is_success": False,
            },
            {
                "id": "vip_rewards",
                "empty_home_is_success": False,
            },
        ])
        food = next(task for task in tasks if task["id"] == "food")
        alliance_help = next(task for task in tasks if task["id"] == "alliance_help")
        fence_survivors = next(task for task in tasks if task["id"] == "fence_survivors")
        vip_rewards = next(task for task in tasks if task["id"] == "vip_rewards")
        custom = next(task for task in tasks if task["id"] == "custom_daily")
        self.assertEqual(food["group"], "Ферма еды")
        self.assertEqual(food["interval_minutes"], 0.1)
        self.assertEqual(food["timeout_seconds"], 30.0)
        self.assertEqual(food["settings"]["resource_level"], 8)
        self.assertTrue(alliance_help["empty_home_is_success"])
        self.assertTrue(fence_survivors["empty_home_is_success"])
        self.assertTrue(vip_rewards["empty_home_is_success"])
        self.assertEqual(custom["name"], "Ежедневная награда")

    def test_healing_has_priority_when_selected(self):
        tasks = default_routine_tasks()
        heal = next(task for task in tasks if task["id"] == "heal")
        heal["enabled"] = True
        index = pick_due_task_index(tasks, {}, start_index=0, now=100.0, active_marches=0, max_marches=5)
        self.assertEqual(tasks[index]["id"], "heal")

    def test_resource_rotation_starts_from_requested_position(self):
        tasks = default_routine_tasks()
        for task in tasks:
            task["enabled"] = task["id"] in {"food", "wood", "metal", "oil"}
        wood_index = next(index for index, task in enumerate(tasks) if task["id"] == "wood")
        index = pick_due_task_index(tasks, {}, start_index=wood_index, now=100.0, active_marches=0, max_marches=5)
        self.assertEqual(tasks[index]["id"], "wood")

    def test_resource_rotation_finishes_never_run_resources_before_repeating(self):
        tasks = default_routine_tasks()
        for task in tasks:
            task["enabled"] = task["id"] in {"food", "wood", "metal", "oil"}
        next_run = {"food": 95.0, "wood": 96.0, "metal": 0.0, "oil": 0.0}
        food_index = next(index for index, task in enumerate(tasks) if task["id"] == "food")

        index = pick_due_task_index(
            tasks,
            next_run,
            start_index=food_index,
            now=100.0,
            active_marches=2,
            max_marches=5,
        )

        self.assertEqual(tasks[index]["id"], "metal")

    def test_retried_training_does_not_starve_never_run_resources(self):
        tasks = default_routine_tasks()
        selected = {
            "train_infantry",
            "train_riders",
            "train_shooters",
            "train_vehicles",
            "food",
            "wood",
        }
        for task in tasks:
            task["enabled"] = task["id"] in selected
        next_run = {
            "train_infantry": 195.0,
            "train_riders": 196.0,
            "train_shooters": 197.0,
            "train_vehicles": 198.0,
            "food": 0.0,
            "wood": 0.0,
        }

        index = pick_due_task_index(tasks, next_run, 0, now=200.0)

        self.assertEqual(tasks[index]["id"], "food")

    def test_training_queue_match_is_limited_to_left_hud_slot(self):
        self.assertTrue(training_queue_match_is_safe((12, 294, 75, 56), 1280, 720))
        self.assertFalse(training_queue_match_is_safe((500, 294, 75, 56), 1280, 720))
        self.assertFalse(training_queue_match_is_safe((12, 80, 75, 56), 1280, 720))

    def test_only_checked_task_is_scheduled(self):
        tasks = default_routine_tasks()
        for task in tasks:
            task["enabled"] = task["id"] == "metal"
        index = pick_due_task_index(tasks, {}, start_index=0, now=100.0, active_marches=0, max_marches=5)
        self.assertEqual(tasks[index]["id"], "metal")
        next_task, _wait = next_due_task(tasks, {}, now=100.0, active_marches=0, max_marches=5)
        self.assertEqual(next_task["id"], "metal")

    def test_each_exclusive_checkbox_schedules_only_its_task(self):
        task_ids = (
            "game_login",
            "alliance_help",
            "prize_hunt",
            "zombie_hunt",
            "collective_mind",
            "food",
            "wood",
            "metal",
            "oil",
        )
        for selected_id in task_ids:
            with self.subTest(selected_id=selected_id):
                tasks = default_routine_tasks()
                for task in tasks:
                    task["enabled"] = task["id"] == selected_id
                index = pick_due_task_index(
                    tasks,
                    {},
                    start_index=0,
                    now=100.0,
                    active_marches=0,
                    max_marches=5,
                )
                self.assertIsNotNone(index)
                self.assertEqual(tasks[index]["id"], selected_id)

    def test_login_precedes_a_selected_daily_task(self):
        tasks = default_routine_tasks()
        for task in tasks:
            task["enabled"] = task["id"] in {"game_login", "alliance_help"}
        index = pick_due_task_index(
            tasks,
            {},
            start_index=0,
            now=100.0,
            active_marches=0,
            max_marches=5,
        )
        self.assertEqual(tasks[index]["id"], "game_login")

    def test_enabled_prize_hunt_precedes_regular_resources(self):
        tasks = default_routine_tasks()
        prize = next(task for task in tasks if task["id"] == "prize_hunt")
        prize["enabled"] = True
        index = pick_due_task_index(tasks, {}, start_index=0, now=100.0, active_marches=5, max_marches=5)
        self.assertEqual(tasks[index]["id"], "prize_hunt")

    def test_old_prize_hunt_config_is_migrated_away_from_world_marches(self):
        tasks = normalize_routine_tasks([{"id": "prize_hunt", "uses_march": True}])
        prize = next(task for task in tasks if task["id"] == "prize_hunt")
        self.assertFalse(prize["uses_march"])

    def test_legacy_combined_radar_is_retired_without_enabling_new_modes(self):
        tasks = normalize_routine_tasks([{"id": "radar", "enabled": True}])
        by_id = {task["id"]: task for task in tasks}

        self.assertNotIn("radar", by_id)
        self.assertTrue(all(not by_id[task_id]["enabled"] for task_id in RADAR_TASK_IDS))

    def test_sixth_march_is_never_scheduled(self):
        tasks = default_routine_tasks()
        for task in tasks:
            task["enabled"] = bool(task.get("uses_march"))
        index = pick_due_task_index(tasks, {}, 0, 100.0, active_marches=5, max_marches=5)
        self.assertIsNone(index)
        task, wait = next_due_task(tasks, {}, 100.0, active_marches=5, max_marches=5)
        self.assertIsNone(task)
        self.assertIsNone(wait)

    def test_configured_four_march_limit_is_respected(self):
        tasks = default_routine_tasks()
        for task in tasks:
            task["enabled"] = bool(task.get("uses_march"))
        blocked = pick_due_task_index(tasks, {}, 0, 100.0, active_marches=4, max_marches=4)
        allowed = pick_due_task_index(tasks, {}, 0, 100.0, active_marches=4, max_marches=5)
        self.assertIsNone(blocked)
        self.assertIsNotNone(allowed)

    def test_research_off_is_not_scheduled(self):
        task = next(task for task in default_routine_tasks() if task["id"] == "research")
        self.assertFalse(task["enabled"])
        self.assertEqual(task["settings"]["branch"], "off")
        task["enabled"] = True
        self.assertFalse(is_task_effectively_enabled(task))
        task["settings"]["branch"] = "economy"
        self.assertTrue(is_task_effectively_enabled(task))
        self.assertEqual(effective_task_group(task), "Исследования")

    def test_alliance_donations_wait_for_the_game_cooldown(self):
        task = next(task for task in default_routine_tasks() if task["id"] == "alliance_donations")
        self.assertFalse(task["enabled"])
        self.assertTrue(task["settings"]["avoid_gems"])
        self.assertEqual(task["settings"]["max_donations"], 100)
        self.assertEqual(task["settings"]["max_project_checks"], 6)
        self.assertEqual(task["interval_minutes"], 20.0)
        self.assertEqual(task["timeout_seconds"], 30.0)
        self.assertEqual(task["completion_runtime_step"], "all_projects_checked")

    def test_repeatable_claims_guard_task_closing(self):
        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        donate_uid = str(uuid.uuid5(namespace, "alliance_donations:donate_resources"))
        donation_close_uid = str(uuid.uuid5(namespace, "alliance_donations:close_project"))
        donation_project_uid = str(
            uuid.uuid5(namespace, "alliance_donations:select_project_research")
        )
        donation_marked_uid = str(
            uuid.uuid5(namespace, "alliance_donations:select_marked_project")
        )
        vip_claim_uid = str(uuid.uuid5(namespace, "vip_rewards:claim_chest"))
        vip_dismiss_uid = str(uuid.uuid5(namespace, "vip_rewards:dismiss_info"))
        vip_receive_uid = str(uuid.uuid5(namespace, "vip_rewards:receive_free"))
        vip_close_uid = str(uuid.uuid5(namespace, "vip_rewards:close_vip"))
        images = [
            {"uid": donate_uid},
            {"uid": donation_close_uid},
            {"uid": donation_project_uid, "confidence": 0.88, "orb_match_threshold": 10},
            {"uid": donation_marked_uid, "allow_repeat": True},
            {"uid": vip_claim_uid},
            {"uid": vip_dismiss_uid},
            {"uid": vip_receive_uid},
            {"uid": vip_close_uid},
        ]
        tasks = default_routine_tasks()
        donation_task = next(task for task in tasks if task["id"] == "alliance_donations")
        donation_task["settings"]["max_donations"] = 30

        upgrade_repeatable_claim_metadata(images, tasks)
        by_uid = {image["uid"]: image for image in images}

        self.assertTrue(by_uid[donate_uid]["allow_repeat"])
        self.assertIn(donate_uid, by_uid[donation_close_uid]["skip_if_visible_uids"])
        self.assertLessEqual(by_uid[donation_project_uid]["confidence"], 0.74)
        self.assertEqual(by_uid[donation_project_uid]["orb_match_threshold"], 3)
        self.assertEqual(by_uid[donation_marked_uid]["action"], "alliance_marked_project")
        self.assertEqual(by_uid[donation_marked_uid]["routine_priority"], 15)
        self.assertFalse(by_uid[donation_marked_uid].get("allow_repeat", False))
        self.assertTrue(by_uid[vip_claim_uid]["allow_repeat"])
        self.assertTrue(by_uid[vip_dismiss_uid]["allow_repeat"])
        self.assertTrue(by_uid[vip_receive_uid]["allow_repeat"])
        self.assertTrue(by_uid[vip_receive_uid]["completes_routine"])
        self.assertEqual(
            by_uid[vip_close_uid]["skip_if_visible_uids"],
            [vip_claim_uid, vip_dismiss_uid, vip_receive_uid],
        )
        self.assertEqual(donation_task["settings"]["max_donations"], 100)
        self.assertEqual(donation_task["settings"]["max_project_checks"], 6)
        self.assertGreaterEqual(donation_task["timeout_seconds"], 30.0)
        self.assertEqual(donation_task["completion_runtime_step"], "all_projects_checked")

    def test_next_run_uses_task_interval(self):
        task = {"interval_minutes": 2.5}
        self.assertEqual(next_run_after_finish(task, 100.0), 250.0)

    def test_healing_next_run_uses_configured_seconds(self):
        task = {
            "id": "heal",
            "interval_minutes": 0.1,
            "settings": {"repeat_delay_seconds": 1},
        }

        self.assertEqual(next_run_after_finish(task, 100.0), 101.0)

    def test_zombie_hunt_repeats_quickly_to_fill_free_marches(self):
        task = next(task for task in default_routine_tasks() if task["id"] == "zombie_hunt")

        self.assertEqual(task["interval_minutes"], 0.1)
        self.assertEqual(next_run_after_finish(task, 100.0), 106.0)

        migrated = normalize_routine_tasks([{"id": "zombie_hunt", "interval_minutes": 1.0}])
        migrated_task = next(task for task in migrated if task["id"] == "zombie_hunt")
        self.assertEqual(migrated_task["interval_minutes"], 0.1)

    def test_next_fixed_utc_run_uses_noon_and_midnight(self):
        before_noon = datetime(2026, 7, 15, 11, 59, tzinfo=timezone.utc).timestamp()
        at_noon = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc).timestamp()
        before_midnight = datetime(2026, 7, 15, 23, 59, tzinfo=timezone.utc).timestamp()
        at_midnight = datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc).timestamp()

        self.assertEqual(next_fixed_utc_run(before_noon, [0, 12]), at_noon)
        self.assertEqual(next_fixed_utc_run(at_noon, [0, 12]), at_midnight)
        self.assertEqual(next_fixed_utc_run(before_midnight, [0, 12]), at_midnight)

    def test_wasteland_uses_live_utc_start_and_stamina_retry_settings(self):
        task = next(
            task
            for task in default_routine_tasks()
            if task["id"] == "wasteland_exploration"
        )

        self.assertFalse(task["enabled"])
        self.assertEqual(task["settings"]["fixed_utc_hours"], [1])
        self.assertEqual(task["settings"]["max_encounters"], 40)
        self.assertEqual(task["settings"]["stamina_retry_minutes"], 12)
        self.assertTrue(task["empty_home_is_success"])
        self.assertFalse(task["uses_march"])
        self.assertEqual(
            {spec["key"] for spec in task_setting_specs(task["id"])},
            {"max_encounters", "stamina_retry_minutes"},
        )

    def test_radar_next_run_uses_fixed_game_reset(self):
        task = next(task for task in default_routine_tasks() if task["id"] == "radar_quick")
        now = datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc).timestamp()
        expected = datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc).timestamp()
        self.assertEqual(next_run_after_finish(task, now), expected)

    def test_no_action_retry_is_bounded(self):
        self.assertEqual(no_action_retry_delay({"interval_minutes": 0.1}), 30.0)
        self.assertEqual(
            no_action_retry_delay({"id": "heal", "interval_minutes": 0.1}),
            2.0,
        )
        self.assertEqual(no_action_retry_delay({"interval_minutes": 2.0}), 120.0)
        self.assertEqual(no_action_retry_delay({"interval_minutes": 60.0}), 300.0)

    def test_pending_healing_collection_retries_without_a_minute_delay(self):
        pending_heal = {
            "id": "heal",
            "interval_minutes": 0.1,
            "settings": {
                "_collection_pending": True,
                "collection_delay_seconds": 2,
            },
        }
        ordinary_heal = {
            "id": "heal",
            "interval_minutes": 0.1,
            "settings": {"_collection_pending": False},
        }

        self.assertEqual(unavailable_retry_delay(pending_heal), 2.0)
        self.assertEqual(unavailable_retry_delay(ordinary_heal), 60.0)

    def test_legacy_healing_profile_receives_collection_delay(self):
        healing = next(
            task
            for task in normalize_routine_tasks(
                [{"id": "heal", "settings": {"troop_count": 2500}}]
            )
            if task["id"] == "heal"
        )

        self.assertEqual(healing["settings"]["collection_delay_seconds"], 2)
        self.assertEqual(healing["settings"]["repeat_delay_seconds"], 2)

    def test_home_recovery_only_runs_before_the_first_march_action(self):
        task = {"uses_march": True, "timeout_seconds": 1800.0}
        self.assertFalse(routine_home_recovery_due(task, False, False, 11.9))
        self.assertTrue(routine_home_recovery_due(task, False, False, 12.0))
        self.assertFalse(routine_home_recovery_due(task, True, False, 1800.0))
        self.assertFalse(routine_home_recovery_due(task, False, True, 1800.0))
        self.assertFalse(
            routine_home_recovery_due({"uses_march": False}, False, False, 20.0)
        )
        self.assertTrue(
            routine_home_recovery_due(
                {
                    "id": "radar_quick",
                    "uses_march": False,
                    "timeout_seconds": 12.0,
                },
                False,
                False,
                12.0,
            )
        )
        self.assertFalse(
            routine_home_recovery_due(
                {
                    "uses_march": True,
                    "manual_screen_required": True,
                    "timeout_seconds": 12.0,
                },
                False,
                False,
                20.0,
            )
        )

    def test_idle_screen_recovery_waits_for_a_confirmed_stall(self):
        task = {
            "id": "radar",
            "complete_when_idle": True,
            "timeout_seconds": 20.0,
        }
        self.assertFalse(routine_idle_screen_recovery_due(task, True, False, False, 59.9))
        self.assertTrue(routine_idle_screen_recovery_due(task, True, False, False, 60.0))
        self.assertFalse(routine_idle_screen_recovery_due(task, False, False, False, 60.0))
        self.assertFalse(routine_idle_screen_recovery_due(task, True, True, False, 60.0))
        self.assertFalse(routine_idle_screen_recovery_due(task, True, False, True, 60.0))

    def test_radar_idle_screen_recovery_uses_one_card_timeout(self):
        task = {
            "id": "radar_quick",
            "complete_when_idle": True,
            "timeout_seconds": 12.0,
        }
        self.assertFalse(routine_idle_screen_recovery_due(task, True, False, False, 11.9))
        self.assertTrue(routine_idle_screen_recovery_due(task, True, False, False, 12.0))

    def test_processing_contest_defers_when_event_entry_is_absent(self):
        task = {"id": "processing_contest", "timeout_seconds": 25.0}
        self.assertFalse(
            routine_missing_followup_is_unavailable(task, {"open_refinery"}, 24.9)
        )
        self.assertTrue(
            routine_missing_followup_is_unavailable(task, {"open_refinery"}, 25.0)
        )
        self.assertFalse(
            routine_missing_followup_is_unavailable(
                task,
                {"open_refinery", "open_contest"},
                60.0,
            )
        )
        self.assertFalse(
            routine_missing_followup_is_unavailable(
                {"id": "processing_factory", "timeout_seconds": 25.0},
                {"open_refinery"},
                60.0,
            )
        )

    def test_gathering_boost_defers_when_selected_item_is_absent(self):
        task = {"id": "gathering_boost", "timeout_seconds": 12.0}
        self.assertFalse(
            routine_missing_followup_is_unavailable(task, {"boost_category"}, 11.9)
        )
        self.assertTrue(
            routine_missing_followup_is_unavailable(task, {"boost_category"}, 12.0)
        )
        self.assertFalse(
            routine_missing_followup_is_unavailable(
                task,
                {"boost_category", "boost_8h"},
                60.0,
            )
        )

    def test_settlement_context_is_required_only_for_base_tasks(self):
        self.assertTrue(routine_requires_settlement({"category": "army"}))
        self.assertTrue(routine_requires_settlement({"category": "daily"}))
        self.assertFalse(routine_requires_settlement({"category": "resources"}))
        self.assertFalse(routine_requires_settlement({"category": "marches"}))

    def test_march_deadline_context_is_scoped_to_player_and_account(self):
        phoenix = routine_march_context_key("adb", "emulator-5564", "phoenix")
        focus = routine_march_context_key("adb", "emulator-5568", "focus")
        second_account = routine_march_context_key("adb", "emulator-5564", "farm")

        self.assertNotEqual(phoenix, focus)
        self.assertNotEqual(phoenix, second_account)
        self.assertEqual(
            phoenix,
            routine_march_context_key("ADB", "emulator-5564", "phoenix"),
        )

    def test_visible_march_counter_overrides_local_estimates(self):
        self.assertEqual(effective_active_marches(1, 1, 1, 100.0, 220.0), 1)
        self.assertEqual(effective_active_marches(4, 1, 5, 100.0, 220.0), 4)
        self.assertEqual(effective_active_marches(2, 5, 5, 100.0, 220.0), 2)
        self.assertEqual(effective_active_marches(0, 1, 1, 221.0, 220.0), 0)
        self.assertEqual(effective_active_marches(None, 2, 4, 100.0, 220.0), 2)

    def test_visible_march_counter_removes_cancelled_local_reservation(self):
        deadlines = [1000.0, 1100.0, 1200.0, 1300.0, 1400.0]
        self.assertEqual(
            reconcile_march_deadlines(deadlines, 4, 200.0, 190.0),
            deadlines[:4],
        )
        self.assertEqual(
            reconcile_march_deadlines(deadlines, 4, 180.0, 190.0),
            deadlines[:4],
        )

    def test_transient_zero_is_ignored_only_during_short_send_grace(self):
        deadlines = [500.0, 600.0, 700.0]

        self.assertEqual(
            reconcile_march_deadlines(deadlines, 0, 180.0, 300.0),
            deadlines,
        )
        self.assertEqual(effective_active_marches(0, 3, 3, 180.0, 300.0), 3)
        self.assertEqual(reconcile_march_deadlines(deadlines, 0, 301.0, 300.0), [])
        self.assertEqual(effective_active_marches(0, 3, 3, 301.0, 300.0), 0)

    def test_missing_march_button_defers_after_squad_screen_grace(self):
        task = {"uses_march": True}
        self.assertFalse(no_available_squad_wait_exceeded(task, {"create_squad"}, 7.9))
        self.assertTrue(no_available_squad_wait_exceeded(task, {"create_squad"}, 8.0))
        self.assertFalse(no_available_squad_wait_exceeded(task, {"create_squad", "march"}, 20.0))

    def test_system_template_can_be_disabled_for_one_routine(self):
        image = {"disabled_routine_ids": ["radar"]}
        self.assertFalse(image_is_allowed_for_routine(image, "radar"))
        self.assertTrue(image_is_allowed_for_routine(image, "oil"))

        startup_image = {"startup_only": True}
        self.assertTrue(image_is_allowed_for_routine(startup_image, "game_login"))
        self.assertFalse(image_is_allowed_for_routine(startup_image, "vip_rewards"))
        self.assertFalse(
            image_is_allowed_for_routine(
                startup_image,
                "game_login",
                routine_started=True,
            )
        )

        login_only = {"only_routine_ids": ["game_login"]}
        self.assertTrue(image_is_allowed_for_routine(login_only, "game_login"))
        self.assertFalse(image_is_allowed_for_routine(login_only, "heal"))

    def test_runtime_steps_block_unsafe_action_until_prerequisite(self):
        image = {"requires_runtime_steps": ["boost_category"]}
        self.assertFalse(runtime_step_is_ready(image, {"open_bag"}))
        self.assertTrue(runtime_step_is_ready(image, {"open_bag", "boost_category"}))

    def test_pending_healing_allows_collection_entry_only(self):
        task = {
            "id": "heal",
            "settings": {"_collection_pending": True},
        }

        for step in ("healing_overview", "start_healing"):
            self.assertFalse(
                healing_pending_allows_image({"runtime_step": step}, task)
            )
        self.assertTrue(
            healing_pending_allows_image(
                {"runtime_step": "open_wounded"},
                task,
            )
        )
        self.assertTrue(
            healing_pending_allows_image(
                {"runtime_step": "collect_finished"},
                task,
            )
        )

    def test_runtime_step_any_mode_accepts_selected_boost(self):
        image = {
            "requires_runtime_steps": ["boost_8h", "boost_24h"],
            "runtime_step_mode": "any",
        }
        self.assertFalse(runtime_step_is_ready(image, {"boost_category"}))
        self.assertTrue(runtime_step_is_ready(image, {"boost_24h"}))

    def test_gathering_boost_duration_must_match_exactly(self):
        boost_8h = {
            "required_setting_key": "boost_hours",
            "required_setting_value": 8,
        }
        boost_24h = {
            "required_setting_key": "boost_hours",
            "required_setting_value": 24,
        }

        self.assertTrue(setting_requirement_matches(boost_8h, {"boost_hours": 8}))
        self.assertFalse(setting_requirement_matches(boost_8h, {"boost_hours": 24}))
        self.assertFalse(setting_requirement_matches(boost_24h, {"boost_hours": 8}))
        self.assertTrue(setting_requirement_matches(boost_24h, {"boost_hours": 24}))

    def test_gathering_boost_uses_the_duration_that_was_actually_selected(self):
        self.assertEqual(gathering_boost_duration_hours({"boost_8h"}, 8), 8.0)
        self.assertEqual(gathering_boost_duration_hours({"boost_24h"}, 8), 24.0)
        self.assertEqual(gathering_boost_duration_hours(set(), 12), 12.0)

    def test_gathering_boost_deadline_only_blocks_while_it_is_future(self):
        task = {"settings": {"active_until": 130.0}}
        self.assertEqual(gathering_boost_active_until(task, now=100.0), 130.0)
        self.assertEqual(gathering_boost_active_until(task, now=130.0), 0.0)

    def test_gathering_boost_deadline_uses_current_time_by_default(self):
        task = {"settings": {"active_until": time.time() + 60.0}}
        self.assertGreater(gathering_boost_active_until(task), 0.0)

    def test_completed_runtime_step_is_not_scanned_again(self):
        image = {"runtime_step": "world_search"}
        self.assertTrue(runtime_step_is_ready(image, set()))
        self.assertFalse(runtime_step_is_ready(image, {"world_search"}))

    def test_old_resource_profile_is_upgraded_to_strict_sequence(self):
        import uuid

        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        region_uid = str(uuid.uuid5(namespace, "wood:region"))
        icon_uid = str(uuid.uuid5(namespace, "wood:resource_icon"))
        search_uid = str(uuid.uuid5(namespace, "wood:search_button"))
        gather_uid = str(uuid.uuid5(namespace, "wood:gather"))
        level6_uid = str(uuid.uuid5(namespace, "resource_result_level:6"))
        images = [
            {"uid": region_uid},
            {"uid": icon_uid},
            {"uid": search_uid},
            {"uid": gather_uid},
            {"uid": level6_uid},
        ]
        tasks = [{"id": "wood", "timeout_seconds": 10.0}]

        self.assertEqual(upgrade_resource_runtime_metadata(images, tasks), 4)
        self.assertEqual(images[0]["action"], "open_world_search")
        self.assertEqual(images[0]["runtime_step"], "world_search")
        self.assertEqual(images[0]["search_region"], [0, 560, 150, 160])
        self.assertEqual(images[1]["requires_runtime_steps"], ["world_search"])
        self.assertEqual(images[2]["requires_runtime_steps"], ["world_search"])
        self.assertTrue(images[1]["allow_runtime_resume"])
        self.assertTrue(runtime_step_is_ready(images[1], set()))
        self.assertEqual(images[3]["expected_result_level_setting"], "resource_level")
        self.assertEqual(set(images[3]["result_level_template_uids"]), {"6", "7"})
        self.assertEqual(images[4]["search_region"], [570, 340, 150, 120])
        self.assertEqual(images[4]["confidence"], 0.65)
        self.assertTrue(all(image["allow_repeat"] for image in images[:4]))
        self.assertTrue(all(image["block_seconds"] == 2.0 for image in images[:4]))
        self.assertEqual(tasks[0]["timeout_seconds"], 30.0)

    def test_resource_result_level_uses_strongest_match_not_mapping_order(self):
        from buzzbot.routines import select_best_resource_result_level

        self.assertEqual(
            select_best_resource_result_level([("6", 0.88), ("7", 0.96)]),
            7,
        )
        self.assertEqual(
            select_best_resource_result_level([("7", 0.91), ("6", 0.97)]),
            6,
        )
        self.assertIsNone(select_best_resource_result_level([]))
        self.assertEqual(
            select_best_resource_result_level(
                [],
                raw_matches=[("6", 0.413), ("7", 0.646)],
            ),
            7,
        )
        self.assertIsNone(
            select_best_resource_result_level(
                [],
                raw_matches=[("6", 0.59), ("7", 0.646)],
            )
        )
        self.assertIsNone(
            select_best_resource_result_level(
                [],
                raw_matches=[("6", 0.50), ("7", 0.61)],
            )
        )

    def test_resource_search_retries_only_before_gather_and_within_limit(self):
        task = {"id": "metal"}
        self.assertTrue(resource_search_retry_due(task, {"search_button"}, 0))
        self.assertTrue(resource_search_retry_due(task, {"world_search", "search_button"}, 2))
        self.assertFalse(resource_search_retry_due(task, {"search_button", "gather"}, 0))
        self.assertFalse(resource_search_retry_due(task, {"search_button"}, 3))
        self.assertFalse(resource_search_retry_due({"id": "radar"}, {"search_button"}, 0))

    def test_confirmed_radar_marker_allows_small_animation_offset(self):
        keys = {("marker-1", 415, 507)}
        self.assertTrue(radar_marker_was_confirmed("marker-1", 421, 512, keys))
        self.assertTrue(radar_marker_was_confirmed("marker-1", 440, 512, keys))
        self.assertFalse(radar_marker_was_confirmed("marker-1", 450, 512, keys))
        self.assertFalse(radar_marker_was_confirmed("marker-2", 415, 507, keys))

    def test_new_radar_card_forgets_previous_card_steps(self):
        completed = {
            "radar_marker",
            "radar_forward",
            "radar_action",
            "radar_squad",
            "radar_march",
        }

        reset_radar_card_runtime_steps(completed)

        self.assertEqual(completed, set())

    def test_radar_retries_running_marches_before_the_next_fixed_reset(self):
        task = next(task for task in default_routine_tasks() if task["id"] == "radar_marches")
        now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc).timestamp()

        self.assertEqual(next_run_after_radar_pass(task, now, True), now + 300.0)
        self.assertEqual(
            next_run_after_radar_pass(task, now, False),
            datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc).timestamp(),
        )
        task["settings"]["in_progress_retry_minutes"] = "invalid"
        self.assertEqual(next_run_after_radar_pass(task, now, True), now + 300.0)

    def test_radar_markers_do_not_use_the_pass_shop_notification(self):
        reward_marker = {"requires_radar_notification": False}
        quick_marker = {"requires_radar_notification": True}

        self.assertFalse(radar_marker_requires_notification(reward_marker, "radar_rewards"))
        self.assertFalse(radar_marker_requires_notification(quick_marker, "radar_quick"))
        self.assertFalse(radar_marker_requires_notification({}, "radar_rewards"))
        self.assertFalse(radar_marker_requires_notification({}, "radar_marches"))

    def test_healing_training_and_hunts_are_upgraded_to_strict_sequences(self):
        import uuid

        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        training_uids = {
            step: str(uuid.uuid5(namespace, f"train_infantry:{step}"))
            for step in ("queue", "building", "train")
        }
        hunt_uids = {
            step: str(uuid.uuid5(namespace, f"zombie_hunt:{step}"))
            for step in ("region", "world_search", "zombie_icon", "search", "march")
        }
        images = [
            *({"uid": uid} for uid in training_uids.values()),
            *({"uid": uid} for uid in hunt_uids.values()),
        ]
        tasks = [
            {"id": "heal", "timeout_seconds": 12.0},
            {"id": "train_infantry", "timeout_seconds": 12.0},
            {"id": "zombie_hunt", "timeout_seconds": 12.0},
        ]

        self.assertEqual(upgrade_strict_runtime_metadata(images, tasks), 8)
        by_uid = {image["uid"]: image for image in images}
        self.assertNotIn("requires_runtime_steps", by_uid[training_uids["building"]])
        self.assertTrue(by_uid[training_uids["queue"]]["repeat_runtime_step"])
        self.assertTrue(by_uid[training_uids["queue"]]["dynamic_building_search"])
        self.assertEqual(by_uid[training_uids["queue"]]["limit_key"], "max_queue_checks")
        self.assertTrue(by_uid[training_uids["queue"]]["defer_when_limit_reached"])
        self.assertLessEqual(by_uid[training_uids["queue"]]["confidence"], 0.64)
        self.assertTrue(by_uid[training_uids["queue"]]["training_queue_region"])
        self.assertEqual(by_uid[training_uids["queue"]]["training_queue_ordinal"], 1)
        self.assertEqual(by_uid[training_uids["queue"]]["training_radial_target"], [758, 487])
        self.assertTrue(tasks[0]["empty_home_is_success"])
        self.assertEqual(tasks[0]["interval_minutes"], 0.1)
        self.assertEqual(tasks[1]["settings"]["max_queue_checks"], 5)
        self.assertEqual(
            by_uid[training_uids["train"]]["requires_runtime_steps"],
            ["building"],
        )
        self.assertEqual(by_uid[hunt_uids["region"]]["action"], "open_world_search")
        self.assertEqual(
            by_uid[hunt_uids["region"]]["next_template_uid"],
            hunt_uids["world_search"],
        )
        self.assertEqual(
            by_uid[hunt_uids["zombie_icon"]]["requires_runtime_steps"],
            ["world_search"],
        )
        self.assertEqual(tasks[0]["timeout_seconds"], 8.0)
        self.assertEqual(tasks[1]["timeout_seconds"], 20.0)
        self.assertTrue(by_uid[hunt_uids["march"]]["confirm_disappears"])
        self.assertTrue(by_uid[hunt_uids["search"]]["allow_repeat"])
        self.assertEqual(by_uid[hunt_uids["search"]]["block_seconds"], 2.0)

    def test_finished_healing_marker_uses_verified_collection_action(self):
        import uuid

        collect_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "heal:collect_finished"))
        collect_alt_uid = str(
            uuid.uuid5(PROFILE_NAMESPACE, "heal:collect_finished_alt_1")
        )
        open_wounded_uid = str(
            uuid.uuid5(PROFILE_NAMESPACE, "heal:open_wounded")
        )
        images = [
            {"uid": collect_uid, "confidence": 0.88, "grayscale": False},
            {"uid": collect_alt_uid, "confidence": 0.88, "grayscale": False},
            {"uid": open_wounded_uid},
        ]
        tasks = [{"id": "heal", "timeout_seconds": 20.0}]

        self.assertEqual(upgrade_strict_runtime_metadata(images, tasks), 3)
        self.assertEqual(images[0]["action"], "collect_healed_troops")
        self.assertTrue(images[0]["observer_only"])
        self.assertEqual(images[0]["confidence"], 0.70)
        self.assertTrue(images[0]["grayscale"])
        self.assertEqual(images[0]["search_region"], [120, 70, 1040, 550])
        self.assertEqual(images[1]["action"], "click")
        self.assertEqual(images[1]["description"], "Открыть панель лечения")
        self.assertEqual(images[1]["confidence"], 0.78)
        self.assertTrue(images[1]["grayscale"])
        self.assertEqual(images[1]["search_region"], [1150, 430, 130, 190])
        self.assertEqual(images[1]["runtime_step"], "healing_overview")
        self.assertNotIn("required_setting_key", images[1])
        self.assertEqual(images[2]["action"], "open_healing_hospital")
        self.assertTrue(images[2]["allow_repeat"])
        self.assertEqual(images[2]["block_seconds"], 0.5)
        self.assertEqual(tasks[0]["interval_minutes"], 0.1)
        self.assertEqual(tasks[0]["timeout_seconds"], 8.0)

    def test_healing_start_uses_short_verified_settle_delay(self):
        import uuid

        start_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "heal:start_healing"))
        images = [{"uid": start_uid, "delay": 0.8}]
        tasks = [{"id": "heal", "timeout_seconds": 8.0}]

        self.assertEqual(upgrade_strict_runtime_metadata(images, tasks), 1)
        self.assertEqual(images[0]["delay"], 0.6)

    def test_research_queue_allows_lab_selection_before_deferred(self):
        research_queue_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:queue"))
        research_lab_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:lab"))
        research_lab_alt_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "research:lab_alt_1"))
        images = [
            {"uid": research_queue_uid, "allow_repeat": True},
            {"uid": research_lab_uid, "confidence": 0.88},
            {"uid": research_lab_alt_uid, "confidence": 0.88},
        ]
        tasks = [{"id": "research", "settings": {"branch": "economy"}}]

        self.assertEqual(upgrade_strict_runtime_metadata(images, tasks), 3)
        self.assertEqual(images[0]["limit_key"], "max_lab_checks")
        self.assertEqual(images[0]["action"], "select_research_queue")
        self.assertTrue(images[0]["defer_when_limit_reached"])
        self.assertLessEqual(images[1]["confidence"], 0.84)
        self.assertLessEqual(images[2]["confidence"], 0.84)
        self.assertEqual(tasks[0]["settings"]["max_lab_checks"], 2)

    def test_animated_active_boost_marker_completes_without_reapplying(self):
        import uuid

        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        active_uid = str(uuid.uuid5(namespace, "gathering_boost:active"))
        images = [{"uid": active_uid, "confidence": 0.9}]

        upgrade_strict_runtime_metadata(images, default_routine_tasks())

        self.assertEqual(images[0]["confidence"], 0.75)
        self.assertEqual(images[0]["orb_match_threshold"], 3)
        self.assertTrue(images[0]["completes_routine"])

    def test_old_profile_cannot_replace_eight_hour_boost_with_twenty_four(self):
        boost_uid = str(
            uuid.uuid5(PROFILE_NAMESPACE, "gathering_boost:boost_24h")
        )
        images = [{"uid": boost_uid, "allow_higher_setting_fallback": True}]

        upgrade_strict_runtime_metadata(images, default_routine_tasks())

        self.assertNotIn("allow_higher_setting_fallback", images[0])

    def test_mail_moves_to_the_next_category_when_claim_button_is_absent(self):
        steps = (
            "open_mail",
            "select_system",
            "claim_system",
            "select_alliance",
            "claim_alliance",
            "select_reports",
            "claim_reports",
        )
        images = [
            {
                "uid": str(uuid.uuid5(PROFILE_NAMESPACE, f"mail_rewards:{step}")),
                "requires_runtime_steps": ["wrong_previous_step"],
            }
            for step in steps
        ]
        tasks = [{"id": "mail_rewards"}]

        self.assertEqual(upgrade_strict_runtime_metadata(images, tasks), len(steps))
        by_step = dict(zip(steps, images))
        self.assertTrue(
            runtime_step_is_ready(by_step["select_alliance"], {"select_system"})
        )
        self.assertTrue(
            runtime_step_is_ready(by_step["select_reports"], {"select_alliance"})
        )
        self.assertFalse(
            runtime_step_is_ready(by_step["claim_alliance"], {"select_system"})
        )
        self.assertEqual(tasks[0]["completion_runtime_step"], "claim_reports")

    def test_completed_tasks_can_resume_when_claim_switches_to_daily_tab(self):
        import uuid

        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        scroll_uid = str(
            uuid.uuid5(namespace, "completed_tasks:scroll_daily_1")
        )
        images = [{"uid": scroll_uid, "requires_runtime_steps": ["select_daily"]}]

        self.assertEqual(upgrade_strict_runtime_metadata(images, []), 1)
        self.assertEqual(images[0]["requires_runtime_steps"], ["open_tasks"])
        self.assertEqual(images[0]["implied_runtime_steps"], ["select_daily"])
        self.assertTrue(runtime_step_is_ready(images[0], {"open_tasks"}))

    def test_main_mission_claim_stops_after_daily_tab_is_selected(self):
        claim_uid = str(
            uuid.uuid5(PROFILE_NAMESPACE, "completed_tasks:claim_main")
        )
        claim = {
            "uid": claim_uid,
            "runtime_step": "claim_main",
            "repeat_runtime_step": True,
            "requires_runtime_steps": ["open_tasks"],
        }

        self.assertEqual(upgrade_strict_runtime_metadata([claim], []), 1)
        self.assertTrue(runtime_step_is_ready(claim, {"open_tasks"}))
        self.assertFalse(
            runtime_step_is_ready(claim, {"open_tasks", "select_daily"})
        )

    def test_prize_hunt_repeat_never_clicks_the_result_exit_button(self):
        import uuid

        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        uids = {
            step: str(uuid.uuid5(namespace, f"prize_hunt:{step}"))
            for step in (
                "campaign",
                "enter",
                "open_squad",
                "prepare",
                "no_deployable_squad",
                "deploy",
                "safe_exit",
                "safe_exit_current",
                "again",
                "match",
                "confirm",
            )
        }
        images = [
            {"uid": uids["enter"], "confidence": 0.8},
            {"uid": uids["open_squad"], "action": "click", "confidence": 0.88},
            {"uid": uids["prepare"], "action": "prize_prepare", "confidence": 0.88},
            {"uid": uids["no_deployable_squad"], "confidence": 0.88},
            {"uid": uids["deploy"]},
            {"uid": uids["safe_exit"]},
            {
                "uid": uids["safe_exit_current"],
                "complete_if_setting_false": "repeat_until_stopped",
            },
            *({"uid": uids[step]} for step in ("again", "match", "confirm")),
        ]
        tasks = [{"id": "prize_hunt", "timeout_seconds": 10.0}]

        images.insert(0, {"uid": uids["campaign"], "confidence": 0.88})

        self.assertEqual(upgrade_prize_hunt_metadata(images, tasks), 9)
        by_uid = {image["uid"]: image for image in images}
        self.assertEqual(by_uid[uids["campaign"]]["confidence"], 0.84)
        self.assertEqual(by_uid[uids["open_squad"]]["action"], "prize_start_or_prepare")
        self.assertTrue(by_uid[uids["open_squad"]]["grayscale"])
        self.assertEqual(by_uid[uids["open_squad"]]["confidence"], 0.84)
        self.assertEqual(by_uid[uids["prepare"]]["action"], "prize_prepare")
        self.assertEqual(
            by_uid[uids["no_deployable_squad"]]["defer_routine_reason"],
            "нет развертываемого отряда",
        )
        self.assertEqual(
            by_uid[uids["no_deployable_squad"]]["requires_runtime_steps"],
            ["prepare", "open_squad"],
        )
        self.assertEqual(
            by_uid[uids["no_deployable_squad"]]["runtime_step_mode"],
            "any",
        )
        self.assertTrue(by_uid[uids["no_deployable_squad"]]["allow_runtime_resume"])
        self.assertEqual(by_uid[uids["no_deployable_squad"]]["routine_priority"], 1)
        self.assertEqual(
            by_uid[uids["deploy"]]["requires_runtime_steps"],
            ["prepare", "open_squad"],
        )
        self.assertEqual(by_uid[uids["deploy"]]["runtime_step_mode"], "any")
        self.assertFalse(by_uid[uids["safe_exit"]]["required_setting_value"])
        self.assertNotIn(
            "complete_if_setting_false",
            by_uid[uids["safe_exit_current"]],
        )
        self.assertTrue(by_uid[uids["again"]]["required_setting_value"])
        self.assertEqual(by_uid[uids["enter"]]["confidence"], 0.74)
        self.assertEqual(
            by_uid[uids["again"]]["requires_runtime_steps"],
            ["safe_exit_current", "deploy", "enter"],
        )
        self.assertEqual(by_uid[uids["again"]]["runtime_step_mode"], "any")
        self.assertTrue(by_uid[uids["again"]]["allow_runtime_resume"])
        self.assertEqual(
            by_uid[uids["confirm"]]["requires_runtime_steps"],
            ["match"],
        )
        self.assertEqual(tasks[0]["timeout_seconds"], 1800.0)

    def test_prize_hunt_branch_hard_guard(self):
        import uuid

        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        exit_image = {
            "uid": str(uuid.uuid5(namespace, "prize_hunt:safe_exit")),
        }
        again_image = {
            "uid": str(uuid.uuid5(namespace, "prize_hunt:again")),
        }
        self.assertFalse(prize_hunt_branch_allows_image(exit_image, True))
        self.assertTrue(prize_hunt_branch_allows_image(again_image, True))
        self.assertTrue(prize_hunt_branch_allows_image(exit_image, False))
        self.assertFalse(prize_hunt_branch_allows_image(again_image, False))

    def test_zombie_lower_levels_and_collective_level_are_selectable(self):
        zombie_keys = {spec["key"] for spec in task_setting_specs("zombie_hunt")}
        collective_keys = {spec["key"] for spec in task_setting_specs("collective_mind")}

        self.assertNotIn("level_min", zombie_keys)
        self.assertNotIn("level_max", zombie_keys)
        self.assertIn("fallback_levels", zombie_keys)
        self.assertIn("level", collective_keys)

        zombie = next(task for task in default_routine_tasks() if task["id"] == "zombie_hunt")
        self.assertEqual(zombie["settings"]["fallback_levels"], 3)
        self.assertEqual(zombie["march_completion_runtime_step"], "march")
        self.assertEqual(zombie_fallback_levels({"fallback_levels": -10}), 0)
        self.assertEqual(zombie_fallback_levels({"fallback_levels": 99}), 10)

        migrated = normalize_routine_tasks(
            [{
                "id": "zombie_hunt",
                "march_completion_runtime_step": "",
                "settings": {"level_min": 1, "level_max": 10},
            }]
        )
        migrated_zombie = next(task for task in migrated if task["id"] == "zombie_hunt")
        self.assertNotIn("level_min", migrated_zombie["settings"])
        self.assertNotIn("level_max", migrated_zombie["settings"])
        self.assertEqual(migrated_zombie["settings"]["fallback_levels"], 3)
        self.assertEqual(migrated_zombie["march_completion_runtime_step"], "march")

    def test_strict_sequence_can_resume_from_visible_later_step(self):
        image = {
            "runtime_step": "create_squad",
            "requires_runtime_steps": ["attack"],
            "allow_runtime_resume": True,
        }
        self.assertTrue(runtime_step_is_ready(image, set()))
        self.assertFalse(runtime_step_is_ready(image, {"search"}))
        self.assertTrue(runtime_step_is_ready(image, {"attack"}))
        image["implied_runtime_steps"] = ["world_search", "attack"]
        self.assertEqual(
            completed_runtime_steps_for_image(image),
            {"world_search", "attack", "create_squad"},
        )

        regular_image = {
            "runtime_step": "create_squad",
            "requires_runtime_steps": ["attack"],
        }
        self.assertFalse(runtime_step_is_ready(regular_image, set()))

    def test_radar_finishes_on_empty_screen_instead_of_action_limit(self):
        import uuid

        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        detail_uid = str(uuid.uuid5(namespace, "radar_quick:open_supply"))
        marker_uid = str(uuid.uuid5(namespace, "radar_quick:task_supply"))
        wait_uid = str(uuid.uuid5(namespace, "radar_quick:wait_in_progress"))
        march_uid = str(uuid.uuid5(namespace, "radar_quick:march"))
        action_uid = str(uuid.uuid5(namespace, "radar_quick:collect_supply"))
        return_uid = str(uuid.uuid5(namespace, "radar_quick:return_shelter"))
        open_uid = str(uuid.uuid5(namespace, "radar_quick:open_radar"))
        images = [
            {"uid": marker_uid},
            {"uid": detail_uid, "limit_key": "max_tasks"},
            {"uid": wait_uid},
            {"uid": march_uid},
            {"uid": open_uid},
            {"uid": action_uid, "delay": 0.8},
            {"uid": return_uid},
        ]
        tasks = [{"id": "radar_quick", "timeout_seconds": 15.0}]

        self.assertEqual(upgrade_radar_runtime_metadata(images, tasks), 7)
        self.assertLess(images[4]["routine_priority"], images[2]["routine_priority"])
        self.assertFalse(images[4]["enabled"])
        self.assertLess(images[2]["routine_priority"], images[1]["routine_priority"])
        self.assertLess(images[1]["routine_priority"], images[0]["routine_priority"])
        self.assertNotIn("limit_key", images[1])
        self.assertTrue(images[0]["prevents_idle_completion"])
        self.assertEqual(tasks[0]["timeout_seconds"], 15.0)
        self.assertTrue(tasks[0]["complete_when_idle"])
        self.assertEqual(tasks[0]["idle_confirmations"], 2)
        self.assertFalse(tasks[0]["manual_screen_required"])
        self.assertTrue(tasks[0]["settings"]["visual_fallback"])
        marker = next(image for image in images if image["uid"] == marker_uid)
        march = next(image for image in images if image["uid"] == march_uid)
        self.assertEqual(marker["confidence"], 0.68)
        self.assertEqual(marker["orb_match_threshold"], 3)
        self.assertEqual(marker["block_seconds"], 8.0)
        self.assertFalse(marker["requires_radar_notification"])
        self.assertTrue(march["confirms_radar_marker"])
        self.assertEqual(march["runtime_step"], "radar_march")
        self.assertEqual(images[5]["requires_runtime_steps"], ["radar_forward"])
        self.assertEqual(images[5]["delay"], 1.5)
        self.assertEqual(images[6]["action"], "radar_return_shelter")
        self.assertNotIn("completes_routine", images[6])
        self.assertEqual(
            images[6]["requires_runtime_steps"],
            ["radar_action", "radar_march"],
        )
        self.assertEqual(images[2]["action"], "radar_defer_in_progress")
        self.assertEqual(tasks[0]["settings"]["in_progress_retry_minutes"], 5)

    def test_radar_reward_upgrade_accepts_completed_markers_without_red_dot(self):
        marker_uid = str(uuid.uuid5(PROFILE_NAMESPACE, "radar_rewards:task_car_reward"))
        images = [{"uid": marker_uid}]
        tasks = [{"id": "radar_rewards", "timeout_seconds": 12.0}]

        upgrade_radar_runtime_metadata(images, tasks)

        self.assertFalse(images[0]["requires_radar_notification"])


if __name__ == "__main__":
    unittest.main()
