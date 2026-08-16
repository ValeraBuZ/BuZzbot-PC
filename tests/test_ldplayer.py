import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buzzbot.ldplayer import (
    adb_debug_enabled,
    bridged_adb_serial_for_index,
    enable_adb_debug,
    index_from_serial,
    launch_instance,
    parse_list2,
    serial_for_index,
    tcp_serial_for_index,
)


class LDPlayerTests(unittest.TestCase):
    def test_list2_parses_running_instance_and_serial(self):
        instances = parse_list2("3,zZuB3,10,20,1,21240,10412,1280,720,240\n")
        self.assertEqual(len(instances), 1)
        self.assertTrue(instances[0].running)
        self.assertEqual(instances[0].adb_serial, "emulator-5560")
        self.assertEqual(serial_for_index(5), "emulator-5564")
        self.assertEqual(index_from_serial("emulator-5560"), 3)
        self.assertEqual(tcp_serial_for_index(2), "127.0.0.1:5559")
        self.assertEqual(index_from_serial("127.0.0.1:5559"), 2)

    def test_enabling_adb_creates_backup_and_updates_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ldconsole = root / "ldconsole.exe"
            ldconsole.write_bytes(b"")
            config_dir = root / "vms" / "config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "leidian3.config"
            config_path.write_text(
                json.dumps({"basicSettings.adbDebug": 0, "advancedSettings.resolution": {"width": 1280}}),
                encoding="utf-8",
            )

            self.assertFalse(adb_debug_enabled(ldconsole, 3))
            self.assertTrue(enable_adb_debug(ldconsole, 3))
            self.assertTrue(adb_debug_enabled(ldconsole, 3))
            self.assertTrue(config_path.with_suffix(".config.buzzbot.bak").is_file())
            self.assertFalse(enable_adb_debug(ldconsole, 3))

    def test_bridged_adb_serial_uses_latest_runtime_address(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "leidian5_vbox.log"
            log_path.write_text(
                "initADB\t(1714):emulator adbmode: 1, 192.168.0.41\n"
                "initADB\t(1714):emulator adbmode: 1, 192.168.0.53\n",
                encoding="utf-8",
            )

            self.assertEqual(
                bridged_adb_serial_for_index(5, temp_dir),
                "192.168.0.53:5555",
            )

    @patch("buzzbot.ldplayer._run_ldconsole")
    def test_launch_instance_uses_hidden_ldconsole_command(self, run_ldconsole):
        launch_instance(Path("ldconsole.exe"), 5)
        run_ldconsole.assert_called_once_with(
            Path("ldconsole.exe"),
            ["launch", "--index", 5],
            timeout=20,
        )


if __name__ == "__main__":
    unittest.main()
