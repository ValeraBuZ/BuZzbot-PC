import unittest

from buzzbot_app import AutoClicker


class QueueOrderRegressionTests(unittest.TestCase):
    def make_bot(self, tasks, index, *, active_marches=0):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = tasks
        bot.current_routine_index = index
        bot.current_routine_task_id = None
        bot.account_rotation_enabled = True
        bot.routine_only_task_id = None
        bot.routine_pass_completed = False
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_radar_return_hold = False
        bot.routine_deployment_blocked_until = 0.0
        bot.routine_max_marches = 5
        bot.routine_next_run = {}
        bot.groups = {}
        bot.lang = "ru"
        bot.input_backend = "desktop"
        bot.search_images = [
            {"group": task["id"], "enabled": True}
            for task in tasks
            if task["id"] != "mysterious_merchant"
        ]
        bot.get_active_marches = lambda _now: active_marches
        bot._release_radar_return_hold = lambda *_args: False
        bot._try_return_camped_zombie_march = lambda *_args: False
        bot.get_routine_templates = lambda *_args, **_kwargs: []
        bot._clear_routine_coordinate_blocks = lambda _task: None
        bot._is_settlement_screen_visible = lambda: True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.saved_pass_states = []
        bot.save_config = lambda: bot.saved_pass_states.append(
            bot.routine_pass_completed
        )
        return bot

    @staticmethod
    def task(task_id, *, enabled=True, uses_march=False, settings=None):
        return {
            "id": task_id,
            "name": task_id,
            "group": task_id,
            "enabled": enabled,
            "uses_march": uses_march,
            "settings": settings or {},
        }

    def test_full_squads_complete_cooling_march_tail_before_revisiting_vip(self):
        for vip_deadline in (0.0, 86400.0):
            with self.subTest(vip_deadline=vip_deadline):
                bot = self.make_bot(
                    [
                        self.task("vip_rewards"),
                        self.task("food", uses_march=True),
                        self.task("oil", uses_march=True),
                    ],
                    1,
                    active_marches=5,
                )
                bot.routine_next_run = {
                    "vip_rewards": vip_deadline,
                    "food": 3600.0,
                    "oil": 0.0,
                }

                self.assertIsNone(bot._begin_due_routine(100.0))

                self.assertIsNone(bot.current_routine_task_id)
                self.assertTrue(bot.routine_pass_completed)
                self.assertEqual(bot.current_routine_index, 0)
                self.assertTrue(bot._account_rotation_switch_due(101.0))
                self.assertEqual(bot.routine_next_run["food"], 3600.0)
                self.assertEqual(bot.routine_next_run["oil"], 160.0)
                self.assertEqual(bot.routine_next_run["vip_rewards"], vip_deadline)

    def test_full_squads_defer_cooling_march_to_next_saved_non_march_slot(self):
        bot = self.make_bot(
            [
                self.task("vip_rewards"),
                self.task("food", uses_march=True),
                self.task("alliance_help"),
            ],
            1,
            active_marches=5,
        )
        bot.routine_next_run = {"food": 3600.0}

        self.assertIsNone(bot._begin_due_routine(100.0))

        self.assertEqual(bot.current_routine_index, 2)
        self.assertFalse(bot.routine_pass_completed)
        self.assertEqual(bot.routine_next_run["food"], 3600.0)
        self.assertEqual(bot.routine_last_outcome["task_id"], "food")

    def test_absent_merchant_in_final_enabled_slot_completes_pass(self):
        for disabled_tail in (False, True):
            with self.subTest(disabled_tail=disabled_tail):
                tasks = [
                    self.task("vip_rewards"),
                    self.task("mysterious_merchant"),
                ]
                if disabled_tail:
                    tasks.append(self.task("heal", enabled=False))
                bot = self.make_bot(tasks, 1)

                self.assertIsNone(bot._begin_due_routine(100.0))

                self.assertIsNone(bot.current_routine_task_id)
                self.assertEqual(bot.current_routine_index, 0)
                self.assertTrue(bot.routine_pass_completed)
                self.assertTrue(bot._account_rotation_switch_due(101.0))
                self.assertEqual(bot.saved_pass_states, [True])
                self.assertEqual(bot.routine_next_run["mysterious_merchant"], 3700.0)

    def test_active_boost_in_final_enabled_slot_completes_before_scheduler_wraps(self):
        for disabled_tail in (False, True):
            with self.subTest(disabled_tail=disabled_tail):
                tasks = [
                    self.task("vip_rewards"),
                    self.task("gathering_boost", settings={"active_until": 3600.0}),
                ]
                if disabled_tail:
                    tasks.append(self.task("heal", enabled=False))
                bot = self.make_bot(tasks, 1)

                self.assertIsNone(bot._begin_due_routine(100.0))

                self.assertIsNone(bot.current_routine_task_id)
                self.assertEqual(bot.current_routine_index, 0)
                self.assertTrue(bot.routine_pass_completed)
                self.assertTrue(bot._account_rotation_switch_due(101.0))
                self.assertEqual(bot.saved_pass_states, [True])
                self.assertEqual(bot.routine_next_run["gathering_boost"], 3600.0)


if __name__ == "__main__":
    unittest.main()
