# TranslatePen

Japanese dictionary lookup and optional Migaku integration for the **WorldPenScan Go MSE09**. Scan a line in a physical book, navigate whole words with the volume keys, and read definitions and name readings on the pen. Double-press B to send the sentence and selected word to Migaku.

![Pen interface showing dictionary lookup and unknown-word underlines with a test sentence](docs/images/pen-ui.png)

**Developer preview.** This works on the author's device running application **V2.2.83**. The native bridge and launcher patch require an exact executable checksum. Other firmware versions are unsupported. A guided install, toolchain bootstrap and native-only prebuilt previews are supplied; a physical power-cycle and restore/reinstall acceptance run remains unverified.

## What it does

- Looks up compounds and conjugated forms using local JMdict data and Yomichan deinflection.
- Provides offline JMnedict readings for names, places and stations, with alternative readings.
- Offers taps, manual span selection and volume-key navigation.
- Defaults to the first word Migaku marks unknown in each scan. Local lookup appears immediately; if word status is unavailable or all words are known, the first local match stays selected. Manual selection takes precedence over a late status reply.
- Sends scans to a Japanese OCR service on your computer or home server. Use a LAN connection or the [authenticated Cloudflare gateway](docs/remote-access.md); dictionary lookup is local.
- With [Migaku Local API](https://github.com/fdansv/migaku-api), underlines unknown words, marks words known, and queues sentence cards without blocking dictionary lookup.
- Translates the full scanned text below the definition using Migaku's configured translation language. Translation loads after local lookup; word navigation keeps the same translation.

Migaku features require your own account and an authenticated Migaku extension running on the API host. Migaku synchronization and AI enrichment use Migaku's online services. Local OCR needs no internet after model download.

## Start here

1. Read the [combined setup guide](docs/setup.md) and [root SSH access notes](docs/ssh-access.md) before buying or changing a pen.
2. Set up [dictionary data and server OCR](docs/ocr.md).
3. Review [development and testing](docs/development.md) before building or changing the native plugin.

This source release contains the app, native bridge, patcher, dictionary builders, CPU OCR and optional GPU corroborator. [Releases](https://github.com/fdansv/translatepen/releases) provide our native plugin separately. Vendor firmware/resources, account sessions, model weights and private installation bundles are excluded. The [reproducibility checklist](docs/reproducibility.md) distinguishes host checks from physical-device checks.

## Controls

| Action | Control |
| --- | --- |
| Scan text | Scan tip / scan key |
| Next / previous word | Volume + / −; wraps at either end |
| Choose a word | Tap it |
| Select an exact span | Select, then tap the first and last character |
| Next dictionary alternative | **1 / N ›** |
| Mark a word known | **Mark known**; needs Migaku API |
| Create a Migaku sentence card | B twice within 450 ms |
| Return to the stock interface | Back arrow or circular hardware key |

## How it fits together

```text
Pen scanner → native Qt bridge → LAN OCR service → sentence on pen
                                                    ↓
                                            local dictionary
                                                    ↓
                               optional Migaku Local API → Migaku
```

The plugin runs inside the existing Qt application. The launcher patch adds the new page and reserves volume-key navigation for it. No partitions are flashed and vendor startup/watchdog scripts are retained. [Architecture and compatibility](docs/architecture.md).

## Status and limits

The existing device has passed physical scan checks, dictionary/navigation checks and Migaku integration checks. Those results describe one MSE09 and the author's server; they are not a multi-device compatibility claim. OCR still makes mistakes, particularly with furigana, clipped scans and ambiguous glyphs. Battery impact and broad font/layout coverage have not been established.

The CPU OCR pipeline is the baseline. An optional GPU corroborator improved saved cases and a small number of fresh scans, but adds hardware/model requirements. See [OCR setup](docs/ocr.md). Start with the documented native Linux/LAN route; GPU model conversion and hardware-specific setup remain manual.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Contributions toward installation, compatible firmware versions, OCR fixtures and additional destinations such as Anki are welcome. Keep local lookup independent of remote services.

## License and attribution

TranslatePen code is **GPL-3.0-or-later**; see [LICENSE](LICENSE). The deinflection algorithm and rules are adapted from Yomichan and retain its notices. Derived JMdict/JMnedict dictionary data is **CC BY-SA 4.0**, separately from the code. See [NOTICE](NOTICE) and [vendor/ATTRIBUTION.txt](vendor/ATTRIBUTION.txt).

This is an independent project, unaffiliated with PenPower or Migaku. Vendor firmware, fonts, dictionaries and the Migaku extension retain their own ownership and licensing.
