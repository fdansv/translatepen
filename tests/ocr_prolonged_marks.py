"""Second-engine vowel-mark recovery without changing first-pass wording."""
from concurrent.futures import Future
import io
from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ocr_server import Recognizer, recover_prolonged_marks, prolonged_mark_steps


class ProlongedMarkTests(unittest.TestCase):
    def evidence(self, ink=True, stroke_height=4, probability=.01, competitor=0, previous='カ'):
        image = Image.new('RGB', (60, 36), 'white')
        if ink:
            ImageDraw.Draw(image).rectangle((24, 20, 38, 19 + stroke_height), fill='black')
        characters = ['', previous, 'レ', 'ー', '一']
        output = np.zeros((10, len(characters)), dtype=np.float32)
        output[:, 0] = 1
        output[2, 0] = output[8, 0] = 0
        output[2, 1] = output[8, 2] = 1
        output[5, 3], output[5, 4] = probability, competitor
        return prolonged_mark_steps(output, characters, image, 80)

    def test_model_and_visible_dash_both_required(self):
        self.assertEqual(self.evidence(), {5})
        self.assertEqual(self.evidence(ink=False), set())
        self.assertEqual(self.evidence(probability=.0005), set())

    def test_rejects_competing_kanji_and_wrong_geometry(self):
        self.assertEqual(self.evidence(competitor=.03), set())
        self.assertEqual(self.evidence(stroke_height=12), set())
        self.assertEqual(self.evidence(previous='身'), set())

    def test_reported_words_and_sentence(self):
        for old, candidate in [('ルムランナ', 'ルームランナー'), ('カレ', 'カレー'),
                               ('それは、ケジというのだろう', 'それは、ケージというのだろう')]:
            self.assertEqual(recover_prolonged_marks(old, candidate), candidate)

    def test_distant_disagreement_never_changes_other_text(self):
        self.assertEqual(recover_prolonged_marks('友人にカレを持っていってあば',
                                                '友人にカレーを持っていってあげ'),
                         '友人にカレーを持っていってあば')

    def test_changed_neighbours_are_not_repaired(self):
        for old, candidate in [('カレを食べる', 'カレーが食べる'), ('ケジとは', 'ゲージとは'),
                               ('あカレを食べる', 'あカレーを飲める')]:
            self.assertEqual(recover_prolonged_marks(old, candidate), old)

    def test_no_regular_letters_or_kanji_are_substituted(self):
        for old, candidate in [('身を貸してる', '身を窶してる'), ('ルムランナ', 'ルールランナー'),
                               ('コヒ', 'コーヒーがほしい')]:
            self.assertEqual(recover_prolonged_marks(old, candidate), old)

    def test_punctuation_gaps_and_duplicate_marks_are_preserved(self):
        for old, candidate in [('カレ を食べる', 'カレーを食べる'), ('カレー', 'カレーー'),
                               ('ーカレ', 'ーーカレ'), ('カレ、を食べる', 'カレーを食べる')]:
            self.assertEqual(recover_prolonged_marks(old, candidate), old)

    def test_already_correct_words_are_unchanged(self):
        self.assertEqual(recover_prolonged_marks('カレーを食べる', 'カレーを食べる'), 'カレーを食べる')

    def test_pipeline_uses_existing_second_engine(self):
        class Completed:
            def submit(self, *args):
                future = Future()
                future.set_result(('それはケージという', 10))
                return future
        image = io.BytesIO()
        Image.new('RGB', (200, 36), 'white').save(image, format='BMP')
        recognizer = object.__new__(Recognizer)
        recognizer.recognize_image = lambda image: ('それはケジという', .98, 0.)
        recognizer.japanese_executor = Completed()
        result = recognizer.recognize(image.getvalue())
        self.assertEqual(result['text'], 'それはケージという')
        self.assertTrue(result['prolonged_mark_recovery'])


if __name__ == '__main__':
    unittest.main()
