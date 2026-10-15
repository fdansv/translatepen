#!/usr/bin/env python3
"""Prepare a PRIVATE install directory from your original executable and dictionary."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import urllib.parse

from patch_launcher import patch
from extract_qml import EXPECTED

ROOT = Path(__file__).resolve().parents[1]


def config(path=None, endpoint=None):
    value = json.loads(path.read_text()) if path else {'endpoint': endpoint}
    if not isinstance(value, dict) or not isinstance(value.get('endpoint'), str):
        raise ValueError('Configuration must be a JSON object with an endpoint string')
    url = urllib.parse.urlsplit(value.get('endpoint', ''))
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Configuration needs an http(s) endpoint without credentials, query or fragment')
    if set(value) - {'endpoint', 'token'} or not isinstance(value.get('token', ''), str):
        raise ValueError('Configuration supports only endpoint and an optional token string')
    return value


def stage(original, dictionary, native, output, ocr, migaku=None):
    if hashlib.sha256(original.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('Unsupported original executable; the version label alone is insufficient')
    header = (native / 'libtranslatepennative.so').read_bytes()[:20]
    if header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 183:
        raise ValueError('Native plugin must be an AArch64 ELF64 library')
    with sqlite3.connect(dictionary.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Dictionary integrity check failed')
        connection.execute('SELECT COUNT(*) FROM entries').fetchone()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for directory in ['app', 'Native']:
        (output / directory).mkdir()
    for source in sorted((ROOT / 'app').iterdir()):
        if source.suffix in {'.qml', '.js'}:
            shutil.copyfile(source, output / 'app' / source.name)
    for name in ['libtranslatepennative.so', 'qmldir']:
        shutil.copyfile(native / name, output / 'Native' / name)
    shutil.copyfile(dictionary, output / 'dictionary.sqlite')
    for source, name in [(ROOT / 'vendor/deinflect.json', 'deinflect.json'),
                         (ROOT / 'vendor/ATTRIBUTION.txt', 'ATTRIBUTION.txt'),
                         (ROOT / 'vendor/YOMICHAN-LICENSE', 'YOMICHAN-LICENSE'),
                         (ROOT / 'LICENSE', 'LICENSE'),
                         (ROOT / 'scripts/restore_pen.sh', 'restore_pen.sh'),
                         (ROOT / 'scripts/install_pen.sh', 'install_pen.sh')]:
        shutil.copyfile(source, output / name)
    patch(original, output / 'scanpen')
    # The patcher's diagnostic contains vendor QML. Leave it outside the
    # transferred tree, in the same ignored private output parent.
    (output / 'scanpen.main.qml').replace(output.with_name(output.name + '.main.qml'))
    output.with_name(output.name + '.main.qml').chmod(0o600)
    for name, value in [('ocr.json', ocr), ('migaku.json', migaku)]:
        if value is not None:
            (output / name).write_text(json.dumps(value) + '\n')
            (output / name).chmod(0o600)
    files = sorted(path for path in output.rglob('*') if path.is_file())
    sums = ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output)}\n' for path in files)
    (output / 'SHA256SUMS').write_text(sums)
    print(f'Private install directory ready: {output} (contains modified vendor code and possibly credentials; never publish it)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--dictionary', type=Path, required=True)
    parser.add_argument('--native', type=Path, default=ROOT / 'build/Native')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/pen-install')
    endpoints = parser.add_mutually_exclusive_group(required=True)
    endpoints.add_argument('--ocr-endpoint', help='e.g. http://YOUR_SERVER_IP:8193/ocr')
    endpoints.add_argument('--ocr-config', type=Path, help='Private JSON for OCR with a device bearer token')
    parser.add_argument('--migaku-config', type=Path, help='Optional private Migaku JSON, copied without logging its token')
    args = parser.parse_args()
    try:
        stage(args.original, args.dictionary, args.native, args.output,
              config(args.ocr_config, args.ocr_endpoint), config(args.migaku_config) if args.migaku_config else None)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
