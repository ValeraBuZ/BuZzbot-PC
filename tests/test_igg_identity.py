import json
import unittest

from buzzbot.accounts import extract_igg_id_targets, normalize_account_profiles
from buzzbot.igg_identity import selected_sdk_igg_id


class IggSdkIdentityTests(unittest.TestCase):
    def test_identity_uses_visual_order_when_xml_order_is_reversed(self):
        xml = """<hierarchy>
          <node class="android.widget.TextView" text="IGG ID: 2115346649"
                bounds="[261,214][894,241]" />
          <node class="android.widget.TextView" text="IGG ID: 2097378622"
                bounds="[261,149][894,176]" />
        </hierarchy>"""
        rows = extract_igg_id_targets(xml)
        self.assertEqual(rows, [
            {"chooser_index": 1, "center": (577, 162), "igg_id": "2097378622"},
            {"chooser_index": 2, "center": (577, 227), "igg_id": "2115346649"},
        ])
        self.assertEqual(selected_sdk_igg_id(xml, 1), rows[0]["igg_id"])
        self.assertEqual(selected_sdk_igg_id(xml, 2), rows[1]["igg_id"])

    def test_zero_size_offscreen_and_unbounded_labels_are_not_selectable(self):
        xml = """<hierarchy>
          <node class="android.view.View" content-desc="IGG ID: 1111111111"
                bounds="[0,0][0,0]" />
          <node class="android.widget.TextView" text="IGG ID: 2222222222"
                bounds="[261,750][894,780]" />
          <node class="android.widget.TextView" text="IGG ID: 3333333333"
                bounds="[1300,149][1600,176]" />
          <node class="android.widget.TextView" text="IGG ID: 5555555555"
                bounds="[-500,149][-100,176]" />
          <node class="android.widget.TextView" text="IGG ID: 4444444444" />
          <node class="android.view.View" content-desc="IGG ID: 2097378622"
                bounds="[261,149][894,176]" />
        </hierarchy>"""
        self.assertEqual(len(extract_igg_id_targets(xml)), 1)
        self.assertEqual(selected_sdk_igg_id(xml), "2097378622")
        self.assertIsNone(selected_sdk_igg_id(xml, 2))

    def test_parent_and_child_labels_do_not_create_two_rows(self):
        xml = """<hierarchy>
          <node class="android.view.View" content-desc="IGG ID: 2097378622"
                clickable="true" bounds="[250,140][920,190]">
            <node class="android.widget.TextView" text="IGG ID: 2097378622"
                  clickable="false" bounds="[261,149][894,176]" />
          </node>
          <node class="android.widget.TextView" text="IGG ID: 2115346649"
                bounds="[261,214][894,241]" />
        </hierarchy>"""
        rows = extract_igg_id_targets(xml)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["center"], (577, 162))
        self.assertEqual(selected_sdk_igg_id(xml, 2), "2115346649")

    def test_hidden_or_disabled_ancestor_excludes_its_rows(self):
        for attribute in ('visible-to-user="false"', 'displayed="false"', 'enabled="false"'):
            with self.subTest(attribute=attribute):
                xml = f"""<hierarchy><node {attribute}>
                  <node class="android.widget.TextView" text="IGG ID: 2097378622"
                        bounds="[261,149][894,176]" />
                </node></hierarchy>"""
                self.assertEqual(extract_igg_id_targets(xml), [])
                self.assertIsNone(selected_sdk_igg_id(xml))

    def test_parent_viewport_excludes_rows_outside_the_visible_webview(self):
        xml = """<hierarchy><node class="android.webkit.WebView" bounds="[0,68][1280,400]">
          <node class="android.widget.TextView" text="IGG ID: 2115346649"
                bounds="[261,410][894,441]" />
          <node class="android.widget.TextView" text="IGG ID: 2097378622"
                bounds="[261,149][894,176]" />
        </node></hierarchy>"""
        self.assertEqual(selected_sdk_igg_id(xml), "2097378622")
        self.assertEqual(len(extract_igg_id_targets(xml)), 1)

    def test_display_bounds_are_respected_for_nonreference_resolution(self):
        xml = """<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1920,1080]">
          <node class="android.view.View" text="IGG ID: 2097378622"
                bounds="[1300,750][1750,780]" />
          <node class="android.view.View" text="IGG ID: 2115346649"
                bounds="[1300,1100][1750,1130]" />
        </node></hierarchy>"""
        self.assertEqual(selected_sdk_igg_id(xml), "2097378622")
        self.assertEqual(len(extract_igg_id_targets(xml)), 1)

    def test_missing_bounds_bad_xml_and_invalid_index_cannot_prove_identity(self):
        xml = '<hierarchy><node class="android.view.View" text="IGG ID: 2097378622" /></hierarchy>'
        self.assertIsNone(selected_sdk_igg_id(xml))
        self.assertIsNone(selected_sdk_igg_id("broken"))
        for index in (0, -1, 21, None, "1"):
            with self.subTest(index=index):
                self.assertIsNone(selected_sdk_igg_id(xml, index))

    def test_only_unambiguous_complete_ids_are_accepted(self):
        for label in ("IGG ID: 12345", "IGG ID: 123456789012345678901", "IGG ID: 2097378622 trailing", "IGG ID: １２３４５６"):
            with self.subTest(label=label):
                xml = f'<hierarchy><node class="android.widget.TextView" text="{label}" bounds="[261,149][894,176]" /></hierarchy>'
                self.assertIsNone(selected_sdk_igg_id(xml))


class VerifiedIggProfileTests(unittest.TestCase):
    def test_verified_identity_survives_config_roundtrip(self):
        source = [{"id": "igg_5", "name": "IGG 5", "verified_igg_id": "2097378622"}]
        profiles = normalize_account_profiles(source)
        reloaded = normalize_account_profiles(json.loads(json.dumps(profiles)))
        self.assertEqual(reloaded[0]["verified_igg_id"], "2097378622")
        self.assertEqual(reloaded, profiles)

    def test_invalid_or_missing_verified_identity_is_empty(self):
        for value in (None, "", "12345", "123456789012345678901", "wrong", "１２３４５６"):
            with self.subTest(value=value):
                profile = normalize_account_profiles([{"id": "igg_5", "verified_igg_id": value}])[0]
                self.assertEqual(profile["verified_igg_id"], "")

    def test_verified_identity_keeps_leading_zeroes_and_trims_whitespace(self):
        profile = normalize_account_profiles([{"id": "igg_5", "verified_igg_id": " 00123456 "}])[0]
        self.assertEqual(profile["verified_igg_id"], "00123456")


if __name__ == "__main__":
    unittest.main()
