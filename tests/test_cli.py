import unittest

from buzzbot_app import (
    should_autostart_fence_only,
    should_autostart_login_only,
    should_autostart_routines,
    should_start_fresh_pass,
)


class CommandLineTests(unittest.TestCase):
    def test_autostart_flag_is_case_insensitive(self):
        self.assertTrue(should_autostart_routines(["--AUTOSTART"]))

    def test_other_arguments_do_not_enable_autostart(self):
        self.assertFalse(should_autostart_routines(["--portable"]))

    def test_fresh_pass_flag_is_explicit(self):
        self.assertTrue(should_start_fresh_pass(["--FRESH-PASS"]))
        self.assertFalse(should_start_fresh_pass(["--autostart"]))

    def test_login_only_flag_is_explicit(self):
        self.assertTrue(should_autostart_login_only(["--LOGIN-ONLY"]))
        self.assertFalse(should_autostart_login_only(["--autostart"]))

    def test_fence_only_flag_is_explicit(self):
        self.assertTrue(should_autostart_fence_only(["--FENCE-ONLY"]))
        self.assertFalse(should_autostart_fence_only(["--autostart"]))


if __name__ == "__main__":
    unittest.main()
