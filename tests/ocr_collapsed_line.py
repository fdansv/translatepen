"""Guard against Japanese-engine hallucinations while recovering lost text."""
from concurrent.futures import Future
import io
from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ocr_server import Recognizer, recover_collapsed_line


class CollapsedLineTests(unittest.TestCase):
    def test_recovers_anchored_short_line(self):
        self.assertEqual(recover_collapsed_line('脳し後', '。脳震盪を起こした後', 185, 36),
                         '。脳震盪を起こした後')

    def test_preserves_complete_main_result(self):
        text = '脳震を起こした後'
        self.assertEqual(recover_collapsed_line(text, '。脳震盪を起こした後', 185, 36), text)

    def test_changed_kanji_or_order_cannot_override_main_result(self):
        for candidate in ['。悩震盪を起こした後', '。脳震盪を起こした日', '脳震盪後を起こした']:
            self.assertEqual(recover_collapsed_line('脳し後', candidate, 185, 36), '脳し後')

    def test_internal_anchor_must_agree(self):
        self.assertEqual(recover_collapsed_line('脳し後', '脳震盪を起こす予定の後', 185, 36), '脳し後')

    def test_rejects_unanchored_or_kana_only_fragments(self):
        for original in ['', '後', 'した', '脳し']:
            self.assertEqual(recover_collapsed_line(original, '。脳震盪を起こした後', 185, 36), original)

    def test_rejects_extra_beginning_or_end(self):
        for candidate in ['彼が脳震盪を起こした後', '脳震盪を起こした後だ']:
            self.assertEqual(recover_collapsed_line('脳し後', candidate, 185, 36), '脳し後')

    def test_rejects_oversized_or_small_gain_candidate(self):
        for candidate in ['脳震し後', '脳' + '震盪を起こした' * 5 + '後']:
            self.assertEqual(recover_collapsed_line('脳し後', candidate, 185, 36), '脳し後')

    def test_rejects_long_column_model_output(self):
        self.assertEqual(recover_collapsed_line('脳し後', '。脳震盪を起こした後', 400, 36), '脳し後')

    def test_recovers_kanji_from_weak_short_physical_scans(self):
        for original, candidate, width, confidence in [
                ('脳り震こ', '脳震盪を起こ', 113, 0.6483),
                ('脳震', '脳震盪を', 101, 0.7396),
                ('脳震起こ', '脳震盪を起こ', 105, 0.5858)]:
            self.assertEqual(recover_collapsed_line(original, candidate, width, 36, confidence), candidate)

    def test_weak_result_still_rejects_kanji_changes_or_reordering(self):
        for candidate in ['悩震盪を起こ', '震脳盪を起こ', '脳震盪を見た']:
            self.assertEqual(recover_collapsed_line('脳震起こ', candidate, 105, 36, 0.58), '脳震起こ')

    def test_confident_or_small_gain_result_cannot_use_weak_fallback(self):
        self.assertEqual(recover_collapsed_line('脳り震こ', '脳震盪を起こ', 113, 36, 0.86), '脳り震こ')
        self.assertEqual(recover_collapsed_line('脳震を起こ', '脳震盪を起こ', 113, 36, 0.7), '脳震を起こ')

    def test_weak_fallback_requires_additional_kanji(self):
        self.assertEqual(recover_collapsed_line('脳震', '脳震はどうした', 113, 36, 0.7), '脳震')

    def test_pipeline_uses_fallback_after_primary_retries_fail(self):
        class CompletedExecutor:
            def submit(self, *args):
                future = Future()
                future.set_result(('。脳震盪を起こした後', 300.0))
                return future

        image = io.BytesIO()
        Image.new('RGB', (185, 36), 'white').save(image, format='BMP')
        recognizer = object.__new__(Recognizer)
        recognizer.recognize_image = lambda image: ('脳し後', 0.86, 0.0)
        recognizer.japanese_executor = CompletedExecutor()
        result = recognizer.recognize(image.getvalue())
        self.assertEqual(result['text'], '。脳震盪を起こした後')
        self.assertTrue(result['japanese_line_recovery'])
        self.assertFalse(result['small_kana_recovery'])


if __name__ == '__main__':
    unittest.main()
