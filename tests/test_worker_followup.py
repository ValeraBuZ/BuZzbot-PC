import subprocess
import unittest
from unittest.mock import Mock, call, patch

from buzzbot_app import AutoClicker


def timeout():
    return subprocess.TimeoutExpired("test-worker", 2)


class WorkerFollowupTests(unittest.TestCase):
    def setUp(self):
        logger_patch = patch("buzzbot_app.logger")
        logger_patch.start()
        self.addCleanup(logger_patch.stop)

    def bot(self, processes):
        bot = AutoClicker.__new__(AutoClicker)
        bot.multi_emulator_workers = {
            index: {"process": process, "runtime_dir": f"unused-worker-{index}"}
            for index, process in enumerate(processes, 1)
        }
        bot.multi_emulator_total = 1 + len(processes)
        bot._write_multi_command = Mock()
        bot.set_status_message = Mock()
        return bot

    def stubborn_process(self):
        process = Mock()
        process.wait.side_effect = timeout()
        process.poll.return_value = None
        process.terminate.side_effect = PermissionError("terminate denied")
        process.kill.side_effect = PermissionError("kill denied")
        return process

    def test_failed_worker_stop_keeps_handle_and_stops_other_workers(self):
        stubborn, finished = self.stubborn_process(), Mock()
        finished.wait.return_value = 0
        bot = self.bot([stubborn, finished])
        survivor = bot.multi_emulator_workers[1]

        self.assertFalse(bot._stop_multi_workers())

        self.assertEqual(bot.multi_emulator_workers, {1: survivor})
        self.assertEqual(bot.multi_emulator_total, 2)
        finished.wait.assert_called_once_with(timeout=2.5)
        stubborn.terminate.assert_called_once()
        stubborn.kill.assert_called_once()

    def test_kill_is_followed_by_wait_even_when_terminate_fails(self):
        process = Mock()
        process.wait.side_effect = [timeout(), timeout(), 0]
        process.terminate.side_effect = PermissionError("terminate denied")
        bot = self.bot([process])

        self.assertTrue(bot._stop_multi_workers())

        self.assertEqual(process.mock_calls, [
            call.wait(timeout=2.5), call.terminate(), call.wait(timeout=2.0),
            call.kill(), call.wait(timeout=2.0),
        ])
        self.assertEqual(bot.multi_emulator_workers, {})
        self.assertEqual(bot.multi_emulator_total, 1)

    def test_control_file_failure_does_not_skip_process_cleanup(self):
        process = Mock()
        process.wait.return_value = 0
        bot = self.bot([process])
        bot._write_multi_command.side_effect = OSError("control directory unavailable")

        self.assertTrue(bot._stop_multi_workers())

        process.wait.assert_called_once_with(timeout=2.5)
        self.assertEqual(bot.multi_emulator_workers, {})

    def test_wait_error_does_not_skip_termination_or_remaining_workers(self):
        first, second = Mock(), Mock()
        first.wait.side_effect = [OSError("wait failed"), 0]
        second.wait.return_value = 0
        bot = self.bot([first, second])

        self.assertTrue(bot._stop_multi_workers())

        first.terminate.assert_called_once()
        first.kill.assert_not_called()
        second.wait.assert_called_once_with(timeout=2.5)
        self.assertEqual(bot.multi_emulator_workers, {})

    def test_survivor_can_be_stopped_again_and_only_then_removed(self):
        process = self.stubborn_process()
        bot = self.bot([process])
        self.assertFalse(bot._stop_multi_workers())
        self.assertIn(1, bot.multi_emulator_workers)

        process.wait.side_effect = None
        process.wait.return_value = 0
        self.assertTrue(bot._stop_multi_workers())

        self.assertEqual(bot.multi_emulator_workers, {})
        self.assertEqual(bot.multi_emulator_total, 1)
        self.assertEqual(bot._write_multi_command.call_count, 2)

    def test_new_launch_is_blocked_before_config_changes_if_worker_survives(self):
        bot = self.bot([self.stubborn_process()])
        bot.is_multi_worker = False
        bot.is_running = False
        bot._running_emulator_targets = Mock()
        bot.save_config = Mock()
        bot.start_routines = Mock()

        self.assertFalse(bot._start_all_emulators())

        self.assertIn(1, bot.multi_emulator_workers)
        bot._running_emulator_targets.assert_not_called()
        bot.save_config.assert_not_called()
        bot.start_routines.assert_not_called()
        bot.set_status_message.assert_called_once()

    def test_finished_old_worker_is_cleaned_before_discovering_new_targets(self):
        process = Mock()
        process.wait.return_value = 0
        bot = self.bot([process])
        bot.is_multi_worker = False
        bot.is_running = False
        bot._running_emulator_targets = Mock(return_value=[])
        bot._show_notification = Mock()

        self.assertFalse(bot._start_all_emulators())

        self.assertEqual(bot.multi_emulator_workers, {})
        process.wait.assert_called_once_with(timeout=2.5)
        bot._running_emulator_targets.assert_called_once()

    def test_failed_primary_cleanup_still_stops_background_workers(self):
        bot = self.bot([])
        bot._start_all_emulators = Mock(side_effect=OSError("spawn failed"))
        bot.stop = Mock(side_effect=RuntimeError("primary cleanup failed"))
        bot._stop_multi_workers = Mock()

        self.assertFalse(bot.start_all_emulators())

        bot.stop.assert_called_once()
        bot._stop_multi_workers.assert_called_once()
        bot.set_status_message.assert_called_once()

    def test_unknown_exit_state_keeps_worker_visible(self):
        process = self.stubborn_process()
        process.poll.side_effect = OSError("process state unavailable")
        bot = self.bot([process])

        self.assertFalse(bot._stop_multi_workers())

        self.assertIn(1, bot.multi_emulator_workers)
        self.assertEqual(bot.multi_emulator_total, 2)


if __name__ == "__main__":
    unittest.main()
