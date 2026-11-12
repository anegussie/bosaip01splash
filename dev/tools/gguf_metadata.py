#!/usr/bin/env python3
"""Read or set one scalar key of a GGUF header, in place.

A GGUF's metadata is a table of key-value pairs before its tensor definitions
(runtime/model/GgufFile.hpp). Scalar keys - integers, floats, booleans,
strings - hold the architecture the engine checks against the target it builds
(GgufImage.cpp requireMetadata), so changing one means rewriting those bytes
where they lie. A key whose value is an array is left alone: its elements are
not a single scalar. The file's size never changes, so the tensor data after
the header stays where the header says it is.

    python3 dev/tools/gguf_metadata.py FILE [KEY [VALUE]]

With no KEY it prints every scalar key; with a KEY it prints its value, and
with a VALUE it writes it. An integer key is written as the same width it
already had; a float likewise."""

from __future__ import annotations

import argparse
import struct
import sys

# gguf_type: the value types a header holds, and the struct code and width of
# each scalar one.
SCALARS = {
    0: ("B", 1),
    1: ("b", 1),
    2: ("H", 2),
    3: ("h", 2),
    4: ("I", 4),
    5: ("i", 4),
    6: ("f", 4),
    7: ("?", 1),
    8: None,
    10: ("Q", 8),
    11: ("q", 8),
    12: ("d", 8),
}


def header(stream):
    """The magic, version, tensor count and metadata count of the GGUF at stream,
    positioned after its header, ready to read the metadata table."""
    magic = stream.read(4)
    if magic != b"GGUF":
        raise ValueError(f"not a GGUF: {magic!r}")
    version = struct.unpack("<I", stream.read(4))[0]
    tensors = struct.unpack("<Q", stream.read(8))[0]
    return version, tensors, struct.unpack("<Q", stream.read(8))[0]


def entries(stream, count):
    """(key, type, offset of its value, value) for each of the count metadata
    entries, walking the table once. An array reports its element type and
    count as its value; a string its text."""
    found = []
    for _ in range(count):
        key = stream.read(struct.unpack("<Q", stream.read(8))[0]).decode("utf-8")
        kind = struct.unpack("<I", stream.read(4))[0]
        offset = stream.tell()
        if kind == 9:  # ARRAY
            element = struct.unpack("<I", stream.read(4))[0]
            length = struct.unpack("<Q", stream.read(8))[0]
            if element == 8:
                value = [
                    stream.read(struct.unpack("<Q", stream.read(8))[0])
                    for _ in range(length)
                ]
            else:
                value = [
                    struct.unpack(
                        "<" + SCALARS[element][0], stream.read(SCALARS[element][1])
                    )[0]
                    for _ in range(length)
                ]
        elif kind == 8:  # STRING
            value = stream.read(struct.unpack("<Q", stream.read(8))[0]).decode("utf-8")
        else:
            code, width = SCALARS[kind]
            value = struct.unpack("<" + code, stream.read(width))[0]
        found.append((key, kind, offset, value))
    return found


def set_scalar(path, key, value):
    """Write value into key's scalar in the GGUF at path, keeping its type and
    width. Raises when the key is absent, an array, or of a kind value cannot
    fit; the file is rewritten only when the bytes actually change."""
    with open(path, "r+b") as stream:
        _, _, count = header(stream)
        for name, kind, offset, current in entries(stream, count):
            if name != key:
                continue
            if kind not in SCALARS or SCALARS[kind] is None:
                raise ValueError(f"{key} is not a scalar (type {kind})")
            code, width = SCALARS[kind]
            try:
                written = struct.pack("<" + code, value)
            except struct.error as error:
                raise ValueError(
                    f"{value} does not fit {key}'s {kind} type: {error}"
                ) from error
            if written == struct.pack("<" + code, current):
                return current
            stream.seek(offset)
            stream.write(written)
            stream.flush()
            return current
    raise KeyError(f"{key} is not in the GGUF header")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file")
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args(argv)

    def read(path):
        with open(path, "rb") as stream:
            _, _, count = header(stream)
            return entries(stream, count)

    if args.key is None:
        for name, kind, _, value in read(args.file):
            print(f"{name} = {value if kind != 9 else '<array>'}")
        return 0
    if args.value is None:
        for name, _, _, value in read(args.file):
            if name == args.key:
                print(value)
                return 0
        print(f"{args.key} is not in the header", file=sys.stderr)
        return 1
    previous = set_scalar(
        args.file, args.key, int(args.value) if args.value.isdigit() else args.value
    )
    print(f"{args.key}: {previous} -> {args.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
