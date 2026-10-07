# Dictionary and OCR setup

Use Python 3.12 on a Linux computer/server. The pen performs dictionary lookup locally but sends scan images to the OCR service over your LAN.

## Build dictionary data

Run from the TranslatePen repository:

```sh
mkdir -p data build
curl --fail --location https://www.edrdg.org/pub/Nihongo/JMdict_e.gz --output data/JMdict_e.gz
curl --fail --location https://www.edrdg.org/pub/Nihongo/JMnedict.xml.gz --output data/JMnedict.xml.gz
python3 scripts/build_dictionary.py data/JMdict_e.gz build/dictionary.sqlite
python3 scripts/add_names_dictionary.py build/dictionary.sqlite data/JMnedict.xml.gz build/dictionary-with-names.sqlite
```

Both builders require a fresh destination. Install the combined database on the pen as `dictionary.sqlite`, alongside `vendor/deinflect.json`. Retain the ordinary JMdict base for rebuilding names. Current source downloads can change entry counts; the original combined build contained approximately 1.06 million spelling/reading entries and occupied 208 MiB.

To update, download current source archives and build into new filenames, validate `PRAGMA integrity_check`, then atomically replace the installed dictionary. Preserve EDRDG attribution and the CC BY-SA 4.0 license when distributing derived data. See [EDRDG's license and updating requirements](https://www.edrdg.org/edrdg/licence.html) and [attribution](../vendor/ATTRIBUTION.txt).

## CPU baseline

```sh
python3 -m venv build/ocr-server-japanese
build/ocr-server-japanese/bin/pip install -r server/requirements-ocr.txt
build/ocr-server-japanese/bin/python scripts/fetch_ocr_model.py build/ppocrv5-server.onnx
build/ocr-server-japanese/bin/python scripts/ocr_server.py \
  --model build/ppocrv5-server.onnx --bind 127.0.0.1 --port 8193
```

The fetcher verifies the pinned model checksum. Model weights are downloaded separately and are not in Git. This recognition-only service expects the pen's stitched line image; it is not a general page-layout OCR API.

To enable the guarded Manga OCR corroboration used by the CPU prototype:

```sh
build/ocr-server-japanese/bin/pip install torch==2.9.1+cpu --index-url https://download.pytorch.org/whl/cpu
build/ocr-server-japanese/bin/pip install -r server/requirements-japanese.txt
build/ocr-server-japanese/bin/python scripts/fetch_japanese_ocr_model.py build/manga-ocr-model
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  build/ocr-server-japanese/bin/python scripts/ocr_server.py \
  --model build/ppocrv5-server.onnx --japanese-model build/manga-ocr-model \
  --bind YOUR_SERVER_IP --port 8193
```

Replace `YOUR_SERVER_IP` with your private LAN address. The OCR endpoint has no authentication; keep it on a trusted LAN/private network. Check `http://YOUR_SERVER_IP:8193/health`, then configure the pen's `Native.ScanBridge.endpoint` to `http://YOUR_SERVER_IP:8193/ocr`.

The example [systemd unit](../server/translatepen-ocr.service) assumes a checkout at `~/repos/translatepen`. Copy it into `~/.config/systemd/user/` and adjust its paths if needed. Put `TRANSLATEPEN_OCR_BIND=YOUR_SERVER_IP` in private `.runtime/ocr.env`; the unit otherwise binds to loopback. Install the Japanese dependencies/models before enabling this unit.

## Optional GPU assist

`scripts/gpu_ocr_assist.py` runs the CPU recognizer in parallel with an independently started, loopback-only llama.cpp server. It accepts bounded, corroborated repairs and keeps the CPU output when the GPU request fails or cannot support a correction.

The original deployment used an AMD RX 6750 XT, llama.cpp **b11455** with Vulkan, and **PaddleOCR-VL-For-Manga** Q4_K_M text weights plus a Q8_0 vision projector. GPU driver setup, model conversion and automated model downloads are not packaged in this preview. Obtain these separately; the example [GPU unit](../server/translatepen-gpu.service) records the expected local layout and arguments. Start its model backend on `127.0.0.1:8194` before running:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  build/ocr-server-japanese/bin/python scripts/gpu_ocr_assist.py \
  --model build/ppocrv5-server.onnx --japanese-model build/manga-ocr-model \
  --dictionary build/dictionary.sqlite --rules vendor/deinflect.json \
  --endpoint http://127.0.0.1:8194/v1/chat/completions \
  --bind YOUR_SERVER_IP --port 8193
```

Run one OCR frontend on port 8193: stop the standalone CPU frontend before starting the assist frontend. The [systemd drop-in](../server/translatepen-ocr.service.d/20-gpu-assist.conf) selects the assist frontend instead of the CPU frontend. The CPU-only setup has lower hardware requirements; it does not reproduce every GPU-assisted recovery.

## Data handling and limits

Images are processed in memory by default. Diagnostic capture is opt-in and can contain private reading material; keep captures outside public Git history. OCR can omit kana, confuse furigana or invent plausible characters. Dictionary agreement is a guard, not proof of what is printed.

The guarded GPU revision passed all 17 saved sentence cases and 17 of 20 compound checks, plus four recorded fresh physical scans on the author's setup. These are small development samples, not a broad accuracy benchmark. The raw private reading captures are excluded from this source release.
