"""Conservative recovery checks independent of model scores and private images."""
from concurrent.futures import Future
import io
from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ocr_server import Recognizer, recover_small_kana


class SmallKanaTests(unittest.TestCase):
    def test_recovers_supported_insertion_and_preserves_first_pass(self):
        self.assertEqual(
            recover_small_kana('「どうや、腕節で勝てると思うか」', 'どうや、腕っ節勝てると思うか'),
            '「どうや、腕っ節で勝てると思うか」')

    def test_changed_kanji_invalidates_correspondence(self):
        original = '「どうや、腕節で勝てると思うか」'
        self.assertEqual(recover_small_kana(original, 'どうや、晩っ節で勝てると思うか'), original)

    def test_does_not_change_existing_full_size_kana(self):
        self.assertEqual(recover_small_kana('いつ頃からそう', 'いっ頃からそう'), 'いつ頃からそう')

    def test_does_not_bridge_punctuation_or_space(self):
        self.assertEqual(recover_small_kana('あ、た', 'あった'), 'あ、た')
        self.assertEqual(recover_small_kana('あ た', 'あった'), 'あ た')

    def test_does_not_insert_unanchored_kana_or_regular_letters(self):
        for candidate in ['っ腕節', '腕節っ', '腕つ節', '腕め節', '別の長い文っだ']:
            self.assertEqual(recover_small_kana('腕節', candidate), '腕節')

    def test_rejects_poor_coverage(self):
        original = 'どうや腕節で勝てると思うか'
        self.assertEqual(recover_small_kana(original, '腕っ節'), original)

    def test_keeps_already_correct_small_kana(self):
        self.assertEqual(recover_small_kana('腕っ節', '腕っ節'), '腕っ節')

    def test_does_not_duplicate_an_existing_small_kana(self):
        self.assertEqual(recover_small_kana('腕っ節', '腕っっ節'), '腕っ節')

    def test_independent_japanese_check_can_correct_a_small_counterpart(self):
        self.assertEqual(recover_small_kana('腕つ節', '腕っ節', True), '腕っ節')
        self.assertEqual(recover_small_kana('腕つ節', '腕っ節'), '腕つ節')

    def test_independent_check_still_rejects_changed_kanji(self):
        self.assertEqual(recover_small_kana('腕つ節', '晩っ節', True), '腕つ節')

    def test_small_substitution_requires_unbroken_neighbours(self):
        for original in ['つ節', '腕つ', '腕、つ節', '腕つ、節']:
            self.assertEqual(recover_small_kana(original, '腕っ節', True), original)

    def test_agreement_keeps_regular_kana_regular(self):
        self.assertEqual(recover_small_kana('いつ頃からそう', 'いつ頃からそう', True), 'いつ頃からそう')

    def test_failed_independent_engine_preserves_the_first_result(self):
        class FailedExecutor:
            def submit(self, *args):
                future = Future()
                future.set_exception(RuntimeError('unavailable checker'))
                return future

        image = io.BytesIO()
        Image.new('RGB', (100, 36), 'white').save(image, format='BMP')
        recognizer = object.__new__(Recognizer)
        recognizer.recognize_image = lambda image: ('腕節', 0.98, 0.0)
        recognizer.japanese_executor = FailedExecutor()
        result = recognizer.recognize(image.getvalue())
        self.assertEqual(result['text'], '腕節')
        self.assertTrue(result['japanese_check_failed'])
        self.assertFalse(result['small_kana_recovery'])


if __name__ == '__main__':
    unittest.main()
