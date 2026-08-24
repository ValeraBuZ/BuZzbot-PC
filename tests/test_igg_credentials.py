import unittest
import threading

import cv2
import numpy as np

from buzzbot_app import AutoClicker, GAME_PACKAGE


IGG_FORM_XML = (
    '<hierarchy><node class="android.webkit.WebView" text="IGG Account">'
    '<node class="android.widget.EditText" password="false" bounds="[238,89][1042,155]" />'
    '<node class="android.widget.EditText" password="true" bounds="[238,176][1042,239]" />'
    '<node class="android.widget.Button" clickable="true" bounds="[238,260][837,326]" />'
    '</node></hierarchy>'
)


class FakeAdbClient:
    def __init__(self, package=GAME_PACKAGE, ui_xml=IGG_FORM_XML):
        self.package = package
        self._ui_xml = ui_xml

    def current_foreground_package(self):
        return self.package

    def ui_xml(self):
        return self._ui_xml


class FormAdbClient(FakeAdbClient):
    def __init__(self):
        super().__init__()
        self.taps = []
        self.inputs = []
        self.clear_calls = 0

    def is_responsive(self):
        return True

    def tap(self, x, y):
        self.taps.append((x, y))

    def clear_focused_text(self, _maximum):
        self.clear_calls += 1

    def input_private_text(self, value):
        self.inputs.append(value)


class FakeCredentialStore:
    def get_password(self, key):
        if key == "login:igg:main":
            return "user@example.com"
        return "safe-password" if key == "igg:main" else None


