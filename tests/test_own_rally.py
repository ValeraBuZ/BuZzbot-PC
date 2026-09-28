import threading
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.own_rally import (OwnRallyController, participant_candidates,
                             rally_rows, same_text, select_new_rally, joining_squad_target)
from buzzbot.own_rally import first_saved_squad_target, saved_squad_loaded
from buzzbot.matching import detect_commander_settings_target, world_map_hud_is_visible
from buzzbot_app import AutoClicker
from buzzbot.state import BotState

ASSETS = Path(__file__).parent / 'assets'


class OwnRallyTests(unittest.TestCase):
    def test_preset_one_requires_squad_screen_and_load_receipt(self):
        before=cv2.imread(str(ASSETS/'own_rally/squad_before_preset.png'))
        after=cv2.imread(str(ASSETS/'own_rally/squad_preset_loaded.png'))
        for scale in (1,.75):
            for frame, loaded in ((before,False),(after,True)):
                scaled=cv2.resize(frame,None,fx=scale,fy=scale)
                target=first_saved_squad_target(scaled)
                self.assertIsNotNone(target)
                self.assertAlmostEqual(target[0],1095*scale,delta=1)
                self.assertAlmostEqual(target[1],249*scale,delta=1)
                self.assertEqual(saved_squad_loaded(scaled),loaded)
        before[225:273,1072:1118]=before[285:333,1072:1118]  # Slot 2 is not slot 1.
        self.assertIsNone(first_saved_squad_target(before))
        self.assertIsNone(first_saved_squad_target(cv2.imread(str(ASSETS/'own_rally/war_created.png'))))

    def test_preset_selection_requires_fresh_receipt_and_refreshes_march_location(self):
        before=cv2.imread(str(ASSETS/'own_rally/squad_before_preset.png'))
        after=cv2.imread(str(ASSETS/'own_rally/squad_preset_loaded.png'))
        controller=OwnRallyController({})
        controller.frame=Mock(side_effect=[after,before,after])
        controller.wait=Mock()
        controller.tap=Mock(return_value=True)
        fresh=SimpleNamespace(x=950,y=643)
        bot=SimpleNamespace(set_status_message=Mock(),current_account_id='main',
            _locate_image=Mock(return_value=(fresh,(830,620,230,48),1)),
            _validate_detected_match=Mock(return_value=(True,'')))
        march={'runtime_step':'march'}
        self.assertIs(controller.select_first_saved_squad(bot,march),fresh)
        controller.wait.assert_called_once()
        controller.tap.assert_called_once_with(bot,(1095,249))

    def test_preset_without_receipt_does_not_release_dispatch(self):
        before=cv2.imread(str(ASSETS/'own_rally/squad_before_preset.png'))
        controller=OwnRallyController({})
        controller.frame=Mock(return_value=before)
        controller.wait=Mock()
        controller.tap=Mock(return_value=True)
        bot=SimpleNamespace(set_status_message=Mock(),_locate_image=Mock(),
                            _save_routine_calibration_frame=Mock())
        self.assertIsNone(controller.select_first_saved_squad(bot,{}))
        bot._locate_image.assert_not_called()
        self.assertEqual(controller.tap.call_count,3)

    def test_missed_preset_tap_retries_in_place_and_uses_fresh_coordinates(self):
        before=cv2.imread(str(ASSETS/'own_rally/squad_before_preset.png'))
        after=cv2.imread(str(ASSETS/'own_rally/squad_preset_loaded.png'))
        controller=OwnRallyController({})
        controller.frame=Mock(side_effect=[before]*11+[
            cv2.resize(before,(960,540)),cv2.resize(after,(960,540))])
        controller.wait=Mock()
        controller.tap=Mock(return_value=True)
        fresh=SimpleNamespace(x=712,y=482)
        bot=SimpleNamespace(set_status_message=Mock(),current_account_id='main',
            _locate_image=Mock(return_value=(fresh,(620,465,180,36),1)),
            _validate_detected_match=Mock(return_value=(True,'')))
        self.assertIs(controller.select_first_saved_squad(bot,{}),fresh)
        self.assertEqual(controller.tap.call_count,2)
        self.assertEqual(controller.tap.call_args_list[0].args[1],(1095,249))
        self.assertEqual(controller.tap.call_args_list[1].args[1],(821.25,186.75))

    def test_preset_retry_stops_if_squad_panel_disappears(self):
        before=cv2.imread(str(ASSETS/'own_rally/squad_before_preset.png'))
        other=cv2.imread(str(ASSETS/'own_rally/war_created.png'))
        controller=OwnRallyController({})
        controller.frame=Mock(side_effect=[before,other,other])
        controller.wait=Mock()
        controller.tap=Mock(return_value=True)
        bot=SimpleNamespace(set_status_message=Mock(),_locate_image=Mock(),
                            _save_routine_calibration_frame=Mock())
        self.assertIsNone(controller.select_first_saved_squad(bot,{}))
        controller.tap.assert_called_once()
        bot._locate_image.assert_not_called()

    def test_late_preset_receipt_prevents_another_tap(self):
        before=cv2.imread(str(ASSETS/'own_rally/squad_before_preset.png'))
        after=cv2.imread(str(ASSETS/'own_rally/squad_preset_loaded.png'))
        controller=OwnRallyController({})
        controller.frame=Mock(side_effect=[before]*11+[after])
        controller.wait=Mock()
        controller.tap=Mock(return_value=True)
        fresh=SimpleNamespace(x=950,y=643)
        bot=SimpleNamespace(set_status_message=Mock(),current_account_id='main',
            _locate_image=Mock(return_value=(fresh,(830,620,230,48),1)),
            _validate_detected_match=Mock(return_value=(True,'')))
        self.assertIs(controller.select_first_saved_squad(bot,{}),fresh)
        controller.tap.assert_called_once()

    def test_march_is_blocked_before_input_if_own_rally_preset_did_not_load(self):
        bot=AutoClicker.__new__(AutoClicker)
        bot._check_worker_interrupted=Mock()
        bot.current_routine_task_id='collective_mind'
        bot.own_rally_controller=Mock()
        bot.own_rally_controller.select_first_saved_squad.return_value=None
        bot.set_status_message=Mock()
        bot.adb_client=Mock()
        march={'runtime_step':'march'}
        self.assertFalse(bot._execute_action(march,SimpleNamespace(x=950,y=643)))
        self.assertEqual(bot.routine_action_failure_reason,'own_rally_preset')
        bot.adb_client.tap.assert_not_called()

    def test_join_deployment_prompt_requires_button_and_queue_title(self):
        frame = cv2.imread(str(ASSETS/'own_rally/deployment_prompt.png'))
        for scale in (1, .75):
            point = joining_squad_target(cv2.resize(frame, None, fx=scale, fy=scale))
            self.assertIsNotNone(point)
            self.assertAlmostEqual(point[0], 969.5*scale, delta=1)
            self.assertAlmostEqual(point[1], 245*scale, delta=1)
        for region in ((slice(0,65), slice(1125,1280)), (slice(200,290), slice(850,1090))):
            partial = frame.copy()
            partial[region] = 0
            self.assertIsNone(joining_squad_target(partial))
        self.assertIsNone(joining_squad_target(cv2.imread(str(ASSETS/'own_rally/war_created.png'))))

    def test_join_creates_squad_before_dispatch_and_only_records_confirmed_march(self):
        controller = OwnRallyController({})
        deployment = cv2.imread(str(ASSETS/'own_rally/deployment_prompt.png'))
        controller.frame = Mock(side_effect=[deployment, np.zeros_like(deployment)])
        controller.wait_asset = Mock(return_value=(650,380))
        controller.tap = Mock(return_value=True)
        controller.wait = Mock()
        march = {'runtime_step':'march', 'group':'Коллективный разум'}
        bot = SimpleNamespace(stop_hotkey_pressed=False, search_images=[march],
            routine_tasks=[{'id':'collective_mind','enabled':False}],
            set_status_message=Mock(), _locate_image=Mock(return_value=((950,643),(0,0,1,1),1)),
            _execute_action=Mock(return_value=True), _register_routine_march=Mock())
        with patch('buzzbot.own_rally.time.time', return_value=1100):
            self.assertTrue(controller.send_joining_squad(bot,1000))
        self.assertEqual(controller.tap.call_count,2)
        bot._locate_image.assert_called_once_with(march)
        bot._execute_action.assert_called_once_with(march,(950,643))
        bot._register_routine_march.assert_called_once()
        self.assertIsNone(bot._own_rally_task)
        self.assertFalse(bot.routine_tasks[0]['enabled'])

    def test_desert_world_is_recognized_but_modal_dimming_is_not(self):
        frame=cv2.imread(str(ASSETS/'own_rally/desert_world.png'))
        self.assertTrue(world_map_hud_is_visible(frame))
        self.assertTrue(world_map_hud_is_visible(cv2.resize(frame,(960,540))))
        self.assertFalse(world_map_hud_is_visible((frame*.35).astype(np.uint8)))
        self.assertFalse(world_map_hud_is_visible(cv2.imread(str(ASSETS/'own_rally/war_created.png'))))
        frame[400:500,:130]=0
        self.assertFalse(world_map_hud_is_visible(frame))

    def test_bright_commander_settings_are_detected_at_both_resolutions(self):
        frame = cv2.imread(str(ASSETS / 'accounts/commander_bright.png'))
        for scale in (1, .75):
            resized = cv2.resize(frame, None, fx=scale, fy=scale)
            actual = detect_commander_settings_target(resized)
            self.assertIsNotNone(actual)
            self.assertAlmostEqual(actual[0], 180*scale, delta=1)
            self.assertAlmostEqual(actual[1], 637*scale, delta=1)
        other = cv2.imread(str(ASSETS / 'own_rally/war_created.png'))
        self.assertIsNone(detect_commander_settings_target(other))

    def test_real_rally_card_and_empty_list(self):
        frame = cv2.imread(str(ASSETS / 'own_rally/war_created.png'))
        rows = rally_rows(frame)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].owned)
        self.assertTrue(rows[0].preparing)
        self.assertIs(select_new_rally([], rows), rows[0])
        self.assertIsNone(select_new_rally(rows, rows))
        self.assertEqual(rally_rows(cv2.imread(str(ASSETS / 'own_rally/war_empty.png'))), [])
        scaled = rally_rows(cv2.resize(frame, (960, 540)))
        self.assertEqual(len(scaled), 1)
        self.assertTrue(scaled[0].matches(scaled[0]))

    def test_ambiguous_old_foreign_and_departed_rallies_are_rejected(self):
        row = rally_rows(cv2.imread(str(ASSETS / 'own_rally/war_created.png')))[0]
        self.assertIsNone(select_new_rally([], [row, row]))
        self.assertIsNone(select_new_rally([], [replace(row, owned=False)]))
        self.assertIsNone(select_new_rally([], [replace(row, preparing=False)]))
        self.assertFalse(row.matches(replace(row, name=np.zeros_like(row.name))))
        self.assertFalse(row.matches(replace(row, target=np.zeros_like(row.target))))
        blank = np.zeros((20, 80, 3), dtype=np.uint8)
        self.assertFalse(same_text(blank, blank))

    def test_candidates_exclude_leader_disabled_and_other_emulator(self):
        leader = dict(id='main', enabled=True, ldplayer_index=0, adb_serial='emulator-5554')
        profiles = [leader, dict(leader, id='a'), dict(leader, id='b'),
                    dict(leader, id='off', enabled=False), dict(leader, id='other', ldplayer_index=1)]
        self.assertEqual([p['id'] for p in participant_candidates(profiles, 'main')], ['a', 'b'])
        self.assertEqual([p['id'] for p in participant_candidates(profiles, 'main', 'b')], ['b'])
        self.assertEqual(participant_candidates(profiles, 'missing'), [])

    def test_adb_recovery_alias_does_not_remove_available_participant(self):
        for index in (0,1):
            emulator=f'emulator-{5554+index*2}'
            tcp=f'127.0.0.1:{5555+index*2}'
            for leader_serial, participant_serial in ((emulator,tcp),(tcp,emulator)):
                with self.subTest(index=index,leader_serial=leader_serial):
                    leader=dict(id='main',enabled=True,ldplayer_index=index,adb_serial=leader_serial)
                    participant=dict(leader,id='a',adb_serial=participant_serial)
                    before=deepcopy([leader,participant])
                    self.assertEqual(participant_candidates([leader,participant],'main'),[participant])
                    self.assertEqual(participant_candidates([leader,participant],'main','a'),[participant])
                    self.assertEqual([leader,participant],before)

    def test_different_or_unknown_adb_addresses_are_not_aliases(self):
        leader=dict(id='main',enabled=True,ldplayer_index=0,adb_serial='127.0.0.1:5555')
        for serial in ('emulator-5556','127.0.0.1:5557','192.168.1.2:5555','',None):
            with self.subTest(serial=serial):
                participant=dict(leader,id='a',adb_serial=serial)
                self.assertEqual(participant_candidates([leader,participant],'main'),[])

    def test_transient_task_does_not_change_saved_preferences_or_scheduler(self):
        bot = AutoClicker.__new__(AutoClicker)
        original = dict(id='collective_mind', group='Коллективный разум', enabled=False, settings={'level': 7})
        bot.routine_tasks = [original, dict(id='research', enabled=True)]
        before = deepcopy(bot.routine_tasks)
        bot.groups = {'Коллективный разум': False}
        bot.account_switch_task = None
        bot.routine_only_task_id = 'collective_mind'
        bot._own_rally_task = dict(deepcopy(original), enabled=True)
        self.assertTrue(bot.get_routine_task('collective_mind')['enabled'])
        self.assertTrue(bot._routine_group_enabled('Коллективный разум'))
        self.assertEqual([p['id'] for p in bot._scheduler_routine_tasks()], ['collective_mind'])
        self.assertEqual(bot.routine_tasks, before)
        bot._own_rally_task = None
        self.assertFalse(bot.get_routine_task('collective_mind')['enabled'])
        self.assertFalse(bot._routine_group_enabled('Коллективный разум'))

    def test_stop_cannot_be_undone_by_next_internal_phase(self):
        controller = OwnRallyController({})
        bot = SimpleNamespace(stop_hotkey_pressed=False, stop_event=threading.Event(), _set_state=Mock())
        bot.stop_event.set()
        controller.cancel.set()
        with self.assertRaises(InterruptedError):
            controller.resume_worker(bot)
        self.assertTrue(bot.stop_event.is_set())
        bot._set_state.assert_not_called()

    def test_internal_phase_completion_keeps_mode_running_but_user_stop_does_not(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot._thread = threading.current_thread()
        bot.own_rally_controller = OwnRallyController({})
        bot._set_state(BotState.STOPPED)
        self.assertTrue(bot.is_running)
        bot.own_rally_controller.cancel.set()
        bot._set_state(BotState.STOPPED)
        self.assertFalse(bot.is_running)

    def test_creation_outcome_releases_internal_worker_without_advancing_normal_tasks(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.own_rally_controller = OwnRallyController({})
        bot.stop_event = threading.Event()
        bot.current_routine_index = 7
        bot._advance_routine_after_outcome({'id':'collective_mind'}, 1000)
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(bot.current_routine_index, 7)
        self.assertFalse(bot.own_rally_controller.cancel.is_set())

    def test_alliance_and_war_click_icons_above_the_recognized_labels(self):
        bot = SimpleNamespace(_return_to_main_screen=Mock(return_value=True), stop_hotkey_pressed=False)
        controller = OwnRallyController({})
        controller.wait_asset = Mock(side_effect=[(972,689),(180,44),(666,477),(641,53)])
        controller.frame = Mock(return_value=np.zeros((720,1280,3),np.uint8))
        controller.tap = Mock(return_value=True)
        self.assertTrue(controller.open_war(bot))
        self.assertEqual([c.args[1] for c in controller.tap.call_args_list],[(972,649),(666,429)])

    def test_switch_cannot_continue_without_verified_target(self):
        controller = OwnRallyController({})
        bot = SimpleNamespace(stop_hotkey_pressed=False, stop_event=threading.Event(), _set_state=Mock(),
                              _prepare_account_switch=Mock(return_value=True), save_config=Mock(),
                              _run_clicker_loop=Mock(), account_switch_task={'settings': {}},
                              routine_next_run={}, current_account_id='wrong', account_switch_confirmed=False,
                              account_switch_error='ID не совпал')
        with self.assertRaisesRegex(RuntimeError, 'ID не совпал'):
            controller.switch(bot, {'id':'main'})
        self.assertEqual(bot.account_switch_failure_count, 1)
        self.assertTrue(bot.account_switch_task['settings']['_stop_after_verification'])
        bot.save_config.assert_called_once()

    def test_expired_rally_never_opens_or_sends(self):
        controller = OwnRallyController({})
        controller.open_war = Mock()
        with patch('buzzbot.own_rally.time.time', return_value=1300):
            self.assertFalse(controller.join(Mock(), Mock(), 1000))
        controller.open_war.assert_not_called()

    def test_complete_round_returns_to_leader_and_cleans_override(self):
        controller = OwnRallyController({'leader_id':'main', 'repeat':False})
        profile = dict(id='main', name='Main', ldplayer_index=0, adb_serial='emulator-5554', auto_login=True)
        bot = SimpleNamespace(account_profiles=[profile, dict(profile,id='a',name='A')],
                              stop_hotkey_pressed=False, account_has_saved_login=lambda _id:True,
                              account_has_saved_password=lambda _id:True, set_status_message=Mock())
        controller.switch = Mock()
        identity = object()
        controller.create = Mock(return_value=(identity, 1000))
        controller.join = Mock(return_value=True)
        controller.run(bot)
        self.assertEqual([c.args[1]['id'] for c in controller.switch.call_args_list], ['main','a','main'])
        controller.join.assert_called_once_with(bot, identity, 1000)
        self.assertEqual(controller.rounds, 1)
        self.assertIsNone(bot._own_rally_task)

    def test_empty_searches_wait_without_counting_them_as_broken_rallies(self):
        controller = OwnRallyController({'leader_id':'main'})
        profile = dict(id='main', name='Main', ldplayer_index=0, adb_serial='emulator-5554', auto_login=True)
        bot = SimpleNamespace(account_profiles=[profile,dict(profile,id='a',name='A')],
                              stop_hotkey_pressed=False, account_has_saved_login=lambda _:True,
                              account_has_saved_password=lambda _:True, set_status_message=Mock(),
                              routine_next_run={}, routine_last_outcome={
                                  'reason':'коллективный разум доступных уровней не найден'})
        controller.switch=Mock()
        controller.create=Mock(return_value=(None,0))
        waits=[]
        def wait(bot,seconds):
            waits.append(seconds)
            if len(waits)==3:
                controller.cancel.set()
        controller.wait=wait
        controller.run(bot)
        self.assertEqual(len(waits),3)
        self.assertEqual(controller.create.call_count,3)
        self.assertEqual(bot.account_switch_stop_message,'Режим своих сборов остановлен')
        self.assertIsNone(bot.own_rally_controller)

    def test_unavailable_preset_keeps_mode_running_until_user_stops_it(self):
        controller = OwnRallyController({'leader_id':'main'})
        profile = dict(id='main', name='Main', ldplayer_index=0,
                       adb_serial='emulator-5554', auto_login=True)
        bot = SimpleNamespace(account_profiles=[profile,dict(profile,id='a',name='A')],
            stop_hotkey_pressed=False, account_has_saved_login=lambda _:True,
            account_has_saved_password=lambda _:True, set_status_message=Mock(),
            routine_next_run={}, routine_last_outcome={
                'reason':'сохранённый отряд №1 не загружен'})
        controller.switch=Mock()
        controller.create=Mock(return_value=(None,0))
        controller.join=Mock()
        waits=[]
        def wait(bot,seconds):
            waits.append(seconds)
            if len(waits)==4:
                controller.cancel.set()
        controller.wait=wait
        controller.run(bot)
        self.assertEqual(waits,[30]*4)
        self.assertEqual(controller.create.call_count,4)
        controller.join.assert_not_called()
        controller.switch.assert_called_once_with(bot,profile)
        self.assertEqual(bot.account_switch_stop_message,'Режим своих сборов остановлен')
        self.assertIsNone(bot.own_rally_controller)


if __name__ == '__main__':
    unittest.main()
