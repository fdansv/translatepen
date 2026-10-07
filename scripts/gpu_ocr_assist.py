#!/usr/bin/env python3
"""Experimental GPU corroborator; leaves the production recognizer unchanged.

Run beside an independently started, loopback-only llama.cpp Japanese model.
The current OCR output remains authoritative except for bounded insertions and
severely collapsed lines with surviving kanji and a corroborating second view.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import io
import json
from pathlib import Path
import sqlite3
import threading
import time
import urllib.parse
import urllib.request

from PIL import Image

from ocr_server import Recognizer, japanese_letter, serve


def kana(char):
    return '\u3041' <= char <= '\u3096' or '\u30a1' <= char <= '\u30fa'


def kanji(char):
    return '\u3400' <= char <= '\u9fff'


class Lexicon:
    """Read-only JMdict support, using the project's existing deinflection rules.

    Bounded deinflection adapted from Yomichan Authors, 2016-2022,
    GPL-3.0-or-later; see vendor/YOMICHAN-LICENSE and app/Lookup.js.
    Dictionary agreement is a guard, not proof of the printed spelling.
    """
    def __init__(self, dictionary, rules):
        path = Path(dictionary).resolve()
        self.connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                          check_same_thread=False)
        self.lock = threading.Lock()
        self.cache = {}
        columns = {row[1] for row in self.connection.execute('PRAGMA table_info(entries)')}
        self.source_clause = " AND e.source='JMdict'" if 'source' in columns else ''
        flags = {'v1': 1, 'v5': 2, 'vs': 4, 'vk': 8, 'vz': 16, 'adj-i': 32, 'iru': 64}
        self.rules = []
        for variants in json.loads(Path(rules).read_text()).values():
            for variant in variants:
                incoming = outgoing = 0
                for name in variant['rulesIn']:
                    incoming |= flags.get(name, 0)
                for name in variant['rulesOut']:
                    outgoing |= flags.get(name, 0)
                self.rules.append((variant['kanaIn'], variant['kanaOut'], incoming, outgoing))

    def forms(self, term):
        result, seen = [(term, 0)], {(term, 0)}
        index = 0
        while index < len(result) and len(result) < 256:
            current, flags = result[index]
            index += 1
            for incoming_text, outgoing_text, incoming, outgoing in self.rules:
                if flags and not flags & incoming:
                    continue
                if not current.endswith(incoming_text):
                    continue
                changed = current[:-len(incoming_text)] + outgoing_text
                value = (changed, outgoing)
                if changed and value not in seen:
                    seen.add(value)
                    result.append(value)
                    if len(result) == 256:
                        break
        return result

    def lookup(self, surface):
        with self.lock:
            if surface in self.cache:
                return self.cache[surface]
            answer = None
            for term, flags in self.forms(surface):
                row = self.connection.execute(
                    'SELECT e.headword,e.reading,e.pos FROM forms f '
                    'JOIN entries e ON e.id=f.entry_id WHERE f.term=?' +
                    self.source_clause + ' AND (?=0 OR e.pos & ? != 0) LIMIT 1',
                    (term, flags, flags)).fetchone()
                if row:
                    answer = dict(surface=surface, lemma=term, headword=row[0], reading=row[1])
                    break
            self.cache[surface] = answer
            return answer

    def insertion_support(self, candidate, candidate_index):
        """Require a new word covering the gap; sentence anchors are checked above.

        A kanji can complete a noun before a particle. Kana evidence must also
        include the next character, avoiding tiny suffix fragments as evidence.
        """
        minimum_end = candidate_index + (1 if kanji(candidate[candidate_index]) else 2)
        for start in range(max(0, candidate_index - 8), candidate_index):
            for end in range(min(len(candidate), start + 12, candidate_index + 9),
                             minimum_end - 1, -1):
                surface = candidate[start:end]
                # Pure-kana short fragments are too permissive as word evidence.
                if not any(kanji(c) for c in surface) and len(surface) < 4:
                    continue
                evidence = self.lookup(surface)
                if not evidence:
                    continue
                without = surface[:candidate_index - start] + surface[candidate_index - start + 1:]
                if self.lookup(without):
                    continue  # A different valid word is not an omission diagnosis.
                return evidence
        return None

    def close(self):
        self.connection.close()


@dataclass
class Decision:
    text: str
    changed: bool
    reason: str
    edits: list
    rejected: list


def select_insertions(original, candidate, lexicon):
    """Preserve every original character; do not complete clipped boundaries.

    No fixture identity, expected answer or recognition score enters this policy.
    It requires unique local alignment, anchors and independent lexical support.
    """
    positions = [i for i, char in enumerate(original) if japanese_letter(char)]
    old = ''.join(original[i] for i in positions)
    new = ''.join(c for c in candidate if japanese_letter(c))
    neutral = lambda reason, rejected=None: Decision(original, False, reason, [], rejected or [])
    if old == new:
        return neutral('letters_agree_keep_punctuation')
    if not old or len(old) < 6 or not new or len(new) > 120:
        return neutral('insufficient_anchors_or_length')
    if any(c.isascii() and c.isalnum() for c in original + candidate):
        return neutral('mixed_script_abstention')
    # Earliest/latest subsequence alignments agree iff the alignment is unique.
    earliest, latest = [], []
    cursor = 0
    for char in old:
        found = new.find(char, cursor)
        if found < 0:
            return neutral('deletion_or_substitution')
        earliest.append(found)
        cursor = found + 1
    cursor = len(new)
    for char in reversed(old):
        found = new.rfind(char, 0, cursor)
        latest.append(found)
        cursor = found
    latest.reverse()
    edits, rejected = [], []
    if earliest[0] or earliest[-1] != len(new) - 1:
        rejected.append(dict(reason='unanchored_boundary', prefix=new[:earliest[0]],
                             suffix=new[earliest[-1] + 1:]))
    for index in range(1, len(old)):
        start, end = earliest[index - 1] + 1, earliest[index]
        if end == start:
            continue
        added = new[start:end]
        reason = None
        if len(added) != 1:
            reason = 'multiple_characters_in_one_gap'
        elif positions[index] != positions[index - 1] + 1:
            reason = 'punctuation_or_space_boundary'
        elif index < 2 or len(old) - index < 2:
            reason = 'short_context'
        elif earliest[index - 2:index + 2] != latest[index - 2:index + 2]:
            reason = 'ambiguous_local_alignment'
        elif added in (old[index - 1], old[index]):
            reason = 'duplicate_neighbour'
        elif kana(added):
            if not (kana(old[index - 1]) and kana(old[index])):
                reason = 'kana_beside_kanji_may_be_ruby'
        elif kanji(added):
            left = index
            while left > 0 and kanji(old[left - 1]):
                left -= 1
            right = index
            while right < len(old) and kanji(old[right]):
                right += 1
            if right - left < 2 or positions[right - 1] - positions[left] != right - left - 1:
                reason = 'insufficient_compound_anchors'
        else:
            reason = 'unsupported_character'
        if reason:
            rejected.append(dict(index=index, added=added, reason=reason))
            continue
        # All neighbours used as anchors must remain directly aligned. Another
        # model insertion between those neighbours makes the local context weak.
        if earliest[index - 1] - earliest[index - 2] != 1 or \
                earliest[index + 1] - earliest[index] != 1:
            rejected.append(dict(index=index, added=added, reason='unstable_local_context'))
            continue
        evidence = lexicon.insertion_support(new, start)
        if not evidence:
            rejected.append(dict(index=index, added=added, reason='no_new_lexical_support'))
            continue
        edits.append(dict(position=positions[index], added=added, evidence=evidence))
    if len(edits) > max(1, min(2, len(old) // 10)):
        return neutral('edit_budget_exceeded', rejected + edits)
    if not edits:
        return neutral('no_supported_insertion', rejected)
    text = original
    for edit in reversed(edits):
        text = text[:edit['position']] + edit['added'] + text[edit['position']:]
    return Decision(text, True, 'supported_insertion', edits, rejected)


def collapsed_line_evidence(original, candidate, width, height, confidence, lexicon):
    """Identify a severe collapse, never a reasonably complete transcription.

    This only requests a second view. It cannot itself authorize replacement.
    Three distinct surviving kanji, both ends and a known leading compound must
    agree. A contradictory kanji, mixed script or internal punctuation abstains.
    """
    positions = [i for i, c in enumerate(original) if japanese_letter(c)]
    old = ''.join(original[i] for i in positions)
    new = ''.join(c for c in candidate if japanese_letter(c))
    anchors = ''.join(c for c in old if kanji(c))
    aspect = width / max(height, 1)
    if not old or not new or confidence >= 0.8 or not 3 <= aspect <= 16 or \
            len(old) >= aspect * 0.6 or len(new) < len(old) * 2 or \
            len(new) > min(120, aspect * 2.5) or len(set(anchors)) < 3:
        return None
    if any(c.isascii() and c.isalnum() for c in original + candidate) or \
            any(not japanese_letter(c) for c in original[positions[0]:positions[-1] + 1]):
        return None
    if new[0] != anchors[0] or new[-1] != old[-1]:
        return None
    cursor = 0
    for anchor in anchors:
        index = new.find(anchor, cursor)
        if index < 0:
            return None
        cursor = index + 1
    end = 0
    while end < len(new) and kanji(new[end]):
        end += 1
    word = new[:end]
    if not 3 <= len(word) <= 8 or not word.startswith(anchors[:2]):
        return None
    support = lexicon.lookup(word)
    if not support:
        return None
    return dict(anchors=anchors, leading_word=support,
                original_prefix=original[:positions[0]],
                original_suffix=original[positions[-1] + 1:])


def select_collapsed_recovery(original, candidate, confirmation, evidence):
    """Require a shorter image view to corroborate a prefix, not just a word.

    Both views use the same model, so their errors are not independent. Surviving
    CPU kanji and strict collapse/geometry gates remain necessary. New punctuation
    is not introduced; original outer punctuation is preserved.
    """
    new = ''.join(c for c in candidate if japanese_letter(c))
    check = ''.join(c for c in confirmation if japanese_letter(c))
    word = evidence['leading_word']['surface']
    if not len(word) + 2 <= len(check) <= len(new) * 0.85 or not new.startswith(check):
        return Decision(original, False, 'collapsed_views_disagree', [], [])
    result = evidence['original_prefix'] + new + evidence['original_suffix']
    return Decision(result, True, 'corroborated_collapsed_line',
                    [dict(kind='collapsed_line', evidence=evidence,
                          confirmed_prefix=check)], [])


def short_compound_evidence(original, candidate, width, height, lexicon):
    """Request confirmation for one missing kanji in a short leading compound.

    Never repairs a whole sentence. CPU confidence cannot establish completeness;
    require implausibly little text, three distinct ordered kanji, an invalid
    partial spelling and one added kanji supported by the dictionary instead.
    """
    positions = [i for i, c in enumerate(original) if japanese_letter(c)]
    old = ''.join(original[i] for i in positions)
    new = ''.join(c for c in candidate if japanese_letter(c))
    anchors = ''.join(c for c in old if kanji(c))
    aspect = width / max(height, 1)
    if not 3 <= len(old) <= 5 or not 3 <= aspect <= 12 or len(old) >= aspect * 0.75 or \
            not 2 * len(old) <= len(new) <= aspect * 2.5 or len(set(anchors)) < 3 or \
            not all(kanji(c) for c in old[:2]) or not new.startswith(old[:2]) or \
            any(c.isascii() and c.isalnum() for c in original + candidate):
        return None
    if positions[1] != positions[0] + 1 or lexicon.lookup(old[:2]):
        return None
    end = 0
    while end < len(new) and kanji(new[end]):
        end += 1
    if end != 3 or new[2] in old[:2] or positions[2] != positions[1] + 1:
        return None
    support = lexicon.lookup(new[:end])
    if not support:
        return None
    cursor = 0
    for anchor in anchors:
        index = new.find(anchor, cursor)
        if index < 0:
            return None
        cursor = index + 1
    # The CPU's next kanji must anchor text just beyond the recovered compound.
    next_index = new.find(anchors[2], end)
    if not end <= next_index <= end + 3:
        return None
    return dict(kind='short_compound', anchors=anchors, leading_word=support,
                position=positions[2], added=new[2])


def select_short_compound(original, candidate, confirmation, evidence):
    new = ''.join(c for c in candidate if japanese_letter(c))
    check = ''.join(c for c in confirmation if japanese_letter(c))
    if not 5 <= len(check) <= len(new) * 0.85 or not new.startswith(check):
        return Decision(original, False, 'short_compound_views_disagree', [], [])
    at = evidence['position']
    text = original[:at] + evidence['added'] + original[at:]
    return Decision(text, True, 'corroborated_short_compound',
                    [dict(position=at, added=evidence['added'], evidence=evidence,
                          confirmed_prefix=check)], [])


class GPUClient:
    def __init__(self, endpoint='http://127.0.0.1:8194/v1/chat/completions', timeout=1.0):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or \
                parsed.path != '/v1/chat/completions' or parsed.username or parsed.password:
            raise ValueError('GPU endpoint must be a loopback chat-completions URL')
        if not 0 < timeout <= 5:
            raise ValueError('GPU timeout must be between zero and five seconds')
        self.endpoint, self.timeout = endpoint, timeout

    def recognize(self, image_bytes):
        then = time.perf_counter()
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.width < source.height or source.width * source.height > 1_000_000:
                raise ValueError('expected a native horizontal strip under one million pixels')
            image = source.convert('RGB').transpose(Image.Transpose.ROTATE_270)
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        payload = dict(model='pen-japanese-assist', messages=[dict(role='user', content=[
            dict(type='image_url', image_url=dict(url='data:image/png;base64,' +
                                                base64.b64encode(stream.getvalue()).decode('ascii'))),
            dict(type='text', text='OCR:')])], temperature=0, top_k=1, seed=0,
            repeat_penalty=1, max_tokens=128, cache_prompt=False)
        request = urllib.request.Request(self.endpoint, json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.load(response)
        choice = body['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('GPU output was incomplete')
        text = choice['message']['content']
        if not isinstance(text, str) or not text.strip() or len(text) > 256 or '\n' in text.strip():
            raise ValueError('GPU output was not a bounded single transcription')
        return dict(text=text.strip(), elapsed_ms=round((time.perf_counter() - then) * 1000, 3),
                    response=body, input_size=list(image.size))


class AssistedRecognizer:
    """Parallel GPU request with a bounded deadline and original-output fallback."""
    def __init__(self, baseline, client, lexicon):
        self.baseline, self.client, self.lexicon = baseline, client, lexicon
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gpu-assist')
        self.lock = threading.Lock()
        self.model_name = baseline.model_name + '+guarded-gpu-assist-experimental'

    def recognize(self, data):
        started = time.perf_counter()
        future = self.executor.submit(self.client.recognize, data)
        baseline = self.baseline.recognize(data)
        deadline = started + self.client.timeout
        candidate = None
        confirmation = None
        confirmation_error = None
        error = None
        try:
            candidate = future.result(timeout=max(0, deadline - time.perf_counter()))
            if candidate['elapsed_ms'] > self.client.timeout * 1000:
                raise TimeoutError('GPU result exceeded its deadline')
            decision = select_insertions(baseline['text'], candidate['text'], self.lexicon)
            if not decision.changed:
                with Image.open(io.BytesIO(data)) as image:
                    evidence = collapsed_line_evidence(baseline['text'], candidate['text'],
                        image.width, image.height, baseline.get('confidence', 1), self.lexicon)
                    if evidence:
                        evidence['kind'] = 'collapsed_line'
                    else:
                        evidence = short_compound_evidence(baseline['text'], candidate['text'],
                                                          image.width, image.height, self.lexicon)
                    if evidence and time.perf_counter() < deadline:
                        # A different, shorter view retains the native pixels;
                        # its width is chosen geometrically, without expected text.
                        crop = image.crop((0, 0, int(image.width * 0.6), image.height))
                        stream = io.BytesIO()
                        crop.save(stream, format='BMP')
                if evidence and time.perf_counter() < deadline:
                    second = self.executor.submit(self.client.recognize, stream.getvalue())
                    try:
                        confirmation = second.result(timeout=max(0, deadline - time.perf_counter()))
                        if time.perf_counter() > deadline:
                            raise TimeoutError('second view exceeded overall deadline')
                        selector = select_short_compound if evidence['kind'] == 'short_compound' \
                            else select_collapsed_recovery
                        decision = selector(baseline['text'], candidate['text'],
                                            confirmation['text'], evidence)
                    except Exception as caught:
                        second.cancel()
                        confirmation_error = type(caught).__name__
        except Exception as caught:
            future.cancel()
            error = type(caught).__name__
            decision = Decision(baseline['text'], False, 'gpu_unavailable_keep_original', [], [])
        total = (time.perf_counter() - started) * 1000
        return dict(**{k:v for k,v in baseline.items() if k not in ('text','server_ms','model')},
                    text=decision.text, model=self.model_name, server_ms=round(total, 1),
                    baseline_text=baseline['text'], baseline_server_ms=baseline['server_ms'],
                    gpu_assist_changed=decision.changed, gpu_assist=asdict(decision),
                    gpu_check_ms=candidate['elapsed_ms'] if candidate else None,
                    gpu_check_error=error, gpu_candidate=candidate,
                    gpu_confirmation=confirmation, gpu_confirmation_error=confirmation_error)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.baseline.close()
        self.lexicon.close()


class TrialCaptures:
    """Bounded opt-in evidence; preserve originals for later fixture promotion."""
    def __init__(self, directory, limit=24):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.limit = limit
        self.saved = 0
        self.lock = threading.Lock()

    def save(self, data, result):
        with self.lock:
            if self.saved >= self.limit:
                return
            stem = self.directory / ('scan-' + str(time.time_ns()))
            for suffix, content in [('.bmp', data),
                                    ('.json', json.dumps(result, ensure_ascii=False, indent=2).encode())]:
                destination = stem.with_suffix(suffix)
                with destination.open('xb') as stream:
                    destination.chmod(0o600)
                    stream.write(content)
            self.saved += 1

    def close(self):
        pass  # Retention is intentional; shutdown must not erase regression evidence.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='build/ppocrv5-server.onnx')
    parser.add_argument('--japanese-model', default='build/manga-ocr-model')
    parser.add_argument('--dictionary', default='build/dictionary.sqlite')
    parser.add_argument('--rules', default='vendor/deinflect.json')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8194/v1/chat/completions')
    parser.add_argument('--gpu-timeout', type=float, default=1.0)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8195)
    parser.add_argument('--capture-dir', type=Path, help='Opt-in preserved, bounded trial evidence')
    parser.add_argument('--capture-limit', type=int, default=24)
    args = parser.parse_args()
    if args.capture_limit < 1 or args.capture_limit > 100:
        parser.error('capture limit must be between 1 and 100')
    recognizer = AssistedRecognizer(
        Recognizer(args.model, threads=args.threads, japanese_model=args.japanese_model),
        GPUClient(args.endpoint, args.gpu_timeout), Lexicon(args.dictionary, args.rules))
    try:
        captures = TrialCaptures(args.capture_dir, args.capture_limit) if args.capture_dir else None
        serve(recognizer, args.bind, args.port, captures)
    finally:
        recognizer.close()


if __name__ == '__main__':
    main()
