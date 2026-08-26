import unittest
from tempfile import TemporaryDirectory

from buzzbot.device_lock import DeviceLease, canonical_device_key
from buzzbot.multi_emulator import prepare_worker_config, runtime_dir_for_instance
from buzzbot_app import should_autostart_all_emulators, should_run_multi_worker


class MultiEmulatorTests(unittest.TestCase):
    def test_worker_gets_same_tasks_and_isolated_player_profile(self):
        source = {
            "routine_tasks": [
                {"id": "zombie_hunt", "enabled": True, "settings": {"level": 10}},
                {"id": "food", "enabled": False, "settings": {"level": 7}},
            ],
            "account_profiles": [{"id": "old", "adb_serial": "emulator-5554"}],
            "account_rotation_enabled": True,
            "routine_next_run": {"zombie_hunt": 999999.0},
            "images": [{"path": "img/template.png"}],
        }

        worker = prepare_worker_config(
            source,
            serial="192.168.0.55:5555",
            index=6,
            name="ФокусФерма-6",
            width=1280,
            height=720,
        )

        self.assertEqual(worker["adb_serial"], "192.168.0.55:5555")
        self.assertEqual(worker["current_account_id"], worker["account_profiles"][0]["id"])
        self.assertEqual(worker["account_profiles"][0]["ldplayer_index"], 6)
        self.assertEqual(
            worker["account_profiles"][0]["task_enabled"],
            {"zombie_hunt": True, "food": False},
        )
        self.assertEqual(worker["routine_next_run"], {"zombie_hunt": 0.0, "food": 0.0})
        self.assertFalse(worker["account_rotation_enabled"])
        self.assertEqual(worker["images"], source["images"])
        self.assertEqual(source["routine_next_run"]["zombie_hunt"], 999999.0)

    def test_runtime_directory_is_stable_per_ldplayer(self):
        path = runtime_dir_for_instance("C:/BuZzbot", 3)
        self.assertEqual(path.name, "ldplayer_3")
        self.assertEqual(path.parent.name, "workers")

    def test_multi_emulator_command_line_flags_are_explicit(self):
        self.assertTrue(should_autostart_all_emulators(["--autostart-all"]))
        self.assertFalse(should_autostart_all_emulators(["--autostart"]))
        self.assertTrue(should_run_multi_worker(["--worker", "--autostart"]))

    def test_only_one_process_can_lease_an_adb_device(self):
        with TemporaryDirectory() as temp_dir:
            first = DeviceLease("emulator-5556", temp_dir)
            second = DeviceLease("emulator-5556", temp_dir)

            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_adb_aliases_of_one_ldplayer_share_the_same_lease(self):
        with TemporaryDirectory() as temp_dir:
            first = DeviceLease("emulator-5556", temp_dir)
            second = DeviceLease("127.0.0.1:5557", temp_dir)

            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_different_ldplayers_can_run_in_parallel(self):
        with TemporaryDirectory() as temp_dir:
            first = DeviceLease("emulator-5556", temp_dir)
            second = DeviceLease("127.0.0.1:5559", temp_dir)

            self.assertTrue(first.acquire())
            self.assertTrue(second.acquire())
            first.release()
            second.release()

    def test_bridged_serial_uses_known_ldplayer_index(self):
        self.assertEqual(
            canonical_device_key("192.168.0.53:5555", ldplayer_index=5),
            "ldplayer_5",
        )

    def test_standard_serial_wins_over_stale_saved_index(self):
        self.assertEqual(
            canonical_device_key("emulator-5556", ldplayer_index=5),
            "ldplayer_1",
        )


if __name__ == "__main__":
    unittest.main()
