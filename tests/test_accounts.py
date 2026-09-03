import unittest

from buzzbot.accounts import (
    apply_tasks,
    default_account_profiles,
    ensure_account_task_defaults,
    extract_google_account_targets,
    extract_android_google_accounts,
    extract_google_accounts,
    extract_igg_id_targets,
    extract_igg_login_form,
    extract_igg_unregistered_cancel_target,
    mask_google_account,
    next_enabled_account,
    normalize_account_profiles,
    recover_account_profiles,
    requires_google_reauthentication,
    requires_manual_google_verification,
    snapshot_tasks,
)
from buzzbot.routines import default_routine_tasks


class AccountProfileTests(unittest.TestCase):
    def test_local_credential_keys_restore_profiles_without_logins(self):
        profiles = recover_account_profiles(
            [{"id": "phoenix675", "name": "Phoenix675"}],
            {
                "login:igg:zzub1",
                "igg:zzub1",
                "login:igg:buzz",
                "igg:buzz",
                "login:google:luckynoob",
                "google:luckynoob",
                "login:igg:igg_7",
                "igg:igg_7",
            },
        )
        by_id = {profile["id"]: profile for profile in profiles}

        self.assertEqual(by_id["zzub1"]["name"], "zZuB1")
        self.assertEqual(by_id["luckynoob"]["login_method"], "google")
        self.assertTrue(by_id["luckynoob"]["auto_login"])
        self.assertFalse(by_id["buzz"]["enabled"])
        self.assertEqual(by_id["igg_7"]["chooser_index"], 1)
        self.assertEqual(by_id["zzub1"]["igg_login"], "")

    def test_local_keys_repair_existing_login_method(self):
        profiles = recover_account_profiles(
            [{"id": "luckynoob", "name": "LuckyNoob", "login_method": "igg"}],
            {"login:google:luckynoob", "luckynoob"},
        )

        self.assertEqual(profiles[0]["login_method"], "google")
        self.assertTrue(profiles[0]["auto_login"])
    def test_extracts_safe_cancel_from_unregistered_igg_dialog(self):
        xml = """
        <hierarchy>
          <node text="This E-mail is not registered. Register?" class="android.widget.TextView" />
          <node clickable="true" class="android.view.View" bounds="[411,416][642,483]" />
          <node clickable="true" class="android.view.View" bounds="[640,416][870,483]" />
          <node clickable="true" class="android.widget.Button" bounds="[238,260][837,326]" />
        </hierarchy>
        """
        self.assertEqual(extract_igg_unregistered_cancel_target(xml), (526, 449))
        self.assertIsNone(
            extract_igg_unregistered_cancel_target('<hierarchy><node text="Sign in" /></hierarchy>')
        )

    def test_extracts_unique_google_accounts_from_android_dump(self):
        account_dump = """
        Account {name=person@example.com, type=com.google}
        Account {name=other@example.com, type=com.google}
        Account {name=person@example.com, type=com.google}
        Account {name=local, type=com.example}
        """
        self.assertEqual(
            extract_android_google_accounts(account_dump),
            ["person@example.com", "other@example.com"],
        )

    def test_default_profile_targets_phoenix(self):
        profile = default_account_profiles()[0]
        self.assertEqual(profile["name"], "Phoenix675")
        self.assertEqual(profile["ldplayer_index"], 5)
        self.assertEqual(profile["adb_serial"], "emulator-5564")
        self.assertEqual(profile["chooser_index"], 2)
        self.assertEqual(profile["login_method"], "igg")

    def test_profile_keeps_task_selection(self):
        tasks = default_routine_tasks()
        next(task for task in tasks if task["id"] == "food")["enabled"] = False
        profile = default_account_profiles()[0]
        snapshot_tasks(profile, tasks)
        next(task for task in tasks if task["id"] == "food")["enabled"] = True
        apply_tasks(profile, tasks)
        self.assertFalse(next(task for task in tasks if task["id"] == "food")["enabled"])

    def test_new_safe_daily_tasks_are_enabled_on_every_saved_account(self):
        tasks = default_routine_tasks()
        profiles = normalize_account_profiles([
            {
                "id": "a",
                "name": "A",
                "task_enabled": {"food": True},
                "task_settings": {
                    "mysterious_merchant": {"avoid_gems": False},
                    "trucks": {"avoid_gems": False, "max_dispatches": 2},
                },
            },
            {"id": "b", "name": "B"},
        ])

        ensure_account_task_defaults(
            profiles,
            tasks,
            enabled_task_ids=("mysterious_merchant", "trucks"),
        )

        for profile in profiles:
            self.assertTrue(profile["task_enabled"]["mysterious_merchant"])
            self.assertTrue(profile["task_enabled"]["trucks"])
            self.assertTrue(
                profile["task_settings"]["mysterious_merchant"]["avoid_gems"]
            )
            self.assertTrue(profile["task_settings"]["trucks"]["avoid_gems"])
        self.assertEqual(profiles[0]["task_settings"]["trucks"]["max_dispatches"], 2)

    def test_rotation_uses_one_enabled_profile_at_a_time(self):
        profiles = normalize_account_profiles([
            {"id": "a", "name": "A", "enabled": True},
            {"id": "b", "name": "B", "enabled": True},
        ])
        self.assertEqual(next_enabled_account(profiles, "a")["id"], "b")
        self.assertEqual(next_enabled_account(profiles, "b")["id"], "a")

    def test_rotation_stays_on_the_current_ldplayer(self):
        profiles = normalize_account_profiles([
            {"id": "solo", "name": "Solo", "enabled": True, "ldplayer_index": 1},
            {"id": "a", "name": "A", "enabled": True, "ldplayer_index": 5},
            {"id": "b", "name": "B", "enabled": True, "ldplayer_index": 5},
        ])

        self.assertIsNone(next_enabled_account(profiles, "solo", 1))
        self.assertEqual(next_enabled_account(profiles, "a", 5)["id"], "b")
        self.assertEqual(next_enabled_account(profiles, "b", 5)["id"], "a")

    def test_google_chooser_index_is_normalized(self):
        profiles = normalize_account_profiles([
            {
                "id": "a",
                "name": "A",
                "chooser_index": 0,
                "google_login": " person@example.com ",
                "auto_login": True,
            },
            {"id": "b", "name": "B", "chooser_index": 99},
        ])
        self.assertEqual(profiles[0]["chooser_index"], 1)
        self.assertEqual(profiles[1]["chooser_index"], 20)
        self.assertEqual(profiles[0]["google_login"], "person@example.com")
        self.assertTrue(profiles[0]["auto_login"])

    def test_profiles_default_to_igg_login(self):
        profiles = normalize_account_profiles([
            {"id": "a", "name": "A", "igg_login": " a@example.com "},
            {"id": "b", "name": "B", "login_method": "unsupported"},
        ])
        self.assertEqual(profiles[0]["login_method"], "igg")
        self.assertEqual(profiles[0]["igg_login"], "a@example.com")
        self.assertEqual(profiles[1]["login_method"], "igg")

    def test_google_reauthentication_is_detected(self):
        self.assertTrue(requires_google_reauthentication('<node text="Подтвердите свою личность" />'))
        self.assertTrue(requires_google_reauthentication('<node text="Verify it\'s you" />'))
        self.assertFalse(requires_google_reauthentication('<node text="Doomsday: Last Survivors" />'))

    def test_recaptcha_requires_manual_verification(self):
        self.assertTrue(requires_manual_google_verification('<node text="reCAPTCHA" />'))
        self.assertTrue(
            requires_manual_google_verification('<node text="Security verification: complete the puzzle" />')
        )
        self.assertTrue(
            requires_manual_google_verification('<node text="Подтвердите, что вы не робот" />')
        )
        self.assertFalse(requires_manual_google_verification('<node text="Password" />'))

    def test_google_accounts_are_extracted_in_chooser_order(self):
        xml = (
            '<hierarchy><node text="First" content-desc="first@example.com" />'
            '<node text="second@example.com" />'
            '<node text="FIRST@example.com" /></hierarchy>'
        )
        self.assertEqual(extract_google_accounts(xml), [
            {"chooser_index": 1, "email": "first@example.com"},
            {"chooser_index": 2, "email": "second@example.com"},
        ])

    def test_google_account_targets_use_clickable_row_bounds(self):
        xml = (
            '<hierarchy><node resource-id="com.google.android.gms:id/container" '
            'clickable="true" bounds="[312,302][967,405]">'
            '<node resource-id="com.google.android.gms:id/account_name" '
            'text="first@example.com" /></node></hierarchy>'
        )
        self.assertEqual(extract_google_account_targets(xml), [
            {
                "chooser_index": 1,
                "email": "first@example.com",
                "center": (639, 353),
            }
        ])

    def test_google_account_mask_hides_local_part(self):
        self.assertEqual(mask_google_account("person@example.com"), "p*****@example.com")

    def test_igg_login_form_targets_accessible_fields_and_button(self):
        xml = (
            '<hierarchy><node class="android.webkit.WebView" text="IGG Account">'
            '<node class="android.widget.EditText" password="false" bounds="[238,89][1042,155]" />'
            '<node class="android.widget.EditText" password="true" bounds="[238,176][1042,239]" />'
            '<node class="android.widget.Button" clickable="true" bounds="[238,260][837,326]" />'
            '</node></hierarchy>'
        )
        self.assertEqual(
            extract_igg_login_form(xml),
            {"login": (640, 122), "password": (640, 207), "submit": (537, 293)},
        )

    def test_igg_login_form_rejects_unrelated_webview(self):
        xml = (
            '<hierarchy><node class="android.webkit.WebView" text="Other">'
            '<node class="android.widget.EditText" password="false" bounds="[1,1][20,20]" />'
            '<node class="android.widget.EditText" password="true" bounds="[1,21][20,40]" />'
            '<node class="android.widget.Button" clickable="true" bounds="[1,41][20,60]" />'
            '</node></hierarchy>'
        )
        self.assertIsNone(extract_igg_login_form(xml))

    def test_igg_login_form_supports_flattened_webview(self):
        xml = (
            '<hierarchy><node class="android.widget.TextView" text="Вход в IGG Account" '
            'bounds="[520,15][760,52]" />'
            '<node class="android.webkit.WebView" '
            'resource-id="com.igg.android.doomsdaylastsurvivors:id/webview_web" '
            'bounds="[0,68][1280,720]" /></hierarchy>'
        )
        self.assertEqual(
            extract_igg_login_form(xml),
            {"login": (640, 122), "password": (640, 208), "submit": (538, 294)},
        )

    def test_igg_login_form_rejects_id_selection_webview(self):
        xml = (
            '<hierarchy><node class="android.widget.TextView" text="Выбрать IGG ID" '
            'bounds="[543,15][736,52]" />'
            '<node class="android.webkit.WebView" text="IGG Account" '
            'bounds="[0,68][1280,720]" /></hierarchy>'
        )
        self.assertIsNone(extract_igg_login_form(xml))

    def test_extracts_saved_igg_id_rows_without_exposing_ids(self):
        xml = (
            '<hierarchy><node class="android.widget.TextView" text="Выбрать IGG ID" '
            'bounds="[543,15][736,52]" />'
            '<node class="android.widget.TextView" text="IGG ID: 123456789" '
            'bounds="[261,149][894,176]" />'
            '<node class="android.widget.TextView" text="IGG ID: 987654321" '
            'bounds="[261,214][894,241]" /></hierarchy>'
        )
        self.assertEqual(extract_igg_id_targets(xml), [
            {"chooser_index": 1, "center": (577, 162)},
            {"chooser_index": 2, "center": (577, 227)},
        ])


if __name__ == "__main__":
    unittest.main()
