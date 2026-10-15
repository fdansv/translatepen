# Contributing

This is a developer preview validated on one firmware version. Include the device model, application version and original executable SHA-256 in compatibility reports. Do not attach vendor executables, extracted resources, account sessions, tokens or private reading captures.

For OCR reports, include a short text sample you can share, an expected transcription and the exact recognition configuration. Private captures are not published with this repository. New fixtures should be independently shareable and should not silently replace a failing baseline.

Keep local dictionary lookup responsive while OCR/Migaku work runs asynchronously. Preserve request cancellation, durable ingestion IDs and recovery checks. Run the relevant host/QML tests described in [development](docs/development.md).

Useful contributions include verification on another retail unit, physical
power-cycle/restore acceptance, improvements to the guided installer and
toolchain bootstrap, and destination adapters such as Anki. A firmware port
needs a fresh audit of native addresses and object layouts. Keep automated
host-fixture results distinct from physical-device results.

The source tree uses a public-file allowlist in `.gitignore`. Add deliberately reviewed new files to that allowlist. Application contributions use GPL-3.0-or-later; preserve third-party notices and keep dictionary data licensing separate.
