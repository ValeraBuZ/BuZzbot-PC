import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buzzbot.memory_guard import (
    GIB, CommitMemory, instance_memory_limit, instance_private_memory, restart_needed,
)
from buzzbot.ldplayer import LDPlayerInstance
from buzzbot_app import AutoClicker
import test_login_identity_gate as identity_fixture
import test_account_transition_recovery as transition_fixture


def vm(index=0, running=True):
    return LDPlayerInstance(index, "test", running, 100, 200, 1280, 720, 240)


class MemoryGuardTests(unittest.TestCase):
    def test_restart_threshold_and_early_commit_pressure(self):
        healthy = CommitMemory(100 * GIB, 70 * GIB)
        low = CommitMemory(100 * GIB, 3 * GIB)
        self.assertFalse(restart_needed(2 * GIB, 14 * GIB, healthy))
        self.assertFalse(restart_needed(6 * GIB, 14 * GIB, low))
        self.assertTrue(restart_needed(8 * GIB, 14 * GIB, low))
        self.assertTrue(restart_needed(110 * GIB, 14 * GIB, healthy))
        self.assertFalse(restart_needed(None, 14 * GIB, low))

    def test_configured_guest_ram_allows_host_overhead(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configs = root / "vms/config"
            configs.mkdir(parents=True)
            (configs / "leidian0.config").write_text(json.dumps({"advancedSettings.memorySize": 6144}))
            self.assertEqual(instance_memory_limit(root / "ldconsole.exe", 0), 14 * GIB)
            self.assertEqual(instance_memory_limit(root / "ldconsole.exe", 5), 8 * GIB)

    @patch("buzzbot.memory_guard.psutil.Process")
    def test_pid_must_still_belong_to_same_vm(self, process):
        process.return_value.name.return_value = "Ld9BoxHeadless.exe"
        process.return_value.cmdline.return_value = ["exe", "--comment", "leidian0"]
        process.return_value.memory_info.return_value = SimpleNamespace(private=110 * GIB)
        self.assertEqual(instance_private_memory(vm()), 110 * GIB)
        self.assertIsNone(instance_private_memory(vm(1)))
        process.return_value.name.return_value = "other.exe"
        self.assertIsNone(instance_private_memory(vm()))

    def bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_serial = "emulator-5554"
        bot._memory_guard_enabled = True
        bot._memory_guard_checked_at = 0
        bot._memory_guard_waiting = False
        bot._memory_guard_restarted_at = None
        bot._ldplayer_instances = Mock(return_value=("ldconsole.exe", [vm()]))
        bot.get_current_account = Mock(return_value={"ldplayer_index": 0})
        bot._recover_runtime_adb_connection = Mock(return_value=True)
        bot._interruptible_sleep = Mock()
        bot.set_status_message = Mock()
        bot.stop_event = threading.Event()
        return bot

    @patch("buzzbot_app.time.monotonic", return_value=1000)
    @patch("buzzbot_app.instance_memory_limit", return_value=14 * GIB)
    @patch("buzzbot_app.instance_private_memory", return_value=110 * GIB)
    @patch("buzzbot_app.system_commit_memory", return_value=CommitMemory(100 * GIB, 50 * GIB))
    def test_restarts_once_and_stops_if_growth_immediately_repeats(self, *_mocks):
        bot = self.bot()
        self.assertTrue(bot._check_runtime_memory())
        bot._recover_runtime_adb_connection.assert_called_once_with(force_restart=True)
        self.assertFalse(bot.stop_event.is_set())
        bot._memory_guard_checked_at = 0
        self.assertTrue(bot._check_runtime_memory())
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(bot._recover_runtime_adb_connection.call_count, 1)

    @patch("buzzbot_app.time.monotonic", return_value=1000)
    @patch("buzzbot_app.instance_memory_limit", return_value=14 * GIB)
    @patch("buzzbot_app.instance_private_memory", return_value=2 * GIB)
    @patch("buzzbot_app.system_commit_memory", return_value=CommitMemory(100 * GIB, GIB))
    def test_other_memory_pressure_blocks_actions_between_checks_then_resumes(self, commit, *_mocks):
        bot = self.bot()
        bot._memory_guard_instance = (950, "ldconsole.exe", vm())
        self.assertTrue(bot._check_runtime_memory())
        self.assertTrue(bot._check_runtime_memory())
        bot._ldplayer_instances.assert_not_called()
        bot._recover_runtime_adb_connection.assert_not_called()
        bot._memory_guard_checked_at = 0
        commit.return_value = CommitMemory(100 * GIB, 50 * GIB)
        self.assertFalse(bot._check_runtime_memory())
        self.assertFalse(bot.stop_event.is_set())

    def test_recovery_gates_queue_on_current_igg_id_and_keeps_task_pointer(self):
        bot = identity_fixture.LoginIdentityGateTests().make_bot()
        bot.adb_serial = "emulator-5554"
        bot.adb_client = Mock()
        bot._adb_recovery_lock = threading.Lock()
        bot._adb_last_recovery_attempt = -100
        bot.repair_adb_connection = Mock(return_value=True)
        bot._refresh_adb_client = Mock()
        bot.stop_hotkey_pressed = False
        self.assertTrue(bot._recover_runtime_adb_connection(force_restart=True))
        bot.repair_adb_connection.assert_called_once_with(instance_index=0, force_restart=True)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.routine_only_task_id, "__account_switch__")
        self.assertEqual(bot.account_switch_task["settings"]["_expected_igg_id"], "1234567890")
        self.assertTrue(bot.account_switch_task["settings"]["_verify_only"])

    def test_recovery_with_rotation_off_resumes_without_identity_check(self):
        bot = identity_fixture.LoginIdentityGateTests().make_bot(rotation=False)
        bot.adb_serial = "emulator-5554"
        bot.adb_client = Mock()
        bot._adb_recovery_lock = threading.Lock()
        bot._adb_last_recovery_attempt = -100
        bot.repair_adb_connection = Mock(return_value=True)
        bot._refresh_adb_client = Mock()
        bot.stop_hotkey_pressed = False
        bot.blocked_coords = {}
        bot.routine_only_task_id = "zombie_hunt"
        bot._prepare_current_account_verification = Mock(side_effect=AssertionError("rotation is off"))
        self.assertTrue(bot._recover_runtime_adb_connection(force_restart=True))
        bot.repair_adb_connection.assert_called_once_with(instance_index=0, force_restart=True)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.routine_only_task_id, "zombie_hunt")
        self.assertFalse(bot.stop_event.is_set())

    @patch("buzzbot_app.time.monotonic", return_value=1000)
    @patch("buzzbot_app.instance_private_memory", return_value=2 * GIB)
    @patch("buzzbot_app.system_commit_memory", return_value=CommitMemory(100 * GIB, 70 * GIB))
    def test_changed_profile_invalidates_old_vm_cache(self, _commit, private, _clock):
        bot = self.bot()
        bot._memory_guard_instance = (995, "ldconsole.exe", vm(1))
        self.assertFalse(bot._check_runtime_memory())
        bot._ldplayer_instances.assert_called_once()
        self.assertEqual(private.call_args.args[0].index, 0)

    def test_memory_recovery_keeps_in_progress_target(self):
        bot, task = transition_fixture.AccountTransitionRecoveryTests().bot()
        bot.adb_serial = "emulator-5556"
        bot._adb_recovery_lock = threading.Lock()
        bot._adb_last_recovery_attempt = -100
        bot.get_current_account = Mock(return_value={"ldplayer_index": 1})
        bot.repair_adb_connection = Mock(return_value=True)
        bot._refresh_adb_client = Mock()
        self.assertTrue(bot._recover_runtime_adb_connection(force_restart=True))
        self.assertEqual(task["settings"]["target_account_id"], "target")
        self.assertEqual(bot.current_account_id, "source")
        self.assertFalse(bot.account_switch_confirmed)

    def test_manual_stop_during_restart_never_launches_game(self):
        bot, _task = transition_fixture.AccountTransitionRecoveryTests().bot()
        bot.adb_serial = "emulator-5556"
        bot._adb_recovery_lock = threading.Lock()
        bot._adb_last_recovery_attempt = -100
        bot.get_current_account = Mock(return_value={"ldplayer_index": 1})
        bot.repair_adb_connection = Mock(side_effect=lambda **kw: (bot.stop_event.set() or True))
        self.assertFalse(bot._recover_runtime_adb_connection(force_restart=True))
        bot.adb_client.launch_package.assert_not_called()


