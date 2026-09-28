import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buzzbot.routines import upgrade_mysterious_merchant_metadata
from buzzbot_app import AutoClicker, SYSTEM_TEMPLATE_GROUP


class _EndIteration(BaseException):
    """End this headless worker fixture before executing any real action."""


class MerchantTemplateRoutingTests(unittest.TestCase):
    def make_bot(self, visual_fallback, *, system_overlay=False):
        bot = AutoClicker.__new__(AutoClicker)
        task = {
            "id": "mysterious_merchant", "group": "merchant", "enabled": True,
            "settings": {"visual_fallback": visual_fallback, "avoid_gems": True},
            "completion_runtime_step": "merchant_complete",
        }
        bot.routine_tasks = [task]
        bot.current_routine_task_id = task["id"]
        bot.routine_mode = True
        bot.routine_last_action_time = 100.0
        bot.routine_current_had_action = False
        bot.routine_completed_steps = {"open_supply_station"}
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.is_paused = False
        bot.anti_loop_enabled = False
        bot.sleep_error = 0.0
        bot.input_backend = "pyautogui"
        bot.groups = {"merchant": True, SYSTEM_TEMPLATE_GROUP: True}
        bot.group_execution = {}
        bot.cycle_mode = False
        bot.cycle_groups = []
        bot.search_images = [
            {
                "uid": "legacy-purchase", "path": "unused-purchase.png",
                "description": "Legacy merchant purchase", "group": "merchant",
                "enabled": True, "action": "click", "merchant_currency": "resources",
                "runtime_step": "merchant_purchase", "requires_runtime_steps": ["open_supply_station"],
            },
            {
                "uid": "legacy-finish", "path": "unused-finish.png",
                "description": "Legacy merchant finish", "group": "merchant",
                "enabled": True, "action": "click", "runtime_step": "merchant_complete",
                "requires_runtime_steps": ["open_supply_station"], "completes_routine": True,
            },
        ]
        if system_overlay:
            bot.search_images.append({
                "uid": "system-overlay", "path": "unused-overlay.png",
                "description": "System overlay close", "group": SYSTEM_TEMPLATE_GROUP,
                "enabled": True, "action": "click",
                "only_routine_ids": ["mysterious_merchant"],
            })
        bot.set_status_message = Mock()
        bot._research_watchdog_due = Mock(return_value=False)
        bot._drain_expired_account_pass = Mock(return_value=False)
        # A regression must fail promptly, including when the worker catches
        # an unexpected exception; it must never leave a live retrying loop.
        bot._begin_due_routine = Mock(side_effect=[task, _EndIteration()])
        bot._recover_interrupted_routine_foreground = Mock(return_value=False)
        bot._try_global_login_connection_recovery = Mock(return_value=False)
        bot._pause_for_manual_account_verification = Mock(return_value=False)
        bot._try_mysterious_merchant_visual_fallback = Mock(return_value=False)
        bot._try_alliance_gifts_visual_fallback = Mock(return_value=False)
        bot._missing_template_uses_visual_fallback = Mock(return_value=False)
        bot._routine_idle_completion_ready = Mock(return_value=False)
        bot._defer_current_routine_no_action = Mock(side_effect=lambda _now: bot.stop_event.set())
        bot._finish_current_routine = Mock(side_effect=_EndIteration)
        bot._locate_image = Mock(return_value=(SimpleNamespace(x=20, y=20), (10, 10, 20, 20), 1.0))
        bot._validate_detected_match = Mock(return_value=(True, None))
        bot._execute_action = Mock(side_effect=_EndIteration)
        return bot, task

    def run_one_iteration(self, bot):
        with patch("buzzbot_app.time.time", return_value=100.0), patch("buzzbot_app.time.sleep"), patch(
            "buzzbot_app.logger.exception"
        ) as unexpected_error:
            try:
                bot._run_clicker_loop()
            except _EndIteration:
                pass
        unexpected_error.assert_not_called()
        self.assertEqual(bot._begin_due_routine.call_count, 1)

    def test_loaded_legacy_purchase_and_finish_never_bypass_visual_price_check(self):
        for flag in (False, True):
            with self.subTest(visual_fallback=flag):
                bot, task = self.make_bot(flag)
                self.assertEqual(len(bot.get_routine_templates(task, active_only=True)), 2)
                self.run_one_iteration(bot)
                bot._try_mysterious_merchant_visual_fallback.assert_called_once_with(task)
                bot._locate_image.assert_not_called()
                bot._execute_action.assert_not_called()
                bot._finish_current_routine.assert_not_called()
                self.assertNotIn("merchant_complete", bot.routine_completed_steps)

    def test_system_overlay_remains_available_when_visual_merchant_has_no_action(self):
        for flag in (False, True):
            with self.subTest(visual_fallback=flag):
                bot, task = self.make_bot(flag, system_overlay=True)
                self.run_one_iteration(bot)
                bot._try_mysterious_merchant_visual_fallback.assert_called_once_with(task)
                self.assertEqual(bot._execute_action.call_count, 1)
                self.assertEqual(bot._execute_action.call_args.args[0]["uid"], "system-overlay")
                self.assertEqual([call.args[0]["uid"] for call in bot._locate_image.call_args_list], ["system-overlay"])
                bot._finish_current_routine.assert_not_called()

    def test_legacy_disabled_visual_flag_is_upgraded_to_required_price_verification(self):
        for flag in (False, True):
            with self.subTest(visual_fallback=flag):
                bot, task = self.make_bot(flag)
                upgrade_mysterious_merchant_metadata(bot.search_images, [task])
                self.assertTrue(task["settings"]["visual_fallback"])
                self.assertTrue(task["settings"]["avoid_gems"])
                self.assertEqual(task["completion_runtime_step"], "merchant_complete")


if __name__ == "__main__":
    unittest.main()
