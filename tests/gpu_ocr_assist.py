"""Correction/fallback checks for the isolated GPU assist; no real GPU needed."""
from concurrent.futures import Future
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from gpu_ocr_assist import (AssistedRecognizer, GPUClient, Lexicon, TrialCaptures,
                           collapsed_line_evidence, select_collapsed_recovery, select_insertions,
                           short_compound_evidence, select_short_compound)


class InsertionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lexicon = Lexicon(ROOT / 'build/dictionary.sqlite', ROOT / 'vendor/deinflect.json')

    @classmethod
    def tearDownClass(cls):
        cls.lexicon.close()

    def choice(self, original, candidate):
        return select_insertions(original, candidate, self.lexicon)

    def test_inflected_word_support_with_literal_punctuation(self):
        result = self.choice('「彼は街を見つている。」', '彼は街を見つめている')
        self.assertEqual(result.text, '「彼は街を見つめている。」')
        self.assertEqual(result.edits[0]['evidence']['lemma'], '見つめる')

    def test_independent_compound_with_existing_anchors(self):
        result = self.choice('私は保士として働いています。', '私は保育士として働いています。')
        self.assertEqual(result.text, '私は保育士として働いています。')

    def test_noun_completion_before_particle(self):
        result = self.choice('彼は新幹に乗って東京へ行った。', '彼は新幹線に乗って東京へ行った。')
        self.assertEqual(result.text, '彼は新幹線に乗って東京へ行った。')

    def test_short_sentence_with_enough_local_anchors(self):
        self.assertEqual(self.choice('新幹に乗った', '新幹線に乗った').text, '新幹線に乗った')

    def test_distant_suffix_ambiguity_does_not_block_unique_interior_gap(self):
        original = '彼は新幹に乗って東京へ行った。'
        result = self.choice(original, '彼は新幹線に乗って東京へ行ったた。')
        self.assertEqual(result.text, '彼は新幹線に乗って東京へ行った。')
        self.assertEqual(len(result.edits), 1)

    def test_ambiguity_within_insertion_anchors_still_abstains(self):
        original = '彼は新幹に乗って東京へ行った。'
        self.assertEqual(self.choice(original, '彼は新新幹線に乗って東京へ行った。').text,
                         original)

    def test_punctuation_changes_alone_do_not_change_output(self):
        original = '「どうや、腕っ節で勝てると思うか'
        self.assertEqual(self.choice(original, 'どうや腕っ節で勝てると思うか」').text, original)

    def test_substitutions_and_deletions_cannot_override_original(self):
        for original,candidate in [
                ('二時過ぎのことだ。突然、強くドアがノックされた。',
                 'ニ時過ぎのことだ。突然、強くドアがノックされた。'),
                ('私は保育士として働いています。', '私は保育士として働いていま。')]:
            self.assertEqual(self.choice(original,candidate).text, original)

    def test_does_not_complete_boundary_even_when_a_word_is_known(self):
        original = '昨日から私は東京に住んでいます。'
        self.assertEqual(self.choice(original, original+'友達').text, original)
        self.assertEqual(self.choice(original, '友達'+original).text, original)
        self.assertEqual(self.choice('新幹', '新幹線').text, '新幹')

    def test_does_not_replace_an_existing_valid_word(self):
        original = '私は心理を学んでいます。'
        self.assertEqual(self.choice(original, '私は心理学を学んでいます。').text, original)

    def test_furigana_intrusion_beside_kanji_is_rejected(self):
        original = '昨日は東京で友達に会いました。'
        self.assertEqual(self.choice(original, '昨日は東京とうで友達に会いました。').text, original)
        self.assertEqual(self.choice(original, '昨日は東京とで友達に会いました。').text, original)

    def test_unknown_kana_expansion_is_not_word_support(self):
        original = '私はこのままここにいる。'
        self.assertEqual(self.choice(original, '私はこのままここにきいる。').text, original)

    def test_repeated_character_alignment_is_ambiguous(self):
        original = 'その窓から見える景色は美しい。'
        self.assertEqual(self.choice(original, 'その窓から見ええる景色は美しい。').text, original)

    def test_punctuation_boundary_is_not_bridged(self):
        original = '「街を見つ、ている。」'
        self.assertEqual(self.choice(original, '街を見つめている').text, original)

    def test_mixed_script_and_empty_results_abstain(self):
        for original,candidate in [('東京で3日間過ごした。','東京で3日間も過ごした。'),
                                   ('街を見つている。',''), ('','街を見つめている。')]:
            self.assertEqual(self.choice(original,candidate).text, original)

    def collapse(self, original='「ら保育園く。」', candidate='保育士として幼稚園で働く',
                 width=432, confidence=0.6):
        return collapsed_line_evidence(original, candidate, width, 36, confidence, self.lexicon)

    def test_collapse_requires_kanji_agreement_and_a_distinct_shorter_view(self):
        original, candidate = '「ら保育園く。」', '保育士として幼稚園で働く'
        evidence = self.collapse(original, candidate)
        self.assertIsNotNone(evidence)
        result = select_collapsed_recovery(original, candidate, '保育士として幼稚園', evidence)
        self.assertEqual(result.text, '「保育士として幼稚園で働く。」')
        for confirmation in ['保育士', candidate, '保育士として小学校']:
            self.assertEqual(select_collapsed_recovery(original, candidate, confirmation,
                                                       evidence).text, original)

    def test_collapse_does_not_override_complete_or_conflicting_results(self):
        self.assertIsNone(self.collapse('保育士として幼稚園で働く'))
        self.assertIsNone(self.collapse('ら保育小く'))
        self.assertIsNone(self.collapse('ら保育く'))  # only two kanji
        self.assertIsNone(self.collapse('ら保育園く', confidence=0.9))
        self.assertIsNone(self.collapse('ら保、育園く'))
        self.assertIsNone(self.collapse('ら保育園く', width=720))
        self.assertIsNone(self.collapse('ら保育園た'))  # last anchor disagrees

    def short_word(self, original='新幹帰', candidate='新幹線で帰宅する'):
        return short_compound_evidence(original, candidate, 216, 36, self.lexicon)

    def test_short_compound_confirmation_repairs_only_one_kanji(self):
        evidence = self.short_word()
        self.assertIsNotNone(evidence)
        result = select_short_compound('新幹帰', '新幹線で帰宅する', '新幹線で帰宅', evidence)
        self.assertEqual(result.text, '新幹線帰')
        self.assertEqual(len(result.edits), 1)
        for check in ['新幹線', '新幹線と帰宅', '新幹線で帰宅する']:
            self.assertEqual(select_short_compound('新幹帰', '新幹線で帰宅する',
                                                   check, evidence).text, '新幹帰')

    def test_short_compound_does_not_override_known_word_or_conflicting_kanji(self):
        for original,candidate in [('東京行', '東京都へ行く'),
                                   ('新幹寄', '新幹線で帰宅する'),
                                   ('新幹', '新幹線で帰宅する'),
                                   ('新幹、帰', '新幹線で帰宅する'),
                                   ('新幹京', '新幹線に乗って東京へ行く')]:
            self.assertIsNone(self.short_word(original, candidate))