class EmulatorBindingTests(unittest.TestCase):
    @patch("buzzbot_app.time.sleep")
    @patch("buzzbot_app.reboot_instance")
    @patch("buzzbot_app.enable_adb_debug")
    @patch("buzzbot_app.AdbClient")
    def test_force_restart_waits_for_new_vm_even_when_old_adb_responds(self, client, _debug, reboot, sleep):
        bot = AutoClicker.__new__(AutoClicker)
        old = vm(1)
        fresh = LDPlayerInstance(1, "test", True, 300, 400, 1280, 720, 240)
        bot.get_adb_repair_target = Mock(return_value=old)
        bot._ldplayer_instances = Mock(side_effect=[("console", [old]), ("console", [old]), ("console", [fresh])])
        bot._auto_detect_adb_connection = Mock(side_effect=AssertionError("must restart despite healthy ADB"))
        bot.adb_path = "adb.exe"
        bot.adb_serial = "emulator-5556"
        bot.is_running = True
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.set_status_message = Mock()
        bot.tr = Mock(return_value="status")
        bot._adopt_adb_serial = Mock()
        client.return_value.is_responsive.return_value = True
        self.assertTrue(bot.repair_adb_connection(1, force_restart=True))
        reboot.assert_called_once_with("console", 1)
        sleep.assert_called_once_with(2.0)
        client.return_value.is_responsive.assert_called_once()
        bot._adopt_adb_serial.assert_called_once_with("emulator-5556", 1)

    def test_stopped_configured_instance_is_selected_instead_of_only_running_other(self):
        bot = AutoClicker.__new__(AutoClicker)
        stopped, other = vm(1, False), vm(0)
        bot.get_current_account = Mock(return_value={"ldplayer_index": 1})
        bot.adb_serial = "emulator-5556"
        bot._ldplayer_instances = Mock(return_value=("ldconsole.exe", [other, stopped]))
        self.assertIs(bot.get_adb_repair_target(), stopped)
        bot._ldplayer_instances.return_value = ("ldconsole.exe", [other])
        self.assertIsNone(bot.get_adb_repair_target())

    @patch("buzzbot_app.bridged_adb_serial_for_index", return_value=None)
    @patch("buzzbot_app.AdbClient")
    def test_stopped_configured_instance_cannot_rebind_through_tcp_probe(self, client, _bridged):
        client.return_value.list_devices.return_value = ["emulator-5554", "127.0.0.1:5555"]
        bot = AutoClicker.__new__(AutoClicker)
        bot.get_current_account = Mock(return_value={"ldplayer_index": 1})
        bot.adb_serial = "emulator-5556"
        bot.adb_path = "adb.exe"
        bot._ldplayer_instances = Mock(return_value=("ldconsole.exe", [vm(0), vm(1, False)]))
        bot._adopt_adb_serial = Mock()
        self.assertFalse(bot._auto_detect_adb_connection())
        bot._adopt_adb_serial.assert_not_called()
        client.return_value.connect.assert_called_once_with("127.0.0.1:5557")
