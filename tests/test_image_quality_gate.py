import io
import unittest

from PIL import Image, ImageDraw

from backend.softcopyright.llm.provider import GeneratedImageQualityError, _inspect_generated_image


def _png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class ImageQualityGateTests(unittest.TestCase):
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

    def test_flat_dark_placeholder_is_rejected(self):
        image = Image.new("RGB", (1280, 720), "#071b2a")
        draw = ImageDraw.Draw(image)
        draw.ellipse((570, 290, 710, 430), fill="#0d2939")
        with self.assertRaises(GeneratedImageQualityError):
            _inspect_generated_image(_png_bytes(image))


if __name__ == "__main__":
    unittest.main()
