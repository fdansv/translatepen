#!/usr/bin/env python3
"""Download and extract the pinned ARM64 toolchain without installing host packages."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name('toolchain-packages.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(package, cache, offline=False):
    target = cache / package['file']
    if target.exists():
        if digest(target) != package['sha256']:
            raise ValueError(f'Cached package checksum mismatch: {target}. Remove that file and retry.')
        return target
    if offline:
        raise FileNotFoundError(f'Offline cache is missing {target.name}')
    errors = []
    for url in package['urls']:
        temporary = target.with_suffix('.download')
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as stream:
                shutil.copyfileobj(response, stream)
            if digest(temporary) != package['sha256']:
                raise ValueError('Downloaded package checksum mismatch')
            temporary.replace(target)
            return target
        except (OSError, ValueError) as error:
            errors.append(str(error))
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError(f'Could not fetch {target.name}: ' + '; '.join(errors))


def bootstrap(destination, cache, manifest=MANIFEST, offline=False):
    data = json.loads(manifest.read_text())
    for package in data['packages']:
        if Path(package['file']).name != package['file'] or package['target'] not in {'cross', 'sysroot', 'qt-host'}:
            raise ValueError('Unexpected toolchain manifest path')
    marker = destination / 'toolchain-manifest.json'
    if destination.exists():
        if marker.is_file() and json.loads(marker.read_text()) == data:
            print(f'Pinned toolchain already assembled at {destination}')
            return
        raise FileExistsError(f'{destination} already exists with no matching manifest; use a new directory.')
    if platform.system() != 'Linux' or platform.machine() not in {'x86_64', 'amd64'}:
        raise RuntimeError('The pinned host tools require x86-64 Linux; use an Ubuntu 24.04 VM on other hosts.')
    if not shutil.which('dpkg-deb'):
        raise RuntimeError('Install dpkg (provides dpkg-deb) on the build host first.')
    cache.mkdir(parents=True, exist_ok=True)
    print(f'Checking/downloading {len(data["packages"])} pinned packages...', flush=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        archives = list(executor.map(lambda package: download(package, cache, offline), data['packages']))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='toolchain-', dir=destination.parent) as temporary:
        staging = Path(temporary) / 'root'
        staging.mkdir()
        for package, archive in zip(data['packages'], archives):
            subprocess.run(['dpkg-deb', '-x', str(archive), str(staging / package['target'])], check=True)
        # The original build layout separated these trees. One sysroot contains
        # all target headers/libraries; these relative aliases preserve the API.
        (staging / 'qt-sysroot').symlink_to('sysroot', target_is_directory=True)
        (staging / 'tesseract-arm64').symlink_to('sysroot', target_is_directory=True)
        (staging / 'toolchain-manifest.json').write_text(json.dumps(data, indent=2) + '\n')
        staging.rename(destination)
    print(f'Toolchain ready: {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT / 'build/toolchain')
    parser.add_argument('--cache', type=Path, default=ROOT / 'build/toolchain-downloads')
    parser.add_argument('--offline', action='store_true', help='Require every pinned package in the cache')
    args = parser.parse_args()
    try:
        bootstrap(args.destination.expanduser().resolve(), args.cache.expanduser().resolve(), offline=args.offline)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