class IggCredentialTests(unittest.TestCase):
    def make_bot(self, *, auto_login=True, ui_xml=IGG_FORM_XML):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_switch_selected_at = 0.0
        bot.account_switch_auto_login_attempted = False
        bot.account_switch_error = ""
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient(ui_xml=ui_xml)
        bot.account_profiles = [{"id": "main", "auto_login": auto_login}]
        bot.routine_last_action_time = 0.0
        bot.click_count = 0
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.fill_igg_credentials = lambda _account_id, form=None: bool(form)
        return bot

    @staticmethod
    def task():
        return {
            "id": "__account_switch__",
            "settings": {"target_account_id": "main", "login_method": "igg"},
        }

    def test_igg_form_is_filled_and_submitted_once(self):
        bot = self.make_bot()

        handled = bot._try_account_switch_igg_login(self.task())

        self.assertTrue(handled)
        self.assertTrue(bot.account_switch_auto_login_attempted)
        self.assertGreater(bot.account_switch_selected_at, 0.0)
        self.assertEqual(bot.click_count, 1)

    def test_igg_login_waits_for_verified_form(self):
        bot = self.make_bot(ui_xml='<hierarchy><node text="Game" /></hierarchy>')

        handled = bot._try_account_switch_igg_login(self.task())

        self.assertFalse(handled)
        self.assertFalse(bot.account_switch_auto_login_attempted)

    def test_igg_login_stops_when_auto_login_is_disabled(self):
        bot = self.make_bot(auto_login=False)

        handled = bot._try_account_switch_igg_login(self.task())

        self.assertTrue(handled)
        self.assertIn("отключён", bot.account_switch_error)

    def test_igg_confirmation_continues_and_restarts_loading_timer(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.account_switch_selected_at = 0.0
        bot.account_switch_auto_login_attempted = True
        frame = np.full((720, 1280, 3), 245, dtype=np.uint8)
        frame[90:274, 238:1043] = (70, 70, 70)
        frame[294:360, 238:1043] = (45, 205, 255)
        frame[379:445, 238:1043] = (215, 215, 215)
        bot._capture_screen_bgr = lambda force=False: (frame, (0, 0))
        tapped = []
        bot._tap_routine_fallback = lambda target, *_args: tapped.append(target) or True
        bot._interruptible_sleep = lambda _seconds: None

        handled = bot._try_account_switch_igg_confirmation(self.task())

        self.assertTrue(handled)
        self.assertEqual(tapped, [(640, 326)])
        self.assertGreater(bot.account_switch_selected_at, 0.0)

    def test_initial_igg_confirmation_requests_different_account(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.account_switch_selected_at = 0.0
        bot.account_switch_auto_login_attempted = False
        frame = np.full((720, 1280, 3), 245, dtype=np.uint8)
        frame[90:274, 238:1043] = (70, 70, 70)
        frame[294:360, 238:1043] = (45, 205, 255)
        frame[379:445, 238:1043] = (215, 215, 215)
        bot._capture_screen_bgr = lambda force=False: (frame, (0, 0))
        tapped = []
        bot._tap_routine_fallback = lambda target, *_args: tapped.append(target) or True
        bot._interruptible_sleep = lambda _seconds: None

        handled = bot._try_account_switch_igg_confirmation(self.task())

        self.assertTrue(handled)
        self.assertEqual(tapped, [(640, 412)])
        self.assertEqual(bot.account_switch_selected_at, 0.0)

    def test_interrupted_connection_resets_account_switch_for_retry(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_switch_selected_at = 123.0
        bot.account_switch_auto_login_attempted = True
        bot.account_switch_error = "old error"
        bot.routine_completed_steps = {
            "account_switch_igg_id_selected",
            "unrelated_step",
        }
        bot.routine_current_had_action = True
        bot.routine_last_action_time = 0.0
        bot.blocked_coords = {(100, 100): 999.0}
        bot._interruptible_sleep = lambda _seconds: None
        frame = np.full((720, 1280, 3), 35, dtype=np.uint8)
        cv2.rectangle(frame, (321, 164), (959, 572), (210, 210, 210), thickness=-1)
        cv2.rectangle(frame, (507, 482), (773, 534), (45, 190, 245), thickness=-1)
        bot._capture_screen_bgr = lambda force=False: (frame, (0, 0))
        tapped = []
        bot._tap_routine_fallback = lambda target, *_args: tapped.append(target) or True

        handled = bot._try_account_switch_connection_recovery(self.task())

        self.assertTrue(handled)
        self.assertEqual(tapped, [(640, 508)])
        self.assertEqual(bot.account_switch_selected_at, 0.0)
        self.assertFalse(bot.account_switch_auto_login_attempted)
        self.assertEqual(bot.account_switch_error, "")
        self.assertEqual(bot.routine_completed_steps, {"unrelated_step"})
        self.assertFalse(bot.routine_current_had_action)

    def test_igg_completion_closes_each_nested_screen_once(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_switch_selected_at = 1.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected"}
        bot._interruptible_sleep = lambda _seconds: None
        tapped = []
        bot._tap_routine_fallback = lambda target, *_args: tapped.append(target) or True

        login_methods = np.full((720, 1280, 3), 160, dtype=np.uint8)
        login_methods[86:668, 133:1147] = (35, 35, 35)
        login_methods[594:643, 507:773] = (45, 180, 235)

        account_details = np.full((720, 1280, 3), (35, 35, 35), dtype=np.uint8)
        for top, bottom in ((158, 191), (229, 263), (371, 406)):
            account_details[top:bottom, 950:1130] = (45, 180, 235)

        settings = np.full((720, 1280, 3), (25, 25, 25), dtype=np.uint8)
        for left, right in ((188, 387), (430, 629), (670, 869), (910, 1110)):
            settings[118:263, left:right] = (65, 80, 95)

        profile = np.full((720, 1280, 3), (130, 130, 130), dtype=np.uint8)
        profile[26:286, 808:1274] = (35, 35, 35)
        import cv2
        cv2.circle(profile, (47, 45), 28, (30, 150, 220), thickness=-1)

        frames = iter((login_methods, account_details, settings, profile, profile))
        bot._capture_screen_bgr = lambda force=False: (next(frames), (0, 0))

        for _index in range(4):
            self.assertTrue(bot._try_account_switch_return_to_main(self.task()))
        self.assertFalse(bot._try_account_switch_return_to_main(self.task()))

        self.assertEqual(tapped, [(640, 618), (1133, 43), (1133, 43), (47, 45)])
        self.assertIn("account_switch_profile_closed", bot.routine_completed_steps)

    def test_completed_switch_keeps_success_flag_for_ui(self):
        bot = AutoClicker.__new__(AutoClicker)
        task = {
            "id": "__account_switch__",
            "settings": {"target_account_id": "main", "probe_only": False},
        }
        bot.current_routine_task_id = "__account_switch__"
        bot.get_routine_task = lambda _task_id: task
        bot.account_switch_error = ""
        bot.account_switch_confirmed = True
        bot.account_switch_selected_at = 2.0
        bot.account_switch_probe_ready = False
        bot.account_switch_auto_login_attempted = True
        bot.account_switch_task = task
        bot.routine_current_had_action = True
        bot.routine_only_task_id = "__account_switch__"
        bot.account_switch_candidates = []
        bot.account_profiles = [{"id": "main", "name": "Main"}]
        bot.select_account_profile = lambda _account_id: True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.account_rotation_enabled = False
        bot.routine_mode = True
        bot.stop_event = threading.Event()

        bot._finish_current_routine()

        self.assertTrue(bot.account_switch_confirmed)
        self.assertEqual(bot.account_switch_last_result, "Аккаунт переключён: Main")

    def test_account_switch_launches_game_from_android_desktop(self):
        class LauncherAdb:
            def __init__(self):
                self.launched = []

            def current_foreground_package(self):
                return "com.android.launcher3"

            def launch_package(self, package):
                self.launched.append(package)

        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = LauncherAdb()
        bot.account_switch_selected_at = 0.0
        bot.routine_last_action_time = 0.0
        bot._invalidate_capture = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot._interruptible_sleep = lambda _seconds: None

        handled = bot._try_account_switch_visual_fallback(self.task())

        self.assertTrue(handled)
        self.assertEqual(bot.adb_client.launched, [GAME_PACKAGE])

    def test_fill_igg_credentials_uses_verified_xml_targets(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FormAdbClient()
        bot.account_profiles = [
            {"id": "main", "login_method": "igg", "igg_login": ""}
        ]
        bot.credential_store = FakeCredentialStore()
        bot._invalidate_capture = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None

        self.assertTrue(bot.fill_igg_credentials("main"))
        self.assertEqual(
            bot.adb_client.taps,
            [(640, 122), (640, 207), (537, 293)],
        )
        self.assertEqual(bot.adb_client.inputs, ["user@example.com", "safe-password"])
        self.assertEqual(bot.adb_client.clear_calls, 2)


class MemoryCredentialStore:
    def __init__(self):
        self.values = {}

    def has_password(self, key):
        return key in self.values

    def set_password(self, key, value):
        self.values[key] = value

    def get_password(self, key):
        return self.values.get(key)

    def delete_password(self, key):
        return self.values.pop(key, None) is not None


class LocalCredentialTests(unittest.TestCase):
    def make_bot(self, profile):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_profiles = [profile]
        bot.credential_store = MemoryCredentialStore()
        bot.save_config = lambda: None
        return bot

    def test_login_and_password_are_kept_out_of_portable_profile(self):
        profile = {"id": "zzub1", "login_method": "igg", "igg_login": "legacy"}
        bot = self.make_bot(profile)

        bot.save_account_credentials("zzub1", "local-login", "local-password", True)

        self.assertEqual(profile["igg_login"], "")
        self.assertEqual(profile["google_login"], "")
        self.assertTrue(profile["auto_login"])
        self.assertEqual(bot.get_account_login("zzub1", "igg"), "local-login")
        self.assertEqual(bot.credential_store.get_password("igg:zzub1"), "local-password")

    def test_legacy_login_is_migrated_to_machine_local_store(self):
        profile = {"id": "zzub1", "login_method": "igg", "igg_login": "legacy-login"}
        bot = self.make_bot(profile)

        self.assertTrue(bot._migrate_account_logins_to_credential_store())

        self.assertEqual(profile["igg_login"], "")
        self.assertEqual(bot.get_account_login("zzub1", "igg"), "legacy-login")


if __name__ == "__main__":
    unittest.main()
