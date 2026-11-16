import io
import unittest

from PIL import Image, ImageDraw

from backend.softcopyright.llm.provider import (
    GeneratedImageQualityError,
    _image_failure_message,
    _image_size_for_attempt,
    _inspect_generated_image,
)


def _png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class ImageQualityGateTests(unittest.TestCase):
    def test_image_retry_keeps_the_configured_size(self):
        self.assertEqual(_image_size_for_attempt("1280x720", 1), "1280x720")
        self.assertEqual(_image_size_for_attempt("1280x720", 2), "1280x720")
        self.assertEqual(_image_size_for_attempt("1280x720", 4), "1280x720")
        self.assertEqual(_image_size_for_attempt("invalid", 2), "1024x1024")

    def test_image_failure_prefers_transient_upstream_history(self):
        class Response:
            status_code = 400

        error = RuntimeError("bad request")
        error.response = Response()
        message = _image_failure_message(
            error,
            model="gpt-image-2",
            attempts=3,
            error_history=[
                {"status_code": 502},
                {"status_code": 502},
                {"status_code": 400},
            ],
        )

        self.assertIn("上游服务临时不可用", message)
        self.assertIn("502 → 502 → 400", message)
        self.assertNotIn("API Key", message)

    def test_image_failure_reports_mixed_quality_and_http_failures_accurately(self):
        error = GeneratedImageQualityError("图片缺少软件界面控件边界")
        message = _image_failure_message(
            error,
            model="gpt-image-2",
            attempts=4,
            error_history=[
                {"status_code": None, "error_type": "GeneratedImageQualityError"},
                {"status_code": None, "error_type": "GeneratedImageQualityError"},
                {"status_code": 502, "error_type": "HTTPError"},
                {"status_code": None, "error_type": "GeneratedImageQualityError"},
            ],
        )

        self.assertIn("3 次返回图片但未通过本地质量校验", message)
        self.assertIn("1 次返回 HTTP 502", message)
        self.assertIn("不会重复请求 image2", message)
        self.assertNotIn("上游服务临时不可用", message)
        self.assertNotIn("BASE_URL", message)

    def test_dense_dark_dashboard_passes_without_long_axis_edges(self):
        image = Image.new("RGB", (1280, 720), "#071b2a")
        draw = ImageDraw.Draw(image)
        colors = [(red, green, blue) for red in (40, 100, 160, 220) for green in (40, 120, 200) for blue in (40, 140)]
        draw.rectangle((0, 0, 170, 720), fill="#0b2638")
        draw.rectangle((8, 8, 36, 36), fill=(220, 120, 40))
        draw.rectangle((1244, 684, 1272, 712), fill=(40, 200, 140))
        for row in range(6):
            for column in range(7):
                left = 190 + column * 145
                top = 35 + row * 105
                draw.rounded_rectangle((left, top, left + 125, top + 82), radius=8, fill=colors[(row + column) % len(colors)])
                draw.rectangle((left + 10, top + 14, left + 102, top + 20), fill="#d8e8ef")
                draw.rectangle((left + 10, top + 34, left + 74, top + 40), fill="#9bb9c7")
                draw.rectangle((left + 10, top + 54, left + 112, top + 61), fill="#7fa5b6")
        result = _inspect_generated_image(_png_bytes(image))
        self.assertTrue(result["image_quality"]["dense_dark_ui_soft_pass"])

    def test_light_mobile_list_ui_passes_with_subtle_card_edges(self):
        image = Image.new("RGB", (720, 1280), "#f7f8fb")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 720, 104), fill="#ffffff")
        draw.rectangle((24, 118, 696, 270), fill="#ffffff", outline="#e2e6ed", width=2)
        for column, color in enumerate(("#3888ee", "#38c98b", "#ff9f32", "#ff626d")):
            left = 28 + column * 170
            draw.rounded_rectangle((left, 132, left + 150, 250), radius=12, fill="#ffffff", outline="#e2e6ed", width=2)
            draw.ellipse((left + 108, 148, left + 136, 176), fill=color)
            draw.rectangle((left + 14, 154, left + 82, 165), fill="#667085")
            draw.rectangle((left + 14, 188, left + 42, 218), fill="#101828")
        for row in range(6):
            top = 292 + row * 145
            draw.rounded_rectangle((24, top, 696, top + 126), radius=12, fill="#ffffff", outline="#e2e6ed", width=2)
            draw.rounded_rectangle((42, top + 24, 100, top + 102), radius=8, fill=(60 + row * 20, 100, 220 - row * 15))
            draw.rectangle((122, top + 24, 440, top + 39), fill="#202735")
            draw.rectangle((122, top + 54, 360, top + 64), fill="#8a94a6")
            draw.rectangle((122, top + 82, 540, top + 88), fill="#3478ef")
            draw.rectangle((622, top + 50, 662, top + 84), fill="#eef3fb", outline="#dfe5ee")
        draw.rectangle((0, 1188, 720, 1280), fill="#ffffff", outline="#e2e6ed")

        result = _inspect_generated_image(_png_bytes(image))

        self.assertGreaterEqual(result["image_quality"]["axis_edge_score"], 8)

    def test_flat_dark_placeholder_is_rejected(self):
        image = Image.new("RGB", (1280, 720), "#071b2a")
        draw = ImageDraw.Draw(image)
        draw.ellipse((570, 290, 710, 430), fill="#0d2939")
        with self.assertRaises(GeneratedImageQualityError):
            _inspect_generated_image(_png_bytes(image))


if __name__ == "__main__":
    unittest.main()
