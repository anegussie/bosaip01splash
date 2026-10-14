#!/usr/bin/env python3
"""Inspect or prune idle scratch caches in build/validation performance runs.

Reports, replies, model installations and the production cache are untouched.
The default is a preview; --prune explicitly removes the listed cache files.
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import stat
from pathlib import Path

VALIDATION = Path(__file__).resolve().parents[2] / "build/validation"
CACHE_FILES = {"kv.slots", "kv.records", "state.slots", "state.records", "lock"}


def cache_roots(validation):
    for run in sorted(validation.glob("performance-*")):
        if run.is_symlink() or not run.is_dir():
            continue
        for path in sorted(run.glob("cache-*")):
            if re.fullmatch(r"cache-[1-9][0-9]*", path.name):
                yield path
        path = run / "launcher-live/persistent-cache"
        if path.exists():
            yield path
        for scratch in sorted(run.glob("scratch-*/cache")):
            if re.fullmatch(r"scratch-[a-z0-9_]{8}", scratch.parent.name):
                yield scratch


@contextlib.contextmanager
def locked_namespace(path):
    descriptor = os.open(path / "lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.fstat(descriptor).st_ino != (path / "lock").lstat().st_ino:
            raise ValueError(f"cache lock changed: {path}")
        yield
    finally:
        os.close(descriptor)


def inspect_root(root, validation):
    root = root.absolute()
    validation = validation.resolve()
    relative = root.relative_to(validation)
    if not relative.parts or not relative.parts[0].startswith("performance-"):
        raise ValueError(f"not a performance scratch cache: {root}")
    allowed = (
        (
            len(relative.parts) == 2
            and re.fullmatch(r"cache-[1-9][0-9]*", relative.parts[1])
        )
        or (
            len(relative.parts) == 3
            and relative.parts[1:] == ("launcher-live", "persistent-cache")
        )
        or (
            len(relative.parts) == 3
            and re.fullmatch(r"scratch-[a-z0-9_]{8}", relative.parts[1])
            and relative.parts[2] == "cache"
        )
    )
    if not allowed:
        raise ValueError(f"not a benchmark cache root: {root}")
    for parent in (root, *root.parents):
        if parent == validation:
            break
        if parent.is_symlink():
            raise ValueError(f"refusing symlink: {parent}")
    namespaces = sorted(root.iterdir())
    for namespace in namespaces:
        if (
            namespace.is_symlink()
            or not namespace.is_dir()
            or not re.fullmatch(r"[0-9a-f]{32}", namespace.name)
        ):
            raise ValueError(f"unexpected cache entry: {namespace}")
        metadata = namespace.stat()
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise ValueError(
                f"cache directory ownership or mode is unsafe: {namespace}"
            )
        names = {p.name for p in namespace.iterdir()}
        if "lock" not in names or not names <= CACHE_FILES:
            raise ValueError(f"unexpected cache files: {namespace}: {sorted(names)}")
        for file in namespace.iterdir():
            if not stat.S_ISREG(file.lstat().st_mode):
                raise ValueError(f"not a regular cache file: {file}")
    return namespaces


def clean(validation=VALIDATION, prune=False):
    validation = validation.resolve()
    rows = []
    for root in cache_roots(validation):
        row = {"path": str(root), "allocated_bytes": 0, "removed": False}
        try:
            namespaces = inspect_root(root, validation)
            with contextlib.ExitStack() as locks:
                for namespace in namespaces:
                    locks.enter_context(locked_namespace(namespace))
                # Recheck the allowlist after taking every lock before unlinking.
                inspect_root(root, validation)
                row["allocated_bytes"] = sum(
                    file.stat().st_blocks * 512
                    for namespace in namespaces
                    for file in namespace.iterdir()
                )
                if prune:
                    for namespace in namespaces:
                        for file in namespace.iterdir():
                            file.unlink()
                        namespace.rmdir()
                    root.rmdir()
                    row["removed"] = True
        except (OSError, ValueError) as error:
            row["skipped"] = str(error)
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args()
    rows = clean(prune=args.prune)
    print(
        json.dumps(
            {
                "prune": args.prune,
                "caches": rows,
                "allocated_bytes": sum(row["allocated_bytes"] for row in rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
