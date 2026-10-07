#!/usr/bin/env python3
"""Download the fixed RapidOCR conversion of PaddleOCR's server recognizer."""
import argparse
import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

URL = (
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/"
    "onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_server.onnx"
)
SHA256 = "e09385400eaaaef34ceff54aeb7c4f0f1fe014c27fa8b9905d4709b65746562a"


def fetch(destination):
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError("existing model has an unexpected checksum")
        print(f"Verified existing model: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            with urllib.request.urlopen(URL, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != SHA256:
            raise RuntimeError("downloaded model failed checksum verification")
        os.replace(temporary, destination)
        print(f"Downloaded and verified: {destination}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    fetch(parser.parse_args().destination)
