import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buzzbot_app import should_run_smoke_test, validate_smoke_test_layout


class SmokeTestTests(unittest.TestCase):
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
