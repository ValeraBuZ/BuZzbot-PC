import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools import register_wasteland_solo as registration


class FakeClient:
    def __init__(self, frame):
        self.frame = frame
        self.keyevents = []

    def screenshot_bgr(self):
        return self.frame

    def keyevent(self, value):
        self.keyevents.append(value)

    def tap(self, *_args):
        pass

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

    @patch.object(registration.time, "sleep")
    @patch.object(
        registration,
        "_open_wasteland_registration",
        return_value=(np.zeros((720, 1280, 3), dtype=np.uint8), "registered_unverified"),
    )
    def test_alliance_registration_status_is_not_account_proof(self, _open, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            ok, detail = registration._create_solo_team(
                self.client,
                Path(directory),
                "Account",
            )

        self.assertFalse(ok)
        self.assertIn("unverified", detail)

    @patch.object(registration.time, "sleep")
    @patch.object(registration, "_registered_status_visible", return_value=False)
    @patch.object(registration, "_capture")
    @patch.object(registration, "_open_wasteland_registration")
    def test_create_requires_visible_confirmation(self, open_registration, capture, _visible, _sleep):
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
