#!/usr/bin/env python3
"""Fetch the pinned, checksum-verified optional Japanese recognition model."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

REVISION = 'aa6573bd10b0d446cbf622e29c3e084914df9741'
FILES = {
    'config.json': '8c0e395de8fa699daaac21aee33a4ba9bd1309cfbff03147813d2a025f39f349',
    'preprocessor_config.json': 'af4eb4d79cf61b47010fc0bc9352ee967579c417423b4917188d809b7e048948',
    'special_tokens_map.json': '303df45a03609e4ead04bc3dc1536d0ab19b5358db685b6f3da123d05ec200e3',  # gitleaks:allow - public model checksum
    'tokenizer_config.json': 'd775ad1deac162dc56b84e9b8638f95ed8a1f263d0f56f4f40834e26e205e266',  # gitleaks:allow - public model checksum
    'vocab.txt': '344fbb6b8bf18c57839e924e2c9365434697e0227fac00b88bb4899b78aa594d',
    'pytorch_model.bin': 'c63e0bb5b3ff798c5991de18a8e0956c7ee6d1563aca6729029815eda6f5c2eb',
}


def checksum(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        target = args.directory / name
        if target.exists():
            if checksum(target) != expected:
                raise SystemExit(f'Existing {name} has a different checksum; choose a fresh directory.')
        else:
            partial = target.with_suffix(target.suffix + '.partial')
            try:
                url = f'https://huggingface.co/kha-white/manga-ocr-base/resolve/{REVISION}/{name}'
                urllib.request.urlretrieve(url, partial)
                if checksum(partial) != expected:
                    raise SystemExit(f'Checksum mismatch for {name}')
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        print(f'{name}: verified', flush=True)


if __name__ == '__main__':
    main()
