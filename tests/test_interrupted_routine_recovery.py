import threading
import unittest
from unittest.mock import Mock

from buzzbot_app import AutoClicker, GAME_PACKAGE


class InterruptedRoutineRecoveryTests(unittest.TestCase):
    def make_bot(self, package="com.android.vending"):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.adb_client.current_foreground_package.return_value = package
        bot.routine_tasks = [
            {"id": "game_login", "enabled": False, "settings": {"_completed_login": True}},
            {"id": "vip_rewards", "enabled": True},
            {"id": "mysterious_merchant", "enabled": True},
            {"id": "trucks", "enabled": True},
        ]
        bot.current_routine_index = 2
        bot.current_routine_task_id = "mysterious_merchant"
        bot.get_routine_task = lambda task_id: next((t for t in bot.routine_tasks if t["id"] == task_id), None)
        bot.routine_only_task_id = None
        bot.routine_mode = True
        bot.routine_next_run = {"mysterious_merchant": 10.0}
        bot.routine_completed_steps = {"merchant_shop_open_requested"}
        bot.blocked_coords = {(10, 20): 30.0}
        bot.stop_event = threading.Event()
        bot.save_config = Mock()
        bot.set_status_message = Mock()
        bot._advance_routine_after_outcome = Mock()
        bot._return_to_main_screen = Mock()
        return bot

    def test_external_store_does_not_defer_or_skip_interrupted_merchant(self):
        bot = self.make_bot()
        bot._defer_current_routine_unavailable("unverified shop", 100.0, retry_delay=3600)
        self.assertEqual(bot.routine_next_run["mysterious_merchant"], 10.0)
        self.assertEqual(bot.routine_forced_task_return_index, 2)
        self.assertEqual(bot.routine_forced_task_active_id, "game_login")
        self.assertEqual(bot.current_routine_index, 0)
        self.assertTrue(bot.routine_tasks[0]["enabled"])
        self.assertIsNone(bot.current_routine_task_id)
        bot._advance_routine_after_outcome.assert_not_called()
        bot._return_to_main_screen.assert_not_called()

    def test_lost_foreground_is_not_a_successful_completion(self):
        bot = self.make_bot()
        bot._finish_current_routine(100.0)
        self.assertEqual(bot.routine_forced_task_return_index, 2)
        bot._advance_routine_after_outcome.assert_not_called()

    def test_lost_foreground_is_not_a_no_action_timeout(self):
        bot = self.make_bot()
        bot._defer_current_routine_no_action(100.0)
        self.assertEqual(bot.routine_forced_task_return_index, 2)
        self.assertEqual(bot.routine_next_run["mysterious_merchant"], 10.0)
        bot._advance_routine_after_outcome.assert_not_called()

    def test_sdk_account_selection_is_not_interrupted(self):
        bot = self.make_bot()
        self.assertFalse(bot._recover_interrupted_routine_foreground({"id": "__account_switch__"}))
        bot.adb_client.current_foreground_package.assert_not_called()

    def test_game_foreground_preserves_active_task(self):
        bot = self.make_bot(GAME_PACKAGE)
        self.assertFalse(bot._recover_interrupted_routine_foreground(bot.routine_tasks[2]))
        self.assertEqual(bot.current_routine_index, 2)
        bot.save_config.assert_not_called()

    def test_one_shot_scope_is_carried_into_login_recovery(self):
        bot = self.make_bot()
        bot.routine_only_task_id = "mysterious_merchant"
        self.assertTrue(bot._recover_interrupted_routine_foreground(bot.routine_tasks[2]))
        self.assertEqual(bot.routine_tasks[0]["settings"]["_foreground_resume_only_task_id"], "mysterious_merchant")
        self.assertIsNone(bot.routine_only_task_id)
        self.assertFalse(bot.stop_event.is_set())

    def test_missing_recovery_task_stops_without_advancing(self):
        bot = self.make_bot()
        bot.routine_tasks.pop(0)
        self.assertTrue(bot._recover_interrupted_routine_foreground(bot.get_routine_task("mysterious_merchant")))
        self.assertTrue(bot.stop_event.is_set())
        bot._advance_routine_after_outcome.assert_not_called()

    def test_temporary_login_preserves_pending_forced_followup_context(self):
        bot = self.make_bot()
        bot.routine_forced_task_queue = ["mysterious_merchant", "trucks"]
        bot.routine_forced_task_active_id = "mysterious_merchant"
        bot.routine_forced_task_return_index = 9
        bot._recover_interrupted_routine_foreground(bot.routine_tasks[2])
        self.assertEqual(bot.routine_tasks[0]["settings"]["_foreground_return_forced_context"], {
            "queue": ["mysterious_merchant", "trucks"],
            "active_id": "mysterious_merchant", "return_index": 9,
        })


if __name__ == "__main__":
    unittest.main()
