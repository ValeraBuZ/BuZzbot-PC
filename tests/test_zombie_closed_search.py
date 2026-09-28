import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2

from buzzbot.matching import zombie_search_not_found_is_visible, zombie_target_card_is_visible
from buzzbot_app import AutoClicker
import tests.test_zombie_search as fixture

ASSETS = Path(__file__).parent / 'assets'


class ZombieClosedSearchTests(unittest.TestCase):
    def test_real_toast_and_target_card_at_both_resolutions(self):
        for name, missing, found in (
            ('zombie/not_found_closed.png',True,False),
            ('zombie/left_card.jpg',False,True),
            ('zombie/march_dispatched.jpg',False,False),
            ('zombie/shop_false_positive.jpg',False,False),
            ('collective/not_found_closed.png',False,False),
            ('collective/own_shelter_card.png',False,False),
        ):
            frame=cv2.imread(str(ASSETS/name))
            for scale in (1,.75):
                with self.subTest(name=name,scale=scale):
                    resized=cv2.resize(frame,None,fx=scale,fy=scale)
                    self.assertEqual(zombie_search_not_found_is_visible(resized),missing)
                    self.assertEqual(zombie_target_card_is_visible(resized),found)
        frame=cv2.imread(str(ASSETS/'zombie/left_card.jpg'))
        for region in ((slice(180,211),slice(235,320)),(slice(538,588),slice(220,420))):
            partial=frame.copy();partial[region]=0
            self.assertFalse(zombie_target_card_is_visible(partial))

    def test_absent_target_toast_never_clicks_the_map(self):
        bot=fixture.ZombieSearchTests().make_bot()
        frame=cv2.imread(str(ASSETS/'zombie/not_found_closed.png'))
        bot._capture_screen_bgr=Mock(return_value=(frame,(0,0)))
        self.assertFalse(AutoClicker._confirm_zombie_search_result(bot,bot.get_display_profile()))
        self.assertEqual(bot.adb_client.taps,[])

    def test_target_confirmation_checks_the_card_after_opening_it(self):
        for backend in ('adb','screen'):
            bot=fixture.ZombieSearchTests().make_bot()
            bot.input_backend=backend
            bot._screen_game_region=lambda:(84,108,1280,720)
            world=cv2.imread(str(ASSETS/'zombie/march_dispatched.jpg'))
            card=cv2.imread(str(ASSETS/'zombie/left_card.jpg'))
            bot._capture_screen_bgr=Mock(side_effect=[(world,(0,0)),(card,(0,0))])
            bot._world_map_visible_in_frame=Mock(return_value=True)
            with patch('buzzbot_app.pyautogui.click') as click:
                self.assertTrue(AutoClicker._confirm_zombie_search_result(bot,bot.get_display_profile()))
                if backend=='adb':
                    self.assertEqual(bot.adb_client.taps,[(640,353)])
                else:
                    click.assert_called_once_with(724,461)

    def test_own_shelter_is_not_a_successful_zombie_search(self):
        bot=fixture.ZombieSearchTests().make_bot()
        frame=cv2.imread(str(ASSETS/'collective/own_shelter_card.png'))
        bot._capture_screen_bgr=Mock(return_value=(frame,(0,0)))
        bot._world_map_visible_in_frame=Mock(return_value=True)
        bot._save_routine_calibration_frame=Mock()
        self.assertFalse(AutoClicker._confirm_zombie_search_result(bot,bot.get_display_profile()))

    def test_closed_search_reopens_before_lowering_using_fresh_button_position(self):
        bot=fixture.ZombieSearchTests().make_bot()
        bot._locate_image=Mock(return_value=(None,None,0))
        bot._confirm_zombie_search_result=Mock(side_effect=[False,True])
        bot._reopen_hunt_search=Mock(return_value=(218,467))
        self.assertTrue(bot._execute_action(fixture.ZombieSearchTests.search_image(),SimpleNamespace(x=640,y=620)))
        self.assertEqual(bot.adb_client.taps,[(640,620),(72,391),(218,467)])
        context,key=bot._hunt_context('zombie_hunt')
        self.assertEqual(bot.zombie_level_restore[context],1)
        self.assertEqual(bot.hunt_found_levels[key],1)
        bot._remember_hunt_dispatch({'id':'zombie_hunt'})
        self.assertEqual(bot.hunt_search_levels[key],0)

    def test_final_closed_search_defers_restoration_until_next_open_panel(self):
        bot=fixture.ZombieSearchTests().make_bot(fallback_levels=1)
        bot._locate_image=Mock(return_value=(None,None,0))
        bot._confirm_zombie_search_result=Mock(return_value=False)
        bot._reopen_hunt_search=Mock(return_value=(218,467))
        image=fixture.ZombieSearchTests.search_image()
        self.assertFalse(bot._execute_action(image,SimpleNamespace(x=640,y=620)))
        self.assertEqual(bot.adb_client.taps,[(640,620),(72,391),(218,467)])
        self.assertEqual(bot.hunt_found_levels,{})
        context,key=bot._hunt_context('zombie_hunt')
        self.assertEqual(bot.zombie_level_restore[context],1)
        bot.adb_client.taps.clear()
        bot._confirm_zombie_search_result=Mock(return_value=True)
        self.assertTrue(bot._execute_action(image,SimpleNamespace(x=218,y=467)))
        self.assertEqual(bot.adb_client.taps,[(362,391),(218,467)])
        self.assertEqual(bot.zombie_level_restore[context],0)

    def test_failed_reopening_keeps_offset_and_never_clicks_stale_controls(self):
        bot=fixture.ZombieSearchTests().make_bot()
        bot._locate_image=Mock(return_value=(None,None,0))
        bot._confirm_zombie_search_result=Mock(return_value=False)
        bot._reopen_hunt_search=Mock(return_value=None)
        self.assertFalse(bot._execute_action(fixture.ZombieSearchTests.search_image(),SimpleNamespace(x=640,y=620)))
        self.assertEqual(bot.adb_client.taps,[(640,620)])
        self.assertEqual(bot.hunt_found_levels,{})
        context,key=bot._hunt_context('zombie_hunt')
        self.assertEqual(bot.hunt_search_levels[key],1)
        self.assertEqual(bot.zombie_level_restore[context],0)

    def test_reopen_selects_zombie_tab_before_finding_search_again(self):
        bot=fixture.ZombieSearchTests().make_bot()
        bot._prepare_world_search_screen=Mock(return_value=True)
        icon={'runtime_step':'zombie_icon','group':'Zombies'}
        image=dict(fixture.ZombieSearchTests.search_image(),group='Zombies')
        bot.search_images=[icon,image]
        bot._locate_image=Mock(side_effect=[(SimpleNamespace(x=210,y=585),(0,0,1,1),1),
                                             (SimpleNamespace(x=218,y=467),(0,0,1,1),1)])
        bot._validate_detected_match=Mock(return_value=(True,''))
        bot._execute_action=Mock(return_value=True)
        self.assertEqual(bot._reopen_hunt_search(image,bot.get_display_profile()),(218,467))
        bot._execute_action.assert_called_once()
        self.assertEqual(bot._execute_action.call_args.args[0],icon)


if __name__=='__main__':
    unittest.main()
