import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from tools import register_wasteland_solo as registration


class FakeClient:
    def __init__(self, frame):
        self.frame = frame
        self.keyevents = []
        self.taps = []

    def screenshot_bgr(self):
        return self.frame

    def keyevent(self, value):
        self.keyevents.append(value)

    def tap(self, *args):
        self.taps.append(args)

    def clear_focused_text(self, *_args):
        pass

    def input_text(self, *_args):
        pass

    def focused_edit_text_value(self):
        return None


class WastelandRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.client = FakeClient(self.frame)

    def test_registration_phase_must_be_selected(self):
        hsv = np.zeros((720, 1280, 3), dtype=np.uint8)
        hsv[145:220, 35:300] = (20, 200, 200)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        self.assertTrue(registration._registration_phase_selected(frame))

    def test_active_event_phase_is_not_registration(self):
        hsv = np.zeros((720, 1280, 3), dtype=np.uint8)
        hsv[240:320, 35:300] = (20, 200, 200)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        self.assertFalse(registration._registration_phase_selected(frame))

    def test_team_button_uses_the_large_orange_action_area(self):
        hsv = np.zeros((720, 1280, 3), dtype=np.uint8)
        hsv[585:655, 470:810] = (20, 220, 220)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        self.assertTrue(registration._team_button_visible(frame))

    def test_live_dialog_templates_are_specific(self):
        name_dialog = cv2.imread(str(registration.TEAM_NAME_DIALOG_TEMPLATE))
        created_dialog = cv2.imread(str(registration.TEAM_CREATED_TEMPLATE))

        self.assertTrue(registration._team_name_dialog_visible(name_dialog))
        self.assertFalse(registration._team_created_visible(name_dialog))
        self.assertTrue(registration._team_created_visible(created_dialog))
        self.assertFalse(registration._team_name_dialog_visible(created_dialog))

    @patch.object(registration.time, "sleep")
    @patch.object(registration, "_team_button_visible", return_value=True)
    @patch.object(registration, "_registration_phase_selected", return_value=True)
    @patch.object(registration, "_registered_status_visible", return_value=True)
    @patch.object(registration, "_event_target", return_value=(500, 100))
    def test_alliance_registration_row_does_not_hide_create_flow(
        self,
        _event_target,
        _registered,
        _registration_phase,
        _team_button,
        _sleep,
    ):
        with tempfile.TemporaryDirectory() as directory:
            frame, state = registration._open_wasteland_registration(
                self.client,
                Path(directory),
                "Account",
            )

        self.assertIs(frame, self.frame)
        self.assertEqual(state, "create")

    @patch.object(registration.time, "sleep")
    @patch.object(
        registration,
        "_open_wasteland_registration",
        return_value=(np.zeros((720, 1280, 3), dtype=np.uint8), "registration_closed"),
    )
    def test_closed_registration_is_reported_without_taps(self, _open, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            ok, detail = registration._create_solo_team(
                self.client,
                Path(directory),
                "Account",
            )

        self.assertFalse(ok)
        self.assertEqual(detail, "registration phase is closed")

    @patch.object(registration.time, "sleep")
    @patch.object(registration, "_team_name_dialog_visible", return_value=False)
    @patch.object(registration, "_capture")
    @patch.object(registration, "_open_wasteland_registration")
    def test_create_requires_name_dialog(self, open_registration, capture, _visible, _sleep):
        open_registration.return_value = (self.frame, "create")
        capture.return_value = self.frame

        with tempfile.TemporaryDirectory() as directory:
            ok, detail = registration._create_solo_team(
                self.client,
                Path(directory),
                "Account",
            )

        self.assertFalse(ok)
        self.assertEqual(detail, "team name dialog was not confirmed")
        self.assertEqual(self.client.taps[0], (640, 617))

    @patch.object(registration.time, "sleep")
    @patch.object(registration, "_team_created_visible", return_value=False)
    @patch.object(registration, "_team_name_dialog_visible", return_value=True)
    @patch.object(registration, "_capture")
    @patch.object(registration, "_open_wasteland_registration")
    def test_create_requires_specific_success_dialog(
        self,
        open_registration,
        capture,
        _name_visible,
        _created_visible,
        _sleep,
    ):
        open_registration.return_value = (self.frame, "create")
        capture.return_value = self.frame

        with tempfile.TemporaryDirectory() as directory:
            ok, detail = registration._create_solo_team(
                self.client,
                Path(directory),
                "Account",
            )

        self.assertFalse(ok)
        self.assertEqual(detail, "solo team creation was not confirmed")


if __name__ == "__main__":
    unittest.main()
