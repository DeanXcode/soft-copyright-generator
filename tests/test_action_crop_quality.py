from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw

from backend.softcopyright.screenshots import (
    _action_crop_has_visible_content,
    _is_action_crop_label,
    _normalize_action_crop_image,
)


class ActionCropQualityTests(unittest.TestCase):
    def test_status_and_table_header_labels_are_not_actions(self):
        for label in ("操作", "待评估", "有冲突", "已适配", "已启用"):
            self.assertFalse(_is_action_crop_label(label))
        for label in ("保存", "发布", "复核", "核验门店核销", "登录系统", "查看详情"):
            self.assertTrue(_is_action_crop_label(label))

    def test_blank_outline_crop_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blank.png"
            image = Image.new("RGB", (96, 34), "white")
            ImageDraw.Draw(image).rectangle((0, 0, 95, 33), outline="#d5dde6", width=1)
            image.save(path)

            self.assertFalse(_action_crop_has_visible_content(path))

    def test_button_with_visible_label_pixels_passes(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "save.png"
            image = Image.new("RGB", (96, 34), "#ea580c")
            draw = ImageDraw.Draw(image)
            for left in (30, 40, 50, 60):
                draw.rectangle((left, 10, left + 5, 24), fill="white")
            image.save(path)

            self.assertTrue(_action_crop_has_visible_content(path))

    def test_action_crop_is_normalized_to_shared_canvas_height(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "query.png"
            image = Image.new("RGB", (84, 26), "#2563eb")
            ImageDraw.Draw(image).rectangle((24, 8, 58, 18), fill="white")
            image.save(path)

            _normalize_action_crop_image(path)

            with Image.open(path) as normalized:
                self.assertEqual(normalized.height, 40)
                self.assertGreater(normalized.width, 84)
                self.assertEqual(normalized.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
