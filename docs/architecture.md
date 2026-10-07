# Architecture and compatibility

## Pen

The MSE09 is a Buildroot Linux ARM64 appliance running Qt 5.12.2. `app/Japanese.qml` runs inside the vendor application's existing stack view, and `scripts/patch_launcher.py` adds its launcher and volume-key guard. `native/scanbridge.cpp` invokes scanner methods at fixed addresses in the inspected executable, cancels the pending vendor OCR timer and uploads the freshly produced lossless line BMP.

The bridge checks the native code section and mapped entry instructions before calling those addresses. The patcher separately checks the complete original executable hash. An application update requires a new compatibility audit; matching product names do not establish compatibility.

OCR responses carry request IDs. New scans and page exit reject or cancel older requests. Local SQLite lookup and Yomichan deinflection are independent of Migaku requests. JMnedict alternatives rank after ordinary JMdict definitions.

## Migaku

`native/migakubridge.cpp` reads the private pen configuration and calls the standalone [Migaku Local API](https://github.com/fdansv/migaku-api). It requests sentence analysis, known-word updates and sentence ingestion asynchronously. The local outbox stores a sentence/focus snapshot and a stable request ID for retries.

The API runs the actual authenticated Migaku extension in a separate Chromium profile. Its private extension RPCs supply parsing, word status, card creation and synchronization. The service does not implement Migaku's cloud backend. Text offsets use UTF-16 code units, matching Qt/JavaScript.

Card enrichment sends sentence/focus data rather than the pen's dictionary gloss. Migaku helpers fill definitions, translation, AI explanation and syntax; automatic image/audio generation is outside the adapter's current scope. Unknown write outcomes are reconciled rather than blindly resubmitted.

## State boundaries

- Pen app/dictionary/configuration: `/userdata/translatepen/`.
- QML native plugin: `/usr/qml/TranslatePen/Native/`.
- Vendor executable: `/oem/scanpen`; original backup under `/userdata/translatepen/backups/`.
- Live pen vocabulary/outbox: Qt LocalStorage under `/.local/share/scanpen/QML/OfflineStorage/Databases/` on the tested firmware.
- OCR models and toolchain: local ignored build directories.
- API sessions, SQLite state and jobs: the API's private `.runtime/` directory.

The application restore preserves pen state. It is not a partition backup or a validated recovery procedure for an unbootable device.
