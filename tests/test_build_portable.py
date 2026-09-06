import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import build_portable


class PortableBuildTests(unittest.TestCase):
    def test_portable_brand_and_windowed_executable_are_stable(self):
        spec = build_portable.build_spec_text()
        self.assertEqual(build_portable.APP_NAME, "BuZzbot")
        self.assertEqual(build_portable.BUNDLE_NAME, "BuZzbotPortable")
        self.assertIn("['buzzbot_app.py']", spec)
        self.assertIn("name='BuZzbot'", spec)
        self.assertIn("console=False", spec)
        self.assertIn('"buzzbot/assets"', spec)
        self.assertIn("a.binaries", spec)
        self.assertIn("a.datas", spec)
        self.assertNotIn("COLLECT(", spec)
        self.assertNotIn("exclude_binaries=True", spec)

    def test_merchant_runtime_assets_are_present_in_bundled_asset_tree(self):
        merchant_dir = build_portable.ASSET_DIR / "merchant"
        required = {
            "merchant_arrival_marker.jpg",
            "merchant_catalog_selection_marker.jpg",
            "merchant_shop_building.jpg",
            "merchant_shop_sign.jpg",
        }

        self.assertTrue(
            required <= {path.name for path in merchant_dir.glob("*.jpg")}
        )
        for name in required:
            self.assertGreater((merchant_dir / name).stat().st_size, 0)
        self.assertIn(
            'datas.append((str(asset_dir), "buzzbot/assets"))',
            build_portable.build_spec_text(),
        )

    def test_stage_executable_places_one_file_binary_in_portable_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage_root = Path(tmp)
            stage_dir = stage_root / "BuZzbotPortable"
            (stage_root / "BuZzbot.exe").write_bytes(b"exe")

            with (
                patch.object(build_portable, "STAGE_ROOT", stage_root),
                patch.object(build_portable, "STAGE_DIR", stage_dir),
            ):
                build_portable.stage_executable()

            self.assertTrue((stage_dir / "BuZzbot.exe").is_file())
            self.assertFalse((stage_root / "BuZzbot.exe").is_file())

    def test_stage_templates_places_png_next_to_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source_img"
            stage = root / "stage"
            (source / "heal").mkdir(parents=True)
            (source / "heal" / "template.png").write_bytes(b"png")

            with (
                patch.object(build_portable, "IMG_DIR", source),
                patch.object(build_portable, "STAGE_DIR", stage),
            ):
                build_portable.stage_templates()

            self.assertTrue((stage / "img" / "heal" / "template.png").is_file())

    def test_validate_portable_layout_rejects_missing_configured_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / "img").mkdir()
            (stage / "img" / "present.png").write_bytes(b"png")
            (stage / "BuZzbot.exe").write_bytes(b"exe")
            (stage / "config.json").write_text(
                json.dumps(
                    {
                        "images": [
                            {
                                "description": "Missing template",
                                "path": "img/missing.png",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(build_portable, "STAGE_DIR", stage):
                with self.assertRaisesRegex(RuntimeError, "Missing template"):
                    build_portable.validate_portable_layout()

    def test_validate_portable_layout_accepts_complete_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / "img" / "heal").mkdir(parents=True)
            (stage / "img" / "heal" / "template.png").write_bytes(b"png")
            (stage / "BuZzbot.exe").write_bytes(b"exe")
            (stage / "config.json").write_text(
                json.dumps(
                    {
                        "images": [
                            {
                                "description": "Heal",
                                "path": "img/heal/template.png",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(build_portable, "STAGE_DIR", stage):
                build_portable.validate_portable_layout()

    def test_smoke_test_requires_marker_from_frozen_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            executable = stage / "BuZzbot.exe"
            executable.write_bytes(b"exe")

            def create_marker(*_args, **_kwargs):
                (stage / "smoke-test.ok").write_text("ok", encoding="utf-8")
                return Mock(returncode=0)

            with (
                patch.object(build_portable, "STAGE_DIR", stage),
                patch.object(build_portable.subprocess, "run", side_effect=create_marker) as run,
            ):
                build_portable.run_portable_smoke_test()

            run.assert_called_once()
            self.assertFalse((stage / "smoke-test.ok").exists())


if __name__ == "__main__":
    unittest.main()
