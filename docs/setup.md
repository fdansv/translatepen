# Complete pen setup: developer preview

The complete setup uses two repositories: [TranslatePen](https://github.com/fdansv/translatepen) for the pen and OCR, and [Migaku Local API](https://github.com/fdansv/migaku-api) for optional Migaku features. You can run dictionary/OCR lookup without the Migaku service.

## Requirements

- WorldPenScan Go **MSE09**, application **V2.2.83**, with original `/oem/scanpen` SHA-256:
  `606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c`.
- Root SSH access to your own pen and a computer that can reach it over Wi-Fi.
- Python 3.12 on a computer/server for OCR and dictionary building.
- For native compilation, an x86-64 Linux host and the compatible ARM64 Qt/sysroot toolchain described in [development](development.md).
- For Migaku features, your own Migaku account, installed extension and [API setup](https://github.com/fdansv/migaku-api#quick-start-linux).

The repository does not provide an SSH password or a procedure to enable SSH. Root access worked on the original device; obtaining access on another unit remains a prerequisite. A matching application version label alone is insufficient: the executable checksum must match.

## 1. Set up the services

Follow [OCR and dictionary setup](ocr.md). Start OCR on an address reachable from the pen and verify `/health` from another LAN device. OCR listens on loopback by default and has no authentication; use a trusted LAN or private network.

Optionally start Migaku Local API and finish its separate-browser login. Check `/worker` reports authentication and readiness, then choose your destination deck in the extension or set the API's `MIGAKU_INGEST_DECK_ID`. Its default Docker port mapping is loopback-only; follow the API's LAN instructions before connecting the pen.

## 2. Build the native plugin and patch your own executable

See [development](development.md). Copy your original executable from the pen into ignored `research/private/scanpen`, then run:

```sh
mkdir -p research/private build
# Copy /oem/scanpen from your pen into research/private/scanpen first.
sha256sum research/private/scanpen
python3 scripts/build_scan_bridge.py --toolchain-root /absolute/path/to/toolchain
python3 scripts/patch_launcher.py research/private/scanpen build/scanpen
```

The patcher refuses an unexpected original hash. It also writes `build/scanpen.main.qml`, which contains modified vendor resources and must stay private. Keep the entire original executable and all extracted resources outside public Git history.

## 3. Configure and stage the pen files

These are the installation destinations; this is a map for developers, not an automated installer:

| Local file | Destination on pen |
| --- | --- |
| `app/` | `/userdata/translatepen/app/` |
| `build/Native/libtranslatepennative.so`, `build/Native/qmldir` | `/usr/qml/TranslatePen/Native/` |
| `build/dictionary-with-names.sqlite` | `/userdata/translatepen/dictionary.sqlite` |
| `vendor/deinflect.json` | `/userdata/translatepen/deinflect.json` |
| `vendor/ATTRIBUTION.txt`, `vendor/YOMICHAN-LICENSE`, `LICENSE` | `/userdata/translatepen/` |
| `scripts/restore_pen.sh` | `/userdata/translatepen/restore_pen.sh` |
| Unmodified original executable | `/userdata/translatepen/backups/scanpen.original` |
| Patched `build/scanpen` | `/oem/scanpen` |

Set your OCR address in `app/Japanese.qml` before copying it to the pen:

```qml
Native.ScanBridge {
    id: defaultScanner
    endpoint: "http://YOUR_SERVER_IP:8193/ocr"
}
```

Replace the existing `Native.ScanBridge { id: defaultScanner }` declaration. The historical native default is specific to the author's LAN, so set this explicitly.

For optional Migaku features, create `/userdata/translatepen/migaku.json` on the pen, using your own API address and token:

```json
{
  "endpoint": "http://YOUR_SERVER_IP:8766",
  "token": "YOUR_PRIVATE_API_TOKEN"
}
```

Restrict this file's permissions to the account running the pen application (root on the tested firmware). Keep it out of Git and screenshots. Without this configuration, local lookup still works.

Before replacing the application, verify the backup hash on the pen and ensure every required file is staged. The current prototype uses an atomic replacement of the executable and the existing vendor watchdog to restart it. A general-purpose installer, free-space checks and a validated full restore/reinstall cycle remain release work.

## 4. Verify and restore

Open the new pen icon, scan a known printed line, navigate words, and test manual span selection. If using Migaku, verify word status and one sentence card in your own account. Use [QML tests](development.md#on-device-qml-tests) before changing scanner code.

The full application restore command, run on the pen over SSH, is:

```sh
sh /userdata/translatepen/restore_pen.sh
```

It checks the original backup hash, atomically restores `/oem/scanpen`, and lets the watchdog restart it. It preserves dictionary data and vocabulary/outbox databases. This script has been inspected; a complete restore/reinstall and power-cycle test has not yet been performed. The executable backup is **not a full device recovery image**.
