# Development and testing

## Native bridge

The tested build uses GCC 13 cross tools, Debian Buster ARM64 Qt **5.11.3** headers/libraries, a glibc **2.28** sysroot and the old ARM64 C++ shared runtime. Those choices keep generated code compatible with the device's glibc 2.29 and Qt 5.12.2. Do not replace system libraries on the pen with host libraries.

The default toolchain is now reproducible from official package downloads. On
Ubuntu 24.04 x86-64, install the host prerequisites once:

```sh
sudo apt-get update
sudo apt-get install -y python3 dpkg libisl23 libmpc3 libmpfr6 libgmp10 libzstd1 zlib1g
python3 scripts/bootstrap_toolchain.py
python3 scripts/build_scan_bridge.py
```

The bootstrap verifies all package SHA-256 values in
`scripts/toolchain-packages.json` before extraction. Debian archive packages
have content-addressed Debian Snapshot fallbacks. Downloads are cached in
`build/toolchain-downloads`; use `--cache /path/to/cache --offline` to reuse a
complete verified cache. It refuses to replace a different existing toolchain.
No development package is installed on the pen or into the host's system paths.

The build script also accepts `--toolchain-root` or
`TRANSLATEPEN_TOOLCHAIN_ROOT` for an existing compatible toolchain. Its default
is `build/toolchain`. The expected extracted-package layout is:

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

The bootstrap uses one extracted target sysroot, with relative `qt-sysroot`
and `tesseract-arm64` aliases pointing to it. The latter is a historical
directory name; the pen plugin does not use Tesseract. Package download URLs,
versions and checksums are pinned, including the original cross compiler.

```sh
python3 scripts/build_scan_bridge.py --toolchain-root /absolute/path/to/toolchain
```

Output: `build/Native/libtranslatepennative.so`, `qmldir` and `build.json`.
`--output` selects another build directory. The builder verifies AArch64 ELF64
and rejects required GLIBC/GLIBCXX versions newer than the tested pen runtime.
`build.json` records input hashes and artifact integrity. From a clean committed
tree, `python3 scripts/package_native.py` creates the distributable native-only
archive with source provenance. It rejects stale artifacts or uncommitted source.
GitHub Actions repeats the download/build/package path on Ubuntu 24.04 and
uploads the native archive. Prebuilt previews are published under Releases.
Vendor executables and extracted QML stay out of Git and public archives.

## Host-side tests

After installing `server/requirements-ocr.txt` into your environment:

```sh
python -m unittest discover -s tests -p 'names_dictionary_build.py'
python -m unittest discover -s tests -p 'ocr_*.py'
python -m unittest discover -s tests -p 'pen_gateway.py'
python -m unittest discover -s tests -p 'setup_tools.py'
```

These published OCR tests use synthetic pixels and mocked inference; no private scan fixtures, model weights or pen are required. GitHub Actions runs these checks on Python 3.12.

Gateway tests use local fake upstream services and temporary device credentials. They cover authentication, revocation, route restrictions, upload framing/limits, credential separation, idempotency, redirects, upstream failures and connection bounds without accessing a Migaku account.

Setup tests check corrupted downloads, refusal to replace an existing toolchain,
unsupported firmware, storage failures, private backup permissions, preservation
of existing configuration, and install/restore/reinstall in an isolated host
filesystem fixture. The fixture does not run the vendor app or its watchdog.

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

`TranslationIntegrationTest.qml` checks that definitions precede translation, older scan replies are ignored, word navigation retains the translation, and failures can be retried. `RenderTest.qml` and `MigakuRenderTest.qml` use fixture translations and make no live translation requests.

`UnknownFocusTest.qml` checks the initial unknown-word priority, exact token spans and UTF-16 offsets, fallback when status is unavailable, words missing from the local dictionary, and preservation of manual choices made before a status reply.

`LoadingIntegrationTest.qml` checks the top-bar indicator across overlapping translation/status requests, card submission, generation and syncing, navigation, offline retry and failures. It uses mocked Migaku jobs and creates no live cards.
