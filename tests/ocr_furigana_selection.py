"""Exercise crop selection and the clear-scan fast path without loading a model."""
import io
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ocr_server import Recognizer


class CropSelectionTests(unittest.TestCase):
    def recognize(self, outputs):
        # Both edges are sparse; the blank bottom margin is slightly sparser
        # than the small readings above the main line, as in the failed scan.
        pixels = np.full((36, 100, 3), 255, dtype=np.uint8)
        for y in range(36):
            pixels[y, 0] = y  # Identifies the crop without mocking PIL.
        pixels[11:28, 3::2] = 0
        pixels[2:7, 10:61:5] = 0
        image = io.BytesIO()
        Image.fromarray(pixels).save(image, format="BMP")
        recognizer = object.__new__(Recognizer)
        calls = []

        def inference(crop):
            top = crop.getpixel((0, 0))[0]
            bounds = (top, top + crop.height)
            calls.append(bounds)
            text, confidence = outputs[bounds]
            return text, confidence, 0.0

        recognizer.recognize_image = inference
        return recognizer.recognize(image.getvalue()), calls

    def test_quiet_margin_failure_falls_back_and_preserves_characters(self):
        result, calls = self.recognize({
            (0, 36): ("bad", 0.5),
            (0, 31): ("still bad", 0.7),
            (0, 27): ("still bad", 0.7),
            (5, 36): ("main text with preserved glyph", 0.9),
            (9, 36): ("main text with missing glyph", 0.96),
        })
        self.assertEqual(result["text"], "main text with preserved glyph")
        self.assertTrue(result["ruby_filter"])
        self.assertEqual(len(calls), 5)

    def test_clear_scan_runs_only_one_inference(self):
        result, calls = self.recognize({(0, 36): ("a complete clear sentence", 0.94)})
        self.assertEqual(calls, [(0, 36)])
        self.assertFalse(result["ruby_filter"])

    def test_weak_crops_do_not_replace_original(self):
        result, _ = self.recognize({
            (0, 36): ("original", 0.65),
            (0, 31): ("longer but unreliable crop", 0.74),
            (0, 27): ("longer but unreliable crop", 0.80),
            (5, 36): ("longer but unreliable crop", 0.79),
            (9, 36): ("longer but unreliable crop", 0.81),
        })
        self.assertEqual(result["text"], "original")
        self.assertFalse(result["ruby_filter"])


if __name__ == "__main__":
    unittest.main()
