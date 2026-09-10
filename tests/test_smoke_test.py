import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buzzbot_app import run_startup_smoke_test, should_run_smoke_test, validate_smoke_test_layout


class SmokeTestTests(unittest.TestCase):
    def test_startup_initializes_tk_without_creating_bot_or_changing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_bytes(b'{"images": [{"path": "template.png"}]}')
            before = config.read_bytes()
            (root / "template.png").write_bytes(b"fixture")
            with patch("buzzbot_app.tk.Tk") as tk, patch("buzzbot_app.AutoClicker") as bot:
                self.assertEqual(run_startup_smoke_test(root), 1)
                tk.return_value.withdraw.assert_called_once()
                tk.return_value.update_idletasks.assert_called_once()
                tk.return_value.destroy.assert_called_once()
                bot.assert_not_called()
            self.assertEqual(config.read_bytes(), before)
            self.assertIn("Tcl/Tk initialized", (root / "smoke-test.ok").read_text())

    def test_tk_failure_removes_stale_success_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "smoke-test.ok"
            marker.write_text("old success")
            with (
                patch("buzzbot_app.validate_smoke_test_layout", return_value=1),
                patch("buzzbot_app.tk.Tk", side_effect=RuntimeError("missing Tcl/Tk")),
                self.assertRaisesRegex(RuntimeError, "missing Tcl/Tk"),
            ):
                run_startup_smoke_test(root)
            self.assertFalse(marker.exists())

    def test_gui_update_failure_destroys_window_without_success_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch("buzzbot_app.validate_smoke_test_layout", return_value=1),
                patch("buzzbot_app.tk.Tk") as tk,
            ):
                tk.return_value.update_idletasks.side_effect = RuntimeError("GUI failure")
                with self.assertRaisesRegex(RuntimeError, "GUI failure"):
                    run_startup_smoke_test(root)
                tk.return_value.destroy.assert_called_once()
            self.assertFalse((root / "smoke-test.ok").exists())

    def test_smoke_test_flag_is_explicit(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(should_run_smoke_test(["--smoke-test"]))
            self.assertTrue(should_run_smoke_test(["--SMOKE-TEST"]))
            self.assertFalse(should_run_smoke_test(["--autostart"]))

    def test_smoke_test_can_be_enabled_by_environment(self):
        with patch.dict("os.environ", {"BUZZBOT_SMOKE_TEST": "1"}, clear=True):
            self.assertTrue(should_run_smoke_test([]))

    def test_layout_validation_checks_configured_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "img" / "task" / "template.png"
            template.parent.mkdir(parents=True)
            template.write_bytes(b"png")
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "images": [
                            {
                                "description": "Тест",
                                "path": "img/task/template.png",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            self.assertEqual(validate_smoke_test_layout(root), 1)

    def test_layout_validation_rejects_missing_template(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text(
                json.dumps({"images": [{"description": "Нет файла", "path": "missing.png"}]}),
                encoding="utf-8",
            )

            with self.assertRaises(FileNotFoundError):
                validate_smoke_test_layout(root)


if __name__ == "__main__":
    unittest.main()
