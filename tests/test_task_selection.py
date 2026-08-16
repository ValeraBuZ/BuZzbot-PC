import unittest

from buzzbot_app import AutoClicker


class TaskSelectionTests(unittest.TestCase):
    def test_clear_routine_selection_disables_every_task_and_group(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "vip_rewards", "group": "Награды VIP", "enabled": True},
            {
                "id": "research",
                "group": "Исследования",
                "enabled": True,
                "settings": {"branch": "economy"},
            },
            {"id": "oil", "group": "Нефть", "enabled": False},
        ]
        bot.groups = {
            "Награды VIP": True,
            "Исследования": True,
            "Нефть": False,
        }
        bot.root = None
        save_calls = []
        bot.save_config = lambda: save_calls.append(True)

        changed = bot.clear_routine_selection()

        self.assertEqual(changed, 2)
        self.assertTrue(all(not task["enabled"] for task in bot.routine_tasks))
        self.assertTrue(all(not enabled for enabled in bot.groups.values()))
        self.assertEqual(save_calls, [True])


if __name__ == "__main__":
    unittest.main()
