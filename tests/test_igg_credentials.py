import unittest

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
