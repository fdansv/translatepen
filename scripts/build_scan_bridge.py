#!/usr/bin/env python3
"""Build the Qt scanner bridge with a compatible extracted ARM64 Qt/GCC toolchain.

Select its root with --toolchain-root or TRANSLATEPEN_TOOLCHAIN_ROOT.
The historical private layout remains the default for existing development.
See docs/development.md. The plugin loads with the pen's Qt 5.12.2.
"""
import argparse
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'research/private/ocr-benchmark'


def build(toolchain_root=None):
    base = Path(toolchain_root or os.environ.get('TRANSLATEPEN_TOOLCHAIN_ROOT', BASE)).expanduser().resolve()
    required = ['qt-host/usr/lib/qt5/bin/moc', 'cross/usr/bin/aarch64-linux-gnu-gcc-13',
                'qt-sysroot/usr/include/aarch64-linux-gnu/qt5', 'sysroot', 'tesseract-arm64']
    missing = [name for name in required if not (base / name).exists()]
    if missing:
        raise FileNotFoundError('Incomplete toolchain at ' + str(base) + ': ' + ', '.join(missing) +
                                '. See docs/development.md.')
    output = ROOT / 'build/Native'
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
               '-Wall', '-Wextra', '-DQT_CORE_LIB', '-DQT_NETWORK_LIB', '-DQT_QML_LIB',
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
    (output/'qmldir').write_bytes((ROOT/'app/Native/qmldir').read_bytes())
    print(output/'libtranslatepennative.so')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-root', type=Path, help='Root of the compatible extracted Qt/GCC/sysroot layout')
    arguments = parser.parse_args()
    build(arguments.toolchain_root)
