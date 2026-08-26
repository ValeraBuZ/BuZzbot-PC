import json
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
import zipfile

from buzzbot.version import APP_VERSION

import cv2
import numpy as np


class ProfileBundleTests(unittest.TestCase):
    def test_profile_installer_can_run_as_a_script(self):
        project_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "tools/install_training_profile.py", "--help"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gathering_boost_templates_exclude_inventory_counts(self):
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "BuZzbot_PC_1280x720.zip"
        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        boost_uids = {
            str(uuid.uuid5(namespace, "gathering_boost:boost_8h")),
            str(uuid.uuid5(namespace, "gathering_boost:boost_24h")),
        }

        with zipfile.ZipFile(profile_path) as archive:
            manifest = json.loads(archive.read("profile.json"))
            images = {image["uid"]: image for image in manifest["images"]}
            for uid in boost_uids:
                encoded = np.frombuffer(archive.read(images[uid]["path"]), dtype=np.uint8)
                template = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                self.assertIsNotNone(template)
                self.assertLessEqual(template.shape[0], 82)

            boost_24h_uid = str(uuid.uuid5(namespace, "gathering_boost:boost_24h"))
            self.assertFalse(
                images[boost_24h_uid].get("allow_higher_setting_fallback", False)
            )

    def test_portable_profile_contains_startup_and_radar_recovery(self):
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "BuZzbot_PC_1280x720.zip"
        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        expected = {
            str(uuid.uuid5(namespace, "system:beast_taming_close")),
            str(uuid.uuid5(namespace, "system:google_play_cancel")),
            str(uuid.uuid5(namespace, "system:last_igg_login")),
            str(uuid.uuid5(namespace, "system:loading_error_reload")),
            str(uuid.uuid5(namespace, "radar_marches:close_region_search")),
        }

        with zipfile.ZipFile(profile_path) as archive:
            manifest = json.loads(archive.read("profile.json"))
            images = {image["uid"]: image for image in manifest["images"]}
            self.assertTrue(expected.issubset(images))
            for uid in expected:
                self.assertIn(images[uid]["path"], archive.namelist())
            google_uid = str(uuid.uuid5(namespace, "system:google_play_cancel"))
            self.assertGreaterEqual(images[google_uid]["delay"], 8.0)
            login_uid = str(uuid.uuid5(namespace, "system:last_igg_login"))
            self.assertTrue(images[login_uid]["startup_only"])
            self.assertGreaterEqual(images[login_uid]["delay"], 8.0)
            reload_uid = str(uuid.uuid5(namespace, "system:loading_error_reload"))
            self.assertTrue(images[reload_uid]["startup_only"])
            self.assertGreaterEqual(images[reload_uid]["delay"], 8.0)
            limited_trial_uid = str(uuid.uuid5(namespace, "system:limited_trial_forward"))
            self.assertTrue(images[limited_trial_uid]["startup_only"])

    def test_march_templates_require_screen_change_confirmation(self):
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "BuZzbot_PC_1280x720.zip"
        with zipfile.ZipFile(profile_path) as archive:
            manifest = json.loads(archive.read("profile.json"))

        march_images = [
            image for image in manifest["images"]
            if image.get("runtime_step") == "march"
        ]
        self.assertTrue(march_images)
        self.assertTrue(all(image.get("confirm_disappears") for image in march_images))

    def test_radar_marches_defer_when_no_squad_can_be_deployed(self):
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "BuZzbot_PC_1280x720.zip"
        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        uid = str(uuid.uuid5(namespace, "radar_marches:no_deployable_squad"))

        with zipfile.ZipFile(profile_path) as archive:
            manifest = json.loads(archive.read("profile.json"))
        images = {image["uid"]: image for image in manifest["images"]}

        self.assertEqual(images[uid]["action"], "observe")
        self.assertIn("нет доступного отряда", images[uid]["defer_routine_reason"])

    def test_collective_no_result_is_observed_but_never_clicked(self):
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "BuZzbot_PC_1280x720.zip"
        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        no_result_uid = str(uuid.uuid5(namespace, "collective_mind:no_result"))
        search_uid = str(uuid.uuid5(namespace, "collective_mind:search"))

        with zipfile.ZipFile(profile_path) as archive:
            manifest = json.loads(archive.read("profile.json"))
        images = {image["uid"]: image for image in manifest["images"]}

        self.assertFalse(images[no_result_uid]["enabled"])
        self.assertTrue(images[no_result_uid]["observer_only"])
        self.assertEqual(images[search_uid]["no_result_template_uid"], no_result_uid)

    def test_wasteland_profile_contains_live_event_flow(self):
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "BuZzbot_PC_1280x720.zip"
        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        steps = {
            "event_entry",
            "unavailable",
            "intro_map",
            "attack",
            "bypass",
            "completed",
            "collect",
            "reward_close",
            "explore",
            "stamina_empty",
        }

        with zipfile.ZipFile(profile_path) as archive:
            manifest = json.loads(archive.read("profile.json"))
            images = {image["uid"]: image for image in manifest["images"]}

        tasks = {task["id"]: task for task in manifest["routine_tasks"]}
        task = tasks["wasteland_exploration"]
        self.assertEqual(task["settings"]["fixed_utc_hours"], [1])
        self.assertFalse(task["empty_home_is_success"])
        self.assertEqual(task["completion_runtime_step"], "stamina_empty")
        self.assertEqual(task["settings"]["stamina_retry_minutes"], 12)

        wasteland_images = {
            step: images[str(uuid.uuid5(namespace, f"wasteland_exploration:{step}"))]
            for step in steps
        }
        self.assertTrue(all(image["use_orb"] for image in wasteland_images.values()))
        self.assertTrue(all(image["orb_match_threshold"] == 3 for image in wasteland_images.values()))
        self.assertEqual(wasteland_images["event_entry"]["search_region"], [350, 20, 650, 260])
        self.assertFalse(wasteland_images["event_entry"]["repeat_runtime_step"])
        self.assertFalse(wasteland_images["intro_map"]["repeat_runtime_step"])
        self.assertTrue(wasteland_images["reward_close"]["repeat_runtime_step"])
        self.assertEqual(wasteland_images["unavailable"]["action"], "observe")
        self.assertTrue(wasteland_images["unavailable"]["defer_routine_reason"])
        self.assertEqual(wasteland_images["reward_close"]["limit_key"], "max_encounters")
        self.assertTrue(wasteland_images["stamina_empty"]["completes_routine"])

    def test_reported_routines_have_safe_runtime_metadata(self):
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "BuZzbot_PC_1280x720.zip"
        namespace = uuid.UUID("7d37a3a8-c963-49ef-9bf2-e3daecf85c48")
        with zipfile.ZipFile(profile_path) as archive:
            manifest = json.loads(archive.read("profile.json"))

            self.assertEqual(manifest["app_version"], APP_VERSION)
        tasks = {task["id"]: task for task in manifest["routine_tasks"]}
        images = {image["uid"]: image for image in manifest["images"]}
        donation = tasks["alliance_donations"]
        self.assertGreaterEqual(donation["timeout_seconds"], 45.0)
        self.assertEqual(donation["completion_runtime_step"], "all_projects_checked")

        project_uid = str(
            uuid.uuid5(namespace, "alliance_donations:select_project_research")
        )
        marked_project_uid = str(
            uuid.uuid5(namespace, "alliance_donations:select_marked_project")
        )
        gathering_elite_uid = str(
            uuid.uuid5(namespace, "alliance_donations:select_project_gathering_elite")
        )
        select_alliance_uid = str(uuid.uuid5(namespace, "mail_rewards:select_alliance"))
        select_reports_uid = str(uuid.uuid5(namespace, "mail_rewards:select_reports"))
        claim_main_uid = str(uuid.uuid5(namespace, "completed_tasks:claim_main"))
        hospital_uid = str(uuid.uuid5(namespace, "heal:open_wounded"))
        collect_healed_uid = str(uuid.uuid5(namespace, "heal:collect_finished"))
        collect_healed_alt_uid = str(
            uuid.uuid5(namespace, "heal:collect_finished_alt_1")
        )
        zombie_search_uid = str(uuid.uuid5(namespace, "zombie_hunt:search"))
        zombie_attack_uid = str(uuid.uuid5(namespace, "zombie_hunt:attack"))
        radar_attack_uid = str(uuid.uuid5(namespace, "radar_marches:attack_zombie"))
        vehicle_queue_uid = str(uuid.uuid5(namespace, "train_vehicles:queue"))
        research_queue_uid = str(uuid.uuid5(namespace, "research:queue"))
        research_lab_uid = str(uuid.uuid5(namespace, "research:lab"))
        prize_unavailable_uid = str(
            uuid.uuid5(namespace, "prize_hunt:no_deployable_squad")
        )
        self.assertLessEqual(images[project_uid]["confidence"], 0.74)
        self.assertEqual(
            images[marked_project_uid]["action"],
            "alliance_marked_project",
        )
        self.assertEqual(
            images[gathering_elite_uid]["description"],
            "Проверить проект: сбор элиты",
        )
        self.assertEqual(
            images[select_alliance_uid]["requires_runtime_steps"],
            ["select_system"],
        )
        self.assertEqual(
            images[select_reports_uid]["requires_runtime_steps"],
            ["select_alliance"],
        )
        self.assertEqual(
            images[claim_main_uid]["disabled_after_runtime_steps"],
            ["select_daily"],
        )
        self.assertTrue(images[hospital_uid]["grayscale"])
        self.assertLessEqual(images[hospital_uid]["confidence"], 0.74)
        self.assertLessEqual(images[collect_healed_uid]["confidence"], 0.70)
        self.assertEqual(
            images[collect_healed_uid]["action"],
            "collect_healed_troops",
        )
        self.assertTrue(images[collect_healed_uid]["grayscale"])
        self.assertEqual(
            images[collect_healed_uid]["search_region"],
            [120, 70, 1040, 550],
        )
        self.assertEqual(images[collect_healed_uid]["routine_priority"], 1)
        self.assertEqual(
            images[collect_healed_alt_uid]["action"],
            "click",
        )
        self.assertEqual(
            images[collect_healed_alt_uid]["description"],
            "Открыть панель лечения",
        )
        self.assertLessEqual(images[collect_healed_alt_uid]["confidence"], 0.78)
        self.assertTrue(images[collect_healed_alt_uid]["grayscale"])
        self.assertEqual(
            images[collect_healed_alt_uid]["search_region"],
            [1150, 430, 130, 190],
        )
        self.assertEqual(
            images[collect_healed_alt_uid]["runtime_step"],
            "healing_overview",
        )
        self.assertNotIn(
            "required_setting_key",
            images[collect_healed_alt_uid],
        )
        self.assertTrue(images[zombie_search_uid]["allow_repeat"])
        self.assertEqual(images[zombie_search_uid]["block_seconds"], 2.0)
        self.assertEqual(images[zombie_attack_uid]["action"], "zombie_attack")
        self.assertEqual(images[radar_attack_uid]["action"], "zombie_attack")
        self.assertLessEqual(images[vehicle_queue_uid]["confidence"], 0.80)
        self.assertEqual(images[vehicle_queue_uid]["action"], "select_training_queue")
        self.assertEqual(images[vehicle_queue_uid]["training_queue_ordinal"], 4)
        self.assertGreaterEqual(tasks["train_vehicles"]["settings"]["max_queue_checks"], 5)
        self.assertEqual(images[research_queue_uid]["action"], "select_research_queue")
        self.assertLessEqual(images[research_lab_uid]["confidence"], 0.84)
        self.assertGreaterEqual(tasks["research"]["settings"]["max_lab_checks"], 2)
        self.assertEqual(
            images[prize_unavailable_uid]["defer_routine_reason"],
            "нет развертываемого отряда",
        )
        self.assertEqual(images[prize_unavailable_uid]["routine_priority"], 1)

        radar_tasks = {
            task_id: tasks[task_id]
            for task_id in ("radar_rewards", "radar_quick", "radar_marches")
        }
        self.assertNotIn("radar", tasks)
        self.assertTrue(all(not task["manual_screen_required"] for task in radar_tasks.values()))
        self.assertTrue(all(task["settings"]["visual_fallback"] for task in radar_tasks.values()))
        self.assertFalse(radar_tasks["radar_rewards"]["uses_march"])
        self.assertFalse(radar_tasks["radar_quick"]["uses_march"])
        self.assertTrue(radar_tasks["radar_marches"]["uses_march"])
        for task_id in radar_tasks:
            open_uid = str(uuid.uuid5(namespace, f"{task_id}:open_radar"))
            self.assertIn(open_uid, images)
            self.assertTrue(images[open_uid]["enabled"])
            self.assertTrue(images[open_uid]["requires_settlement_screen"])
            self.assertEqual(images[open_uid]["routine_priority"], 2)

if __name__ == "__main__":
    unittest.main()
