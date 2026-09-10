from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from buzzbot import alliance_gifts


class GiftTemplatePathTests(unittest.TestCase):
    def test_gift_template_can_be_read_from_cyrillic_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Шаблоны"
            root.mkdir()
            expected = np.arange(100, dtype=np.uint8).reshape(10, 10)
            success, encoded = cv2.imencode(".png", expected)
            self.assertTrue(success)
            (root / "claim.png").write_bytes(encoded.tobytes())
            alliance_gifts._template.cache_clear()
            try:
                with patch.object(alliance_gifts, "ASSET_DIR", root):
                    actual = alliance_gifts._template("claim")
                np.testing.assert_array_equal(actual, expected)
            finally:
                alliance_gifts._template.cache_clear()


if __name__ == "__main__":
    unittest.main()