class FallbackTests(unittest.TestCase):
    def baseline(self):
        class Baseline:
            model_name='original'
            def recognize(self,data):
                return dict(text='「彼は街を見つている。」',server_ms=0.1,confidence=0.99)
            def close(self):
                pass
        return Baseline()

    def run_with(self, client):
        lexicon=Lexicon(ROOT/'build/dictionary.sqlite',ROOT/'vendor/deinflect.json')
        recognizer=AssistedRecognizer(self.baseline(),client,lexicon)
        try:
            return recognizer.recognize(b'fake-image')
        finally:
            recognizer.close()

    def test_network_failure_keeps_original(self):
        class Client:
            timeout=1
            def recognize(self,data):
                raise ConnectionRefusedError('model not running')
        result=self.run_with(Client())
        self.assertEqual(result['text'],'「彼は街を見つている。」')
        self.assertEqual(result['gpu_check_error'],'ConnectionRefusedError')

    def test_late_completed_result_is_not_applied(self):
        class Client:
            timeout=0.01
            def recognize(self,data):
                return dict(text='彼は街を見つめている',elapsed_ms=20)
        result=self.run_with(Client())
        self.assertEqual(result['text'],'「彼は街を見つている。」')
        self.assertEqual(result['gpu_check_error'],'TimeoutError')

    def test_queued_request_expires_without_waiting_for_gpu(self):
        class Client:
            timeout=0.01
            def recognize(self,data):
                raise AssertionError('executor stub owns this test')
        class PendingExecutor:
            def __init__(self):self.future=Future()
            def submit(self,*args):return self.future
            def shutdown(self,**kwargs):pass
        lexicon=Lexicon(ROOT/'build/dictionary.sqlite',ROOT/'vendor/deinflect.json')
        recognizer=AssistedRecognizer(self.baseline(),Client(),lexicon)
        recognizer.executor.shutdown()
        executor=PendingExecutor()
        recognizer.executor=executor
        try:
            result=recognizer.recognize(b'fake-image')
            self.assertEqual(result['text'],'「彼は街を見つている。」')
            self.assertEqual(result['gpu_check_error'],'TimeoutError')
            self.assertTrue(executor.future.cancelled())
        finally:
            recognizer.close()

    def test_second_view_failure_keeps_collapsed_original(self):
        class Baseline:
            model_name = 'original'
            def recognize(self, data):
                return dict(text='ら保育園く', server_ms=0.1, confidence=0.6)
            def close(self):
                pass
        class Client:
            timeout = 1
            calls = 0
            def recognize(self, data):
                self.calls += 1
                if self.calls == 2:
                    raise ConnectionRefusedError('second view failed')
                return dict(text='保育士として幼稚園で働く', elapsed_ms=1)
        stream = io.BytesIO()
        Image.new('RGB', (432, 36), 'white').save(stream, format='BMP')
        lexicon = Lexicon(ROOT/'build/dictionary.sqlite', ROOT/'vendor/deinflect.json')
        recognizer = AssistedRecognizer(Baseline(), Client(), lexicon)
        try:
            result = recognizer.recognize(stream.getvalue())
            self.assertEqual(result['text'], 'ら保育園く')
            self.assertEqual(result['gpu_confirmation_error'], 'ConnectionRefusedError')
        finally:
            recognizer.close()

    def test_second_view_cannot_extend_the_overall_deadline(self):
        class Baseline:
            model_name = 'original'
            def recognize(self, data):
                return dict(text='ら保育園く', server_ms=0.1, confidence=0.6)
            def close(self):
                pass
        class Client:
            timeout = 1
            calls = 0
            def recognize(self, data):
                self.calls += 1
                return dict(text='保育士として幼稚園で働く' if self.calls == 1 else
                            '保育士として幼稚園', elapsed_ms=1)
        stream = io.BytesIO()
        Image.new('RGB', (432, 36), 'white').save(stream, format='BMP')
        lexicon = Lexicon(ROOT/'build/dictionary.sqlite', ROOT/'vendor/deinflect.json')
        recognizer = AssistedRecognizer(Baseline(), Client(), lexicon)
        try:
            with patch('gpu_ocr_assist.time.perf_counter',
                       side_effect=[0, .001, .002, .003, .004, 1.001, 1.002]):
                result = recognizer.recognize(stream.getvalue())
            self.assertEqual(result['text'], 'ら保育園く')
            self.assertEqual(result['gpu_confirmation_error'], 'TimeoutError')
        finally:
            recognizer.close()


