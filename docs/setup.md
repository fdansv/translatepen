# Complete pen setup: developer preview

The setup uses [TranslatePen](https://github.com/fdansv/translatepen) for the pen
and OCR, and [Migaku Local API](https://github.com/fdansv/migaku-api) for optional
Migaku features. Start with a trusted LAN and native Linux services. Remote
access and GPU assist are optional additions.

## 1. Establish access and compatibility first

Read [root SSH access](ssh-access.md). Root login was obtained on the author's
unit without flashing or opening it; access on other retail units is not
verified. This is not a general firmware-unlock tool.

You need an MSE09 with original application V2.2.83 and `/oem/scanpen` SHA-256
`606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c`.
The version label alone is insufficient. From an x86-64 Linux computer with
Python 3.12 and OpenSSH:

```sh
PEN_SSH_TARGET=root@YOUR_PEN_IP
python3 scripts/check_pen.py "$PEN_SSH_TARGET"
mkdir -p research/private
ssh "$PEN_SSH_TARGET" 'cat /oem/scanpen' > research/private/scanpen
sha256sum research/private/scanpen
```

The check is read-only. A modified application is not approved for a fresh
installation, even when an original backup exists. Use the restore step below
before updating an existing TranslatePen installation. Preserve your original
executable locally as well as on the pen; it is not a full device recovery image.

## 2. Start OCR and optionally Migaku

Follow [dictionary and OCR setup](ocr.md): build the dictionary and start the
CPU OCR service on a LAN address reachable by the pen. Model fetchers verify
pinned weights; models and dictionary archives are downloaded separately.
Check `http://YOUR_SERVER_IP:8193/health` from another LAN client.

For Migaku, follow the [API quick start](https://github.com/fdansv/migaku-api#quick-start-linux).
Run its offline doctor before logging in. Card enrichment and translation need
the exact supported **1.31.0.16** extension assets; a newly installed different
version may require an adapter update. Use your own Migaku account and extension.
Check `/worker` reports `authenticated`, `ready` and `initial_sync_done`.

Configure a persistent bearer token and LAN bind as described in
[API deployment](https://github.com/fdansv/migaku-api/blob/main/docs/setup.md).
Select your destination deck in the isolated extension or configure
`MIGAKU_INGEST_DECK_ID`. Docker login/profile portability remains experimental;
the native Linux setup is the tested starting point.

## 3. Obtain the native plugin

Use either the prebuilt plugin or the reproducible source build. Do not mix
application source and a native archive from different releases.

**Prebuilt:** download `translatepen-native-mse09.tar.gz` from the
[developer-preview releases](https://github.com/fdansv/translatepen/releases).
Use the corresponding source tag. The archive includes the plugin, QML module
file, build provenance, integrity checksums and license; no vendor firmware,
dictionaries or account configuration is included.

```sh
mkdir -p build/prebuilt
# Download the release archive to this computer first.
tar -xzf /path/to/translatepen-native-mse09.tar.gz -C build/prebuilt
(cd build/prebuilt && sha256sum -c SHA256SUMS)
PEN_NATIVE_DIR=build/prebuilt/Native
```

**Source:** on Ubuntu 24.04 x86-64 (or a VM), follow
[toolchain prerequisites](development.md#native-bridge), then:

```sh
python3 scripts/bootstrap_toolchain.py
python3 scripts/build_scan_bridge.py
PEN_NATIVE_DIR=build/Native
```

The bootstrap downloads and verifies pinned official packages, extracting them
under `build/toolchain`. It does not install old libraries into the host or pen.
The build rejects an unexpected ELF architecture or symbols newer than the
supported runtime.

## 4. Prepare a private installation directory

If using Migaku, create an ignored local `.runtime/migaku.json` containing your
own endpoint and API token, and restrict it to mode `0600`:

```json
{"endpoint":"http://YOUR_SERVER_IP:8766","token":"YOUR_PRIVATE_API_TOKEN"}
```

Create the `.runtime` directory with mode `0700`. Edit the configuration using
your local editor; do not put real tokens in command arguments or Git.
The Migaku API root has no `/ingest` suffix.

```sh
python3 scripts/stage_pen.py \
  --original research/private/scanpen \
  --dictionary build/dictionary-with-names.sqlite \
  --native "$PEN_NATIVE_DIR" \
  --ocr-endpoint http://YOUR_SERVER_IP:8193/ocr \
  --output build/pen-install
```

Add `--migaku-config .runtime/migaku.json` for Migaku. For remote OCR, use
`--ocr-config .runtime/ocr.json` instead of `--ocr-endpoint`, following
[authenticated remote access](remote-access.md).

The stage helper validates the original hash, native architecture and SQLite
integrity, patches a private copy of your executable, and produces `SHA256SUMS`.
Its output and adjacent diagnostic QML contain vendor code and may contain
credentials: keep them private. It refuses to overwrite an existing output
directory; choose a new path for another attempt.

## 5. Transfer and install

Use a fresh directory on the pen for each attempt. The following streams a tar
archive over SSH, avoiding dependence on an SFTP server on the pen:

```sh
tar -czf build/pen-install.tar.gz -C build/pen-install .
PEN_STAGE=/userdata/translatepen/staging-$(date +%Y%m%dT%H%M%S)
ssh "$PEN_SSH_TARGET" 'umask 077; mkdir -p /userdata/translatepen'
ssh "$PEN_SSH_TARGET" "umask 077; mkdir '$PEN_STAGE'"
ssh "$PEN_SSH_TARGET" "tar -xzf - -C '$PEN_STAGE'" < build/pen-install.tar.gz
ssh "$PEN_SSH_TARGET" "cd '$PEN_STAGE' && sh ./install_pen.sh"
```

Keep the pen powered and awake. The installer requires the supported stock
executable, verifies staging checksums, checks available space, and saves the
original plus an archive of existing managed files. It installs app/data files
before atomically replacing `/oem/scanpen`, then lets the vendor watchdog
restart it. Existing Migaku configuration is preserved when no replacement
configuration was staged. Dictionary, application and native-module backups
remain available. Vendor startup scripts and partitions are unchanged.

The installer is not a power-loss transaction across all filesystems. If it
stops before completion, keep its printed backup path and staging directory.
The original executable remains available in the verified original backup.
Host filesystem tests exercise failure handling and a restore/reinstall cycle;
physical installation, power loss and full device recovery remain separate checks.

## 6. Verify, restore and update

Open the new pen icon, scan a known printed line, navigate words and select a
span. With Migaku, verify underlines, translation and a double-B sentence card
in your own account. Confirm the chosen card/deck and job status. See
[development tests](development.md#on-device-qml-tests) and the
[reproducibility checklist](reproducibility.md).

To return to the stock application over SSH:

```sh
ssh "$PEN_SSH_TARGET" 'sh /userdata/translatepen/restore_pen.sh'
```

If installation stopped before copying that helper, run `restore_pen.sh` from
the retained staging directory. The helper verifies the original hash and
atomically restores the executable; it preserves dictionary, configuration,
vocabulary, outbox and backup files. For an update, restore stock, run the
compatibility check again, and install a fresh staged directory. Do not copy a
patched executable back into `research/private/scanpen` as the original.

After successful installation, perform a normal physical power-off/power-on,
verify the stock interface and custom page, and repeat a scan. A physical
restore/reinstall/power-cycle acceptance run on a second retail unit is still
unverified. Keep this release described as a developer preview.
