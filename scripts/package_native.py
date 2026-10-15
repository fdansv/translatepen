#!/usr/bin/env python3
"""Package only our native plugin, license and source reference; no vendor firmware or runtime files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def package(native, output):
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit the reviewed source before making a public binary archive.')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    metadata = json.loads((native / 'build.json').read_text())
    if hashlib.sha256((native / 'libtranslatepennative.so').read_bytes()).hexdigest() != metadata['artifact_sha256']:
        raise ValueError('Native artifact does not match its build metadata')
    for name, digest in metadata['source_files'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Native artifact was built from different source; rebuild before packaging.')
    files = {'Native/libtranslatepennative.so': (native / 'libtranslatepennative.so').read_bytes(),
             'Native/qmldir': (native / 'qmldir').read_bytes(),
             'Native/build.json': (native / 'build.json').read_bytes(),
             'LICENSE': (ROOT / 'LICENSE').read_bytes(),
             'NOTICE': (ROOT / 'NOTICE').read_bytes()}
    files['BUILD.txt'] = (f'Source: https://github.com/fdansv/translatepen/tree/{commit}\n'
        'Compatibility: MSE09 application V2.2.83 only; verify the original executable hash.\n'
        'Build: python3 scripts/bootstrap_toolchain.py && python3 scripts/build_scan_bridge.py\n'
        'Toolchain integrity pins: scripts/toolchain-packages.json in the corresponding source.\n'
        'This archive contains no vendor executable, dictionary, configuration or credentials.\n').encode()
    files['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n'
        for name, data in sorted(files.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as archive:
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size = len(data)
            item.mode = 0o644
            archive.addfile(item, io.BytesIO(data))
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, default=ROOT / 'build/Native')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/translatepen-native-mse09.tar.gz')
    args = parser.parse_args()
    package(args.native, args.output)
