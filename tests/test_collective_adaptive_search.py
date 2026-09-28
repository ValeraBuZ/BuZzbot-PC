import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import tests.test_zombie_search as zombie_fixture
from buzzbot_app import AutoClicker
from buzzbot.matching import collective_target_card_is_visible, collective_search_not_found_is_visible


class CollectiveAdaptiveSearchTests(unittest.TestCase):
    def make_bot(self, level=7):
        bot = zombie_fixture.ZombieSearchTests().make_bot()
        bot._current_task_settings = lambda: {"level": level}
        bot._confirm_collective_search_result = Mock(return_value=True)
        return bot

    @staticmethod
    def image():
        return dict(zombie_fixture.ZombieSearchTests.search_image(), action="hivemind_search")

    def test_lowers_until_found_and_next_dispatch_raises_only_one_level(self):
        bot = self.make_bot()
        visible = iter([True, True, True, False])
        bot._locate_image = lambda _image: ((SimpleNamespace(x=640, y=620), None, 0.9)
                                          if next(visible) else (None, None, 0.0))
        point = SimpleNamespace(x=640, y=620)
        self.assertTrue(bot._execute_action(self.image(), point))
        context, key = bot._hunt_context("collective_mind")
        self.assertEqual(bot.hunt_found_levels[key], 4)
        self.assertNotIn(key, bot.hunt_search_levels)  # Finding is not dispatching.
        self.assertEqual(bot.adb_client.taps.count((494, 544)), 3)
        bot._remember_hunt_dispatch({"id": "collective_mind", "settings": {"level": 7}})
        self.assertEqual(bot.hunt_search_levels[key], 5)
        bot.adb_client.taps.clear()
        bot._locate_image = lambda _image: (None, None, 0.0)
        self.assertTrue(bot._execute_action(self.image(), point))
        self.assertEqual(bot.adb_client.taps[:9], [(784, 544)] * 7 + [(494, 544)] * 2)
        self.assertEqual(bot.hunt_found_levels[key], 5)

    def test_stays_at_configured_ceiling_after_success(self):
        for ceiling in (6, 7):
            with self.subTest(ceiling=ceiling):
                bot = self.make_bot(ceiling)
                bot._locate_image = lambda _image: (None, None, 0.0)
                self.assertTrue(bot._execute_action(self.image(), SimpleNamespace(x=640, y=620)))
                bot._remember_hunt_dispatch({"id": "collective_mind", "settings": {"level": ceiling}})
                _context, key = bot._hunt_context("collective_mind")
                self.assertEqual(bot.hunt_search_levels[key], ceiling)

    def test_no_targets_searches_through_level_one_then_defers_without_rally(self):
        bot = self.make_bot()
        bot._locate_image = lambda _image: (SimpleNamespace(x=640, y=620), None, 0.9)
        self.assertFalse(bot._execute_action(self.image(), SimpleNamespace(x=640, y=620)))
        self.assertEqual(bot.adb_client.taps.count((640, 620)), 7)
        self.assertEqual(bot.adb_client.taps.count((494, 544)), 6)
        self.assertEqual(bot.adb_client.taps.count((784, 544)), 7)
        self.assertNotIn((640, 353), bot.adb_client.taps)
        self.assertEqual(len(bot.deferred_unavailable), 1)
        self.assertEqual(bot.deferred_unavailable[0][1], 60)
        self.assertEqual(bot.hunt_found_levels, {})

    def test_closed_search_toast_and_own_shelter_are_not_a_collective_target(self):
        assets = Path(__file__).parent/'assets/collective'
        for name, target, absent in [('target_card.jpg',True,False),
                                     ('not_found_closed.png',False,True),
                                     ('own_shelter_card.png',False,False)]:
            frame = cv2.imread(str(assets/name))
            for scale in (1,.75):
                resized = cv2.resize(frame,None,fx=scale,fy=scale)
                self.assertEqual(collective_target_card_is_visible(resized),target,name)
                self.assertEqual(collective_search_not_found_is_visible(resized),absent,name)

    def test_no_target_toast_never_clicks_the_map_center(self):
        bot = self.make_bot()
        frame = cv2.imread(str(Path(__file__).parent/'assets/collective/not_found_closed.png'))
        bot._capture_screen_bgr = lambda **kw:(frame,(0,0))
        self.assertFalse(AutoClicker._confirm_collective_search_result(bot,bot.get_display_profile()))
        self.assertEqual(bot.adb_client.taps,[])

    def test_wrong_card_never_completes_search(self):
        bot=self.make_bot()
        frame=cv2.imread(str(Path(__file__).parent/'assets/collective/own_shelter_card.png'))
        bot._capture_screen_bgr=lambda **kw:(frame,(0,0))
        bot._world_map_visible_in_frame=lambda frame:True
        bot._save_routine_calibration_frame=Mock()
        self.assertFalse(AutoClicker._confirm_collective_search_result(bot,bot.get_display_profile()))
        self.assertEqual(bot.adb_client.taps,[(640,353)])

    def test_closed_empty_search_reopens_before_lowering_and_only_remembers_confirmed_target(self):
        bot=self.make_bot()
        bot._locate_image=lambda image:(None,None,0)
        bot._confirm_collective_search_result=Mock(side_effect=[False,True])
        bot._reopen_collective_search=Mock(return_value=(383,467))
        self.assertTrue(bot._execute_action(self.image(),SimpleNamespace(x=640,y=620)))
        bot._reopen_collective_search.assert_called_once()
        _,key=bot._hunt_context('collective_mind')
        self.assertEqual(bot.hunt_found_levels[key],6)
        self.assertEqual(bot.adb_client.taps[-9:],[(527,391)]*7+[(237,391),(383,467)])

    def test_failed_reopening_does_not_click_stale_slider_and_preserves_lower_retry(self):
        bot=self.make_bot()
        bot._locate_image=lambda image:(None,None,0)
        bot._confirm_collective_search_result=Mock(return_value=False)
        bot._reopen_collective_search=Mock(return_value=None)
        self.assertFalse(bot._execute_action(self.image(),SimpleNamespace(x=640,y=620)))
        self.assertEqual(bot.adb_client.taps,[(784,544)]*7+[(640,620)])
        self.assertEqual(bot.hunt_found_levels,{})
        _,key=bot._hunt_context('collective_mind')
        self.assertEqual(bot.hunt_search_levels[key],6)

    def test_stopped_search_never_clicks_target_or_marks_a_level_found(self):
        bot = self.make_bot()
        bot._locate_image = Mock(side_effect=AssertionError("search stopped"))
        bot._interruptible_sleep = lambda seconds: bot.stop_event.set()
        self.assertFalse(bot._execute_action(self.image(), SimpleNamespace(x=640, y=620)))
        self.assertEqual(len(bot.adb_client.taps), 1)
        self.assertEqual(bot.hunt_found_levels, {})

    def test_levels_are_isolated_between_accounts_and_hunt_types(self):
        bot = self.make_bot()
        _, first = bot._hunt_context("collective_mind")
        bot.hunt_found_levels = {first: 3}
        bot._remember_hunt_dispatch({"id": "collective_mind", "settings": {"level": 7}})
        _, zombie = bot._hunt_context("zombie_hunt")
        bot.current_account_id = "account-b"
        _, other = bot._hunt_context("collective_mind")
        self.assertEqual(bot.hunt_search_levels, {first: 4})
        self.assertNotEqual(first, zombie)
        self.assertNotEqual(first, other)

    def test_collective_stamina_popup_is_not_a_successful_march(self):
        bot = self.make_bot()
        bot.cycle_mode = False
        bot.current_routine_task_id = "collective_mind"
        bot._current_task_settings = lambda: {"use_stamina_items": False}
        frame = cv2.imread(str(Path(__file__).parent / "assets/collective/stamina.png"))
        bot._capture_screen_bgr = lambda **kwargs: (frame, (0, 0))
        bot._world_map_visible_in_frame = lambda _frame: False
        bot._locate_image = Mock(return_value=(None, None, 0.0))
        image = dict(self.image(), action="click", confirm_disappears=True,
                     description="Rally march", click_sequence=[])
        self.assertFalse(bot._execute_action(image, SimpleNamespace(x=950, y=643)))
        self.assertEqual(bot.routine_action_failure_reason, "stamina")
        bot._locate_image.assert_not_called()

    def test_collective_waits_for_popup_then_refills_and_dispatches(self):
        bot = self.make_bot()
        bot.cycle_mode = False
        bot.current_routine_task_id = "collective_mind"
        assets = Path(__file__).parent / "assets"
        toast = cv2.imread(str(assets / "collective/stamina_toast.png"))
        stamina = cv2.imread(str(assets / "collective/stamina.png"))
        world = cv2.imread(str(assets / "zombie/march_dispatched.jpg"))
        captures = iter([stamina * 0, toast, stamina, world])
        bot._capture_screen_bgr = lambda **kwargs: (next(captures), (0, 0))
        bot._world_map_visible_in_frame = lambda frame: frame is world
        bot._locate_image = Mock(side_effect=[
            (SimpleNamespace(x=950, y=643), (839, 620, 223, 47), 0.99),
            (None, None, 0.0),
        ])
        image = dict(self.image(), action="click", confirm_disappears=True,
                     description="Rally march", click_sequence=[])
        self.assertTrue(bot._execute_action(image, SimpleNamespace(x=950, y=643)))
        self.assertEqual(len(bot.adb_client.taps), 4)  # March, refill, close, March again.
        self.assertEqual(bot.adb_client.taps[0], (950, 643))
        self.assertEqual(bot.adb_client.taps[-1], (950, 643))

    def test_disappeared_march_button_without_map_is_not_success(self):
        bot = self.make_bot()
        bot.cycle_mode = False
        bot.current_routine_task_id = "collective_mind"
        frame = cv2.imread(str(Path(__file__).parent / "assets/zombie/shop_false_positive.jpg"))
        bot._capture_screen_bgr = lambda **kwargs: (frame, (0, 0))
        bot._world_map_visible_in_frame = lambda _frame: False
        bot._locate_image = Mock(return_value=(None, None, 0.0))
        image = dict(self.image(), action="click", confirm_disappears=True,
                     description="Rally march", click_sequence=[])
        with patch("buzzbot_app.time.monotonic", side_effect=[0, 0, 7]):
            self.assertFalse(bot._execute_action(image, SimpleNamespace(x=950, y=643)))
