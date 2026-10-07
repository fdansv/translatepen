# Development and testing

## Native bridge

The tested build uses GCC 13 cross tools, Debian Buster ARM64 Qt **5.11.3** headers/libraries, a glibc **2.28** sysroot and the old ARM64 C++ shared runtime. Those choices keep generated code compatible with the device's glibc 2.29 and Qt 5.12.2. Do not replace system libraries on the pen with host libraries.

The build script accepts `--toolchain-root` or `TRANSLATEPEN_TOOLCHAIN_ROOT`. Its historical default remains `research/private/ocr-benchmark` for existing local development. The expected extracted-package layout is:

```text
toolchain/
  cross/usr/bin/aarch64-linux-gnu-gcc-13
  cross/usr/lib/x86_64-linux-gnu/
  qt-host/usr/lib/qt5/bin/moc
  qt-host/usr/lib/x86_64-linux-gnu/
  qt-sysroot/usr/include/aarch64-linux-gnu/qt5/
  qt-sysroot/usr/lib/aarch64-linux-gnu/
  sysroot/usr/include/
  sysroot/usr/lib/aarch64-linux-gnu/
  tesseract-arm64/usr/lib/aarch64-linux-gnu/
  tesseract-arm64/lib/aarch64-linux-gnu/
```

The directory named `tesseract-arm64` supplies the older C++ runtime/link dependencies; the native plugin does not run Tesseract. The original packages were Ubuntu 24.04 GCC 13 cross tools and Debian Buster `qtbase5-dev`, `qtdeclarative5-dev`, `qtbase5-dev-tools`, `libc6-dev`, `libc6`, `linux-libc-dev`, `libstdc++6` and matching Qt/shared-library dependencies. The host `moc` and Qt header versions should match.

This preview documents the existing layout but does not yet provide a fully automated toolchain bootstrap. Extract development packages into an isolated toolchain directory rather than installing old libraries into your host system.

```sh
python3 scripts/build_scan_bridge.py --toolchain-root /absolute/path/to/toolchain
```

Output: `build/Native/libtranslatepennative.so` and `build/Native/qmldir`. Build artifacts, vendor executables and extracted QML stay out of Git.

## Host-side tests

After installing `server/requirements-ocr.txt` into your environment:

```sh
python -m unittest discover -s tests -p 'names_dictionary_build.py'
python -m unittest discover -s tests -p 'ocr_*.py'
```

These published OCR tests use synthetic pixels and mocked inference; no private scan fixtures, model weights or pen are required. GitHub Actions runs these checks on Python 3.12.

The GPU policy tests additionally need the ordinary dictionary from [OCR setup](ocr.md):

```sh
python -m unittest discover -s tests -p 'gpu_ocr_assist.py'
```

## On-device QML tests

The QML tests need the native module, current dictionary, rules and app installed on a compatible pen. Copy the selected `tests/` directory under `/userdata/translatepen/tests/`. For example:

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QV4_FORCE_INTERPRETER=1 \
  LD_LIBRARY_PATH=/oem qmlscene /userdata/translatepen/tests/LookupTest.qml
```

Require the matching `TRANSLATEPEN_*_PASS` log marker; QML process exit status alone is not proof of success. The lookup test creates and removes its own test vocabulary row. `NamesLookupTest.qml` needs the combined JMdict/JMnedict dictionary. Page tests use mocked scanner/Migaku objects but still load the native module and local dictionary.

Hardware controls, physical capture and recovery need separate checks on the real device. Host tests and offscreen renders cannot establish those outcomes.
