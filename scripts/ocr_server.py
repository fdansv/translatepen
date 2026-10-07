#!/usr/bin/env python3
"""Recognition-only LAN OCR service for the pen's already stitched images.

POST an image's bytes to /ocr. Keep the model loaded between requests.
Requires Pillow, NumPy and ONNX Runtime. No cloud API or image persistence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import difflib
import io
import json
import math
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError


def japanese_letter(char):
    return '\u3041' <= char <= '\u30ff' or '\u3400' <= char <= '\u9fff'


def recover_collapsed_line(original, candidate, width, height, confidence=1.0):
    """Recover lost kanji on short strips with agreement between recognitions."""
    original_letters = ''.join(c for c in original if japanese_letter(c))
    candidate_letters = ''.join(c for c in candidate if japanese_letter(c))
    original_kanji = ''.join(c for c in original_letters if '\u3400' <= c <= '\u9fff')
    candidate_kanji = ''.join(c for c in candidate_letters if '\u3400' <= c <= '\u9fff')
    aspect = width / height
    # Whole-column Japanese OCR becomes unreliable on very long strips. Do not
    # let it replace a reasonably complete PP result or invent an unanchored line.
    if aspect > 8 or len(original_kanji) < 2 or \
            not candidate_letters or len(candidate_letters) > aspect * 2.5:
        return original
    collapsed = len(original_letters) < aspect * 0.6 and \
        len(candidate_letters) >= len(original_letters) * 2
    # Low-confidence PP can mix readings into the main line. In that case
    # require all surviving kanji to agree and at least one additional kanji,
    # rather than requiring its unreliable kana to survive too.
    weak = confidence < 0.85 and len(candidate_letters) >= len(original_letters) * 1.5 and \
        len(candidate_kanji) > len(original_kanji)
    if not collapsed and not weak:
        return original
    if collapsed and candidate_letters[0] == original_letters[0] and \
            candidate_letters[-1] == original_letters[-1]:
        anchors = original_letters
    elif weak and candidate_letters[0] == original_kanji[0]:
        anchors = original_kanji
    else:
        return original
    # Every surviving Japanese letter must agree, in order. In particular a
    # Japanese-model kanji substitution cannot overrule the first recognition.
    remaining = iter(candidate_letters)
    if not all(any(c == anchor for c in remaining) for anchor in anchors):
        return original
    return candidate


def recover_small_kana(original, candidate, allow_small_substitutions=False):
    """Corroborate small kana while preserving all other first-pass characters."""
    original_letters = ''.join(c for c in original if japanese_letter(c))
    candidate_letters = ''.join(c for c in candidate if japanese_letter(c))
    if not original_letters:
        return original
    alignment = difflib.SequenceMatcher(None, original_letters, candidate_letters, autojunk=False)
    operations = alignment.get_opcodes()
    # An upright reconstruction can lose punctuation or merge touching glyphs.
    # A changed kanji/kana or poor coverage makes it unsafe as corroboration.
    counterparts = dict(zip('つやゆよツヤユヨ', 'っゃゅょッャュョ'))

    def small_substitution(tag, a1, a2, b1, b2):
        return allow_small_substitutions and tag == 'replace' and a2 - a1 == b2 - b1 == 1 and \
            counterparts.get(original_letters[a1]) == candidate_letters[b1]

    matched = sum(a2 - a1 for tag, a1, a2, b1, b2 in operations
                  if tag == 'equal' or small_substitution(tag, a1, a2, b1, b2))
    if any(tag == 'replace' and not small_substitution(tag, a1, a2, b1, b2)
           for tag, a1, a2, b1, b2 in operations) or matched < len(original_letters) * 0.85:
        return original
    positions = [i for i, c in enumerate(original) if japanese_letter(c)]
    insertions = []
    for tag, a1, a2, b1, b2 in operations:
        substitution = small_substitution(tag, a1, a2, b1, b2)
        if (tag != 'insert' and not substitution) or b2 - b1 != 1 or \
                not 0 < a1 < len(original_letters) or a2 >= len(original_letters):
            continue
        char = candidate_letters[b1]
        if char not in 'っゃゅょッャュョ' or char in (original_letters[a1 - 1], original_letters[a2]):
            continue
        # Both immediate neighbours must agree, and the first pass must place
        # them next to each other, with no intervening punctuation/space.
        if b1 == 0 or b2 == len(candidate_letters) or \
                original_letters[a1 - 1] != candidate_letters[b1 - 1] or \
                original_letters[a2] != candidate_letters[b2] or \
                positions[a1] != positions[a1 - 1] + 1:
            continue
        if substitution and positions[a2] != positions[a1] + 1:
            continue
        insertions.append((positions[a1], int(substitution), char))
    for position, remove, char in reversed(insertions):
        original = original[:position] + char + original[position + remove:]
    return original


def upright_glyph_strip(image):
    """Try the sideways vertical layout only when its glyphs separate cleanly."""
    gray = image.convert('L')
    pixels = np.asarray(gray, dtype=np.int16)
    background = np.asarray(gray.filter(ImageFilter.GaussianBlur(3)), dtype=np.int16)
    rows = (pixels < background - 18).sum(axis=1)
    if not rows.max():
        return None
    main = np.flatnonzero(rows >= rows.max() * 0.25)
    top, bottom = max(0, int(main[0]) - 1), min(image.height, int(main[-1]) + 1)
    if bottom - top < 8:
        return None
    crop = image.crop((0, top, image.width, bottom))
    gray = crop.convert('L')
    pixels = np.asarray(gray, dtype=np.int16)
    background = np.asarray(gray.filter(ImageFilter.GaussianBlur(3)), dtype=np.int16)
    columns = (pixels < background - 18).sum(axis=0)
    ink = np.flatnonzero(columns)
    if not len(ink):
        return None
    gaps = np.flatnonzero(np.diff(ink) >= 3)
    starts, ends = np.r_[ink[0], ink[gaps + 1]], np.r_[ink[gaps] + 1, ink[-1] + 1]
    widths = ends - starts
    if len(widths) < 3 or widths.max() > crop.height * 1.5:
        return None  # Joined characters cannot be rotated safely as one glyph.
    typical = widths[widths > crop.height * 0.25]
    if not len(typical):
        return None
    nominal = float(np.median(typical))
    bounds = []
    # A single blank column can join two neighbouring letters at scan scale.
    # Split modestly wider groups at a local ink valley near the expected pitch.
    # Very wide/ambiguous groups were rejected above.
    for start, end in zip(starts, ends):
        start, end = int(start), int(end)
        parts = round((end - start) / nominal) if end - start > nominal * 1.6 else 1
        splits = [start]
        for part in range(1, parts):
            goal = start + (end - start) * part / parts
            low, high = max(splits[-1] + 3, round(goal) - 3), min(end - 3, round(goal) + 4)
            if low >= high:
                return None
            splits.append(min(range(low, high), key=lambda x: columns[x] + 0.2 * abs(x - goal)))
        splits.append(end)
        bounds.extend(zip(splits, splits[1:]))
    height = max(end - start for start, end in bounds) + 4
    width = crop.height * len(bounds)
    if math.ceil(width / height * 48) > 4096:
        return None
    upright = Image.new('RGB', (width, height), 'white')
    for index, (start, end) in enumerate(bounds):
        glyph = crop.crop((int(start), 0, int(end), crop.height)).transpose(Image.Transpose.ROTATE_270)
        # Baseline alignment preserves the distinction between っ and つ.
        upright.paste(glyph, (index * crop.height, height - 2 - glyph.height))
    return upright


def flatten_paper(image):
    """Remove local paper shading while keeping antialiased character strokes."""
    gray = image.convert('L')
    pixels = np.asarray(gray, dtype=np.float32)
    paper = np.asarray(gray.filter(ImageFilter.MaxFilter(5)), dtype=np.float32)
    normalized = np.clip(pixels / np.maximum(paper, 1) * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(normalized).convert('RGB')


class DiagnosticCaptures:
    """Temporary, bounded local captures; never exposed through HTTP."""
    def __init__(self, directory, minutes, limit=12):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.limit = limit
        self.lock = threading.Lock()
        self.active = True
        self.timer = threading.Timer(minutes * 60, self.close)
        self.timer.daemon = True
        self.timer.start()

    def save(self, data, result):
        with self.lock:
            if not self.active:
                return
            stem = self.directory / ("scan-" + str(time.time_ns()))
            for suffix, content in ((".bmp", data), (".json", json.dumps(result, ensure_ascii=False).encode())):
                path = stem.with_suffix(suffix)
                path.write_bytes(content)
                path.chmod(0o600)
            files = sorted(self.directory.glob("scan-*.bmp"))
            for expired in files[:-self.limit]:
                expired.unlink(missing_ok=True)
                expired.with_suffix(".json").unlink(missing_ok=True)

    def close(self):
        with self.lock:
            self.active = False
            for suffix in ("bmp", "json"):
                for path in self.directory.glob("scan-*." + suffix):
                    path.unlink(missing_ok=True)
        self.timer.cancel()


class Recognizer:
    def __init__(self, model, threads=2, japanese_model=None):
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            model, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.characters = [""] + self.session.get_modelmeta().custom_metadata_map[
            "character"
        ].splitlines() + [" "]
        self.lock = threading.Lock()
        self.model_name = 'PP-OCRv5_server_rec'
        self.japanese = None
        self.japanese_executor = None
        if japanese_model:
            import torch
            from manga_ocr import MangaOcr
            torch.set_num_threads(threads)
            torch.set_num_interop_threads(1)
            self.japanese = MangaOcr(japanese_model, force_cpu=True)
            self.japanese_executor = ThreadPoolExecutor(max_workers=1)
            self.model_name += '+manga-ocr'

    def japanese_check(self, image):
        import torch
        start = time.perf_counter()
        with torch.inference_mode():
            text = self.japanese(image.transpose(Image.Transpose.ROTATE_270))
        return text, (time.perf_counter() - start) * 1000

    def close(self):
        if self.japanese_executor is not None:
            self.japanese_executor.shutdown()

    def recognize(self, image_bytes):
        start = time.perf_counter()
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.width * source.height > 1_000_000:
                raise ValueError("image exceeds one million pixels")
            # The native line image is a horizontal strip, also for vertical text.
            if source.width < source.height:
                raise ValueError("expected the native stitched horizontal strip")
            image = ImageOps.autocontrast(source.convert("RGB"))
        if math.ceil(image.width / image.height * 48) > 4096:
            raise ValueError("strip is too long; scan a shorter line")
        japanese_future = None
        if getattr(self, 'japanese_executor', None) is not None and image.height >= 12:
            japanese_future = self.japanese_executor.submit(self.japanese_check, image)
        text, confidence, inference_time = self.recognize_image(image)
        ruby_filter = False
        # Small ruby at the side of a vertical line becomes an edge band in the
        # native strip. A blank opposite margin can be even sparser. Try the
        # quieter edge first, but check the other sparse edge if it fails. Clear
        # scans retain the single-pass path.
        if image.height >= 12 and (confidence < 0.85 or len(text) < image.width / image.height * 0.6):
            gray = image.convert("L")
            pixels = np.asarray(gray, dtype=np.int16)
            background = np.asarray(gray.filter(ImageFilter.GaussianBlur(3)), dtype=np.int16)
            rows = (pixels < background - 15).sum(axis=1)
            edge = max(1, image.height // 4)
            middle = float(rows[edge:-edge].mean())
            top, bottom = float(rows[:edge].mean()), float(rows[-edge:].mean())
            for density, side in sorted(((top, "top"), (bottom, "bottom"))):
                if middle <= 0 or density >= middle * 0.35:
                    continue
                candidates = []
                # Compare a shallow crop with the original quarter-height crop.
                # Confidence alone can prefer a result that drops main text.
                for cut in sorted({max(1, image.height // 7), edge}):
                    if math.ceil(image.width / (image.height - cut) * 48) > 4096:
                        continue
                    bounds = (0, cut, image.width, image.height) if side == "top" else \
                        (0, 0, image.width, image.height - cut)
                    candidate, candidate_confidence, second_time = self.recognize_image(image.crop(bounds))
                    inference_time += second_time
                    if candidate_confidence >= 0.85 and candidate_confidence > confidence + 0.05 and \
                            len(candidate) * candidate_confidence > len(text) * confidence * 1.2:
                        candidates.append((candidate, candidate_confidence))
                if candidates:
                    # Prefer recovered characters among credible results, then
                    # confidence. Stop after this edge succeeds so an opposite
                    # crop cannot replace it with damaged main characters.
                    text, confidence = max(candidates, key=lambda item: (len(item[0]), item[1]))
                    ruby_filter = True
                    break
        small_kana_recovery = False
        small_kana_source = None
        # Keep the already-expensive ruby retry path unchanged. The upright
        # check targets omissions in otherwise strong first-pass results.
        if image.height >= 12 and text and confidence >= 0.85 and not ruby_filter:
            upright = upright_glyph_strip(image)
            if upright is not None:
                # Gray paper blocks around reconstructed glyphs can suppress a
                # small letter. Try local illumination normalization first;
                # fall back to the untouched reconstruction if it cannot help.
                for view in (flatten_paper(upright), upright):
                    candidate, upright_confidence, second_time = self.recognize_image(view)
                    inference_time += second_time
                    if upright_confidence >= 0.88:
                        recovered = recover_small_kana(text, candidate)
                        if recovered != text:
                            text = recovered
                            confidence = min(confidence, upright_confidence)
                            small_kana_recovery = True
                            small_kana_source = 'upright'
                            break
        japanese_ms = japanese_wait = 0.0
        japanese_check_failed = False
        japanese_line_recovery = False
        if japanese_future is not None:
            waiting = time.perf_counter()
            try:
                candidate, japanese_ms = japanese_future.result()
                recovered = recover_small_kana(text, candidate, allow_small_substitutions=True)
                if recovered != text:
                    text = recovered
                    small_kana_recovery = True
                    small_kana_source = 'japanese'
                recovered = recover_collapsed_line(text, candidate, image.width, image.height, confidence)
                if recovered != text:
                    text = recovered
                    japanese_line_recovery = True
            except Exception as error:
                japanese_check_failed = True
                print('Japanese check failed: ' + type(error).__name__, flush=True)
            japanese_wait = time.perf_counter() - waiting
        total_time = time.perf_counter() - start
        return {
            "text": text,
            "confidence": round(confidence, 4),
            "preprocess_ms": round((total_time - inference_time - japanese_wait) * 1000, 1),
            "inference_ms": round(inference_time * 1000, 1),
            "server_ms": round(total_time * 1000, 1),
            "ruby_filter": ruby_filter,
            "small_kana_recovery": small_kana_recovery,
            "small_kana_source": small_kana_source,
            "japanese_check_ms": round(japanese_ms, 1),
            "japanese_check_failed": japanese_check_failed,
            "japanese_line_recovery": japanese_line_recovery,
            "model": getattr(self, 'model_name', 'PP-OCRv5_server_rec'),
        }

    def recognize_image(self, image):
        width = math.ceil(image.width / image.height * 48)
        if width > 4096:
            raise ValueError("strip is too long; scan a shorter line")
        tensor = np.zeros((1, 3, 48, max(320, width)), dtype=np.float32)
        tensor[0, :, :, :width] = (
            np.asarray(image.resize((width, 48), Image.Resampling.BILINEAR), dtype=np.float32)
            .transpose(2, 0, 1) / 127.5 - 1
        )
        prepared = time.perf_counter()
        output = self.session.run(None, {self.input_name: tensor})[0][0]
        recognized = time.perf_counter()
        if output.shape[1] != len(self.characters):
            raise RuntimeError("model vocabulary and output size differ")
        indexes = output.argmax(axis=1)
        selected = (indexes != 0) & np.r_[True, indexes[1:] != indexes[:-1]]
        text = "".join(self.characters[x] for x in indexes[selected])
        confidence = float(output.max(axis=1)[selected].mean()) if selected.any() else 0.0
        return text, confidence, recognized - prepared


def serve(recognizer, bind, port, captures=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def reply(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The pen cancelled this scan while inference was running.
            self.close_connection = True

        def do_GET(self):
            if self.path != "/health":
                self.reply(404, {"error": "not found"})
                return
            self.reply(200, {"ready": True, "model": recognizer.model_name})

        def do_POST(self):
            if self.path != "/ocr":
                self.reply(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.reply(400, {"error": "invalid content length"})
                return
            if not 0 < length <= 2_000_000:
                self.reply(413, {"error": "image must be between 1 byte and 2 MB"})
                return
            if not recognizer.lock.acquire(blocking=False):
                self.reply(429, {"error": "recognizer is busy"})
                return
            try:
                data = self.rfile.read(length)
                if len(data) != length:
                    self.reply(400, {"error": "incomplete image"})
                    return
                result = recognizer.recognize(data)
                if captures is not None:
                    captures.save(data, result)
                self.reply(200, result)
            except TimeoutError:
                self.reply(408, {"error": "image upload timed out"})
            except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
                self.reply(400, {"error": "invalid or unsupported scan image"})
            finally:
                recognizer.lock.release()

    server = ThreadingHTTPServer((bind, port), Handler)
    print(f"OCR ready at http://{bind}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if captures is not None:
            captures.close()
        recognizer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8193)
    parser.add_argument("--threads", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--japanese-model", help="Optional local Manga OCR model for small-kana corroboration")
    parser.add_argument("--capture-dir", help="Temporary local diagnostic capture directory (opt-in)")
    parser.add_argument("--capture-minutes", type=int, choices=range(1, 31), default=20)
    args = parser.parse_args()
    captures = DiagnosticCaptures(args.capture_dir, args.capture_minutes) if args.capture_dir else None
    serve(Recognizer(args.model, args.threads, args.japanese_model), args.bind, args.port, captures)
