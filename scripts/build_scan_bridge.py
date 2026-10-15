#!/usr/bin/env python3
"""Build the Qt scanner bridge with a compatible extracted ARM64 Qt/GCC toolchain.

Select its root with --toolchain-root or TRANSLATEPEN_TOOLCHAIN_ROOT.
Run scripts/bootstrap_toolchain.py first, or select another compatible toolchain.
See docs/development.md. The plugin loads with the pen's Qt 5.12.2.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'build/toolchain'


def build(toolchain_root=None, output=None):
    base = Path(toolchain_root or os.environ.get('TRANSLATEPEN_TOOLCHAIN_ROOT', BASE)).expanduser().resolve()
    required = ['qt-host/usr/lib/qt5/bin/moc', 'cross/usr/bin/aarch64-linux-gnu-gcc-13',
                'qt-sysroot/usr/include/aarch64-linux-gnu/qt5', 'sysroot', 'tesseract-arm64']
    missing = [name for name in required if not (base / name).exists()]
    if missing:
        raise FileNotFoundError('Incomplete toolchain at ' + str(base) + ': ' + ', '.join(missing) +
                                '. See docs/development.md.')
    output = Path(output or ROOT / 'build/Native').resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment['LD_LIBRARY_PATH'] = str(base / 'qt-host/usr/lib/x86_64-linux-gnu')
    moc = base / 'qt-host/usr/lib/qt5/bin/moc'
    subprocess.run([str(moc), str(ROOT/'native/scanbridge.h'), '-o', str(output/'moc_scanbridge.cpp')],
                   env=environment, check=True)
    subprocess.run([str(moc), str(ROOT/'native/migakubridge.h'), '-o', str(output/'moc_migakubridge.cpp')],
                   env=environment, check=True)
    subprocess.run([str(moc), str(ROOT/'native/plugin.cpp'), '-o', str(output/'plugin.moc')],
                   env=environment, check=True)
    environment['LD_LIBRARY_PATH'] = str(base / 'cross/usr/lib/x86_64-linux-gnu')
    qt = base / 'qt-sysroot/usr/include/aarch64-linux-gnu/qt5'
    libraries = base / 'qt-sysroot/usr/lib/aarch64-linux-gnu'
    old = base / 'tesseract-arm64'
    # Use gcc as the link driver and select the old shared C++ runtime explicitly.
    # g++ would otherwise embed its newer static runtime (needs newer glibc).
    command = [str(base/'cross/usr/bin/aarch64-linux-gnu-gcc-13'),
               '--sysroot='+str(base/'sysroot'), '-shared', '-fPIC', '-O2', '-std=c++11',
               '-Wall', '-Wextra', '-ffile-prefix-map='+str(ROOT)+'=.',
               '-DQT_CORE_LIB', '-DQT_NETWORK_LIB', '-DQT_QML_LIB',
               '-I'+str(qt), '-I'+str(qt/'QtCore'), '-I'+str(qt/'QtNetwork'), '-I'+str(qt/'QtQml'), '-I'+str(qt/'QtGui'),
               '-I'+str(ROOT/'native'), '-I'+str(output),
               str(ROOT/'native/scanbridge.cpp'), str(output/'moc_scanbridge.cpp'), str(ROOT/'native/plugin.cpp'),
               str(ROOT/'native/migakubridge.cpp'), str(output/'moc_migakubridge.cpp'),
               '-L'+str(libraries), '-L'+str(old/'usr/lib/aarch64-linux-gnu'),
               '-L'+str(old/'lib/aarch64-linux-gnu'), '-lQt5Qml', '-lQt5Network', '-lQt5Core', '-lQt5Gui',
               '-l:libstdc++.so.6',
               '-Wl,-rpath-link,'+str(libraries), '-Wl,-rpath-link,'+str(old/'usr/lib/aarch64-linux-gnu'),
               '-Wl,-rpath-link,'+str(old/'lib/aarch64-linux-gnu'),
               '-o', str(output/'libtranslatepennative.so')]
    subprocess.run(command, env=environment, check=True)
    artifact = output / 'libtranslatepennative.so'
    header = artifact.read_bytes()[:20]
    if header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 183:
        raise RuntimeError('Build output is not a little-endian AArch64 ELF64 library')
    readelf = base / 'cross/usr/bin/aarch64-linux-gnu-readelf'
    versions = subprocess.check_output([str(readelf), '--version-info', str(artifact)], text=True, env=environment)
    for family, limit in [('GLIBC', (2, 29)), ('GLIBCXX', (3, 4, 25))]:
        required = {tuple(map(int, value.split('.'))) for value in re.findall(r'\b'+family+r'_([0-9.]+)', versions)}
        if required and max(required) > limit:
            raise RuntimeError(f'Output requires {family}_{max(required)}, newer than the tested pen runtime')
    (output/'qmldir').write_bytes((ROOT/'app/Native/qmldir').read_bytes())
    inputs = sorted((ROOT / 'native').glob('*')) + [Path(__file__), ROOT / 'app/Native/qmldir']
    metadata = {'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                'source_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in inputs if path.is_file()},
                'toolchain_manifest_sha256': hashlib.sha256((base / 'toolchain-manifest.json').read_bytes()).hexdigest()
                    if (base / 'toolchain-manifest.json').is_file() else None}
    (output / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(output/'libtranslatepennative.so')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-root', type=Path, help='Root of the compatible extracted Qt/GCC/sysroot layout')
    parser.add_argument('--output', type=Path, help='Native module output directory; default build/Native')
    arguments = parser.parse_args()
    build(arguments.toolchain_root, arguments.output)
