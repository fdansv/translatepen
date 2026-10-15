# Reproducing the developer preview

Use the [combined setup guide](setup.md). All three components have public
source: the pen app/native bridge and OCR in this repository, and the
[Migaku API](https://github.com/fdansv/migaku-api) separately. Match source tags
to native prebuilt archives. Dictionary data, model downloads, your own vendor
executable and your own authenticated Migaku extension remain external inputs.

## Verification boundaries

| Area | Automated or verified evidence | Remaining check |
| --- | --- | --- |
| Native build | Pinned package downloads from Ubuntu/Debian; new toolchain directory; AArch64 build and GLIBC/GLIBCXX checks; CI repeats the build | Runtime loading on another retail pen |
| Native archive | Source/input/artifact hashes, clean-source packaging and archive checksums; no vendor executable/resources | Use the archive matching your source release |
| Pen access | Existing root SSH on the author's V2.2.83 unit; read-only compatibility probe | SSH availability/credentials on another untouched retail unit |
| Installer | Original and payload hashes, free-space checks, retained backups; host fixture covers corruption, storage failure and configuration preservation | Actual install under the pen's mounts/watchdog and physical power-loss behavior |
| Restore/reinstall | Checksum-gated executable restore and reinstall in an isolated host filesystem fixture | A physical restore/reinstall/power-cycle acceptance run |
| OCR | Host regression tests with synthetic pixels/mocked inference; model fetchers verify pinned weights; CPU service instructions | Broad font/layout accuracy and your own physical scans |
| Migaku | Offline doctor checks extension assets and browser availability; fake-RPC/API tests; original authenticated installation validated | Your login, initial sync, deck, account services and live RPC behavior |
| Remote access | Gateway tests and original pen HTTPS checks | Your tunnel/domain and a physical scan through an external network |

These checks do not establish universal retail compatibility. Host tests do
not run the pen's hardware, native Qt app, kernel, storage mounts or watchdog.

## Acceptance on a new unit

1. Save model/version details and the original executable checksum. Establish
   root SSH and run `scripts/check_pen.py` before staging an installation.
2. Retain a local copy of the verified original. Confirm the installer's printed
   backup path and run a physical scan after installation.
3. Check compounds, conjugated words, name alternatives, volume navigation,
   exact span selection and return to the stock home interface.
4. With Migaku configured, verify a known and unknown word, initial unknown-word
   selection, whole-scan translation and one card in your selected deck.
5. Run the stock restore command, confirm the original hash and verify that the
   stock UI still scans. Install a fresh stage again and repeat a scan.
6. Perform a normal physical power-off/power-on and repeat the checks. Keep the
   original backup and installation log. Do not describe this checklist as
   passed until you have done it on the physical device.

If SSH is unavailable, the executable backup is not a general recovery path.
No partition flashing, factory recovery image or hardware recovery procedure
is supplied by this project.