class ClientTests(unittest.TestCase):
    def image(self):
        stream=io.BytesIO()
        Image.new('RGB',(100,36),'white').save(stream,format='BMP')
        return stream.getvalue()

    def response(self, text='文字', reason='stop'):
        return io.BytesIO(json.dumps(dict(choices=[dict(finish_reason=reason,
                      message=dict(content=text))])).encode())

    def test_native_strip_is_rotated_and_deterministic_request_is_uncached(self):
        client=GPUClient()
        with patch('gpu_ocr_assist.urllib.request.urlopen',return_value=self.response()) as request:
            result=client.recognize(self.image())
        payload=json.loads(request.call_args.args[0].data)
        self.assertEqual(result['input_size'],[36,100])
        self.assertEqual(payload['temperature'],0)
        self.assertFalse(payload['cache_prompt'])

    def test_incomplete_or_multiline_transcription_is_rejected(self):
        for text,reason in [('文字','length'),('説明\n文字','stop')]:
            with patch('gpu_ocr_assist.urllib.request.urlopen',return_value=self.response(text,reason)):
                with self.assertRaises(ValueError):GPUClient().recognize(self.image())

    def test_only_the_local_model_endpoint_is_accepted(self):
        for endpoint in ['https://example.com/v1/chat/completions',
                         'http://192.168.8.199:8194/v1/chat/completions',
                         'http://127.0.0.1:8194/other']:
            with self.assertRaises(ValueError):GPUClient(endpoint)


class CaptureTests(unittest.TestCase):
    def test_shutdown_preserves_exact_bytes_and_private_result(self):
        with tempfile.TemporaryDirectory() as directory:
            captures=TrialCaptures(Path(directory)/'captures',limit=1)
            data=b'original-image-bytes'
            result={'text':'字','baseline_text':'原'}
            captures.save(data,result)
            captures.close()
            image=next(captures.directory.glob('*.bmp'))
            self.assertEqual(image.read_bytes(),data)
            self.assertEqual(json.loads(image.with_suffix('.json').read_text()),result)
            self.assertEqual(image.stat().st_mode & 0o777,0o600)
            self.assertEqual(image.with_suffix('.json').stat().st_mode & 0o777,0o600)

    def test_capture_limit_does_not_delete_earlier_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            captures=TrialCaptures(Path(directory)/'captures',limit=1)
            captures.save(b'first',{'text':'一'})
            captures.save(b'second',{'text':'二'})
            self.assertEqual(len(list(captures.directory.glob('*.bmp'))),1)
            self.assertEqual(next(captures.directory.glob('*.bmp')).read_bytes(),b'first')


if __name__=='__main__':
    unittest.main()
