#!/usr/bin/env python3
"""Extract QML/JS from the inspected MSE09 executable, without executing it.

This is intentionally tied to the SHA-256 of the device binary examined on
2026-10-05. Addresses come from its ELF symbol table. Resource format reference:
https://github.com/qt/qtbase/blob/v5.12.2/src/corelib/io/qresource.cpp
Vendor resources are for local inspection and must remain in research/private/.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import zlib

EXPECTED = "606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c"
BASE = 0x400000
DATA = 0x5AD000 - BASE
NAMES = 0x1081D00 - BASE
TREE = 0x108A590 - BASE
NODE_COUNT = 0x3AC8 // 22


def extract(binary: Path, output: Path) -> int:
    image = binary.read_bytes()
    if hashlib.sha256(image).hexdigest() != EXPECTED:
        raise ValueError("Unrecognized firmware executable; rederive resource addresses first")
    visited = set()
    count = 0

    def walk(node: int, parent: Path):
        nonlocal count
        if node in visited or not 0 <= node < NODE_COUNT:
            raise ValueError("Invalid resource tree")
        visited.add(node)
        position = TREE + 22 * node
        name_offset, flags = struct.unpack_from(">IH", image, position)
        length = struct.unpack_from(">H", image, NAMES + name_offset)[0]
        name = image[NAMES + name_offset + 6:NAMES + name_offset + 6 + length * 2].decode("utf-16be") if node else ""
        if node and (not name or name in (".", "..") or "/" in name or "\\" in name):
            raise ValueError("Unsafe resource name")
        path = parent / name
        if flags & 2:
            children, first = struct.unpack_from(">II", image, position + 6)
            for child in range(first, first + children):
                walk(child, path)
        elif path.suffix in (".qml", ".js"):
            offset = struct.unpack_from(">I", image, position + 10)[0]
            size = struct.unpack_from(">I", image, DATA + offset)[0]
            payload = image[DATA + offset + 4:DATA + offset + 4 + size]
            if flags & 1:
                payload = zlib.decompress(payload[4:])
            destination = output / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            count += 1

    walk(0, Path())
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(f"Extracted {extract(args.binary, args.output)} QML/JS files")
